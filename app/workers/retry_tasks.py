"""
Block 5 — Retry Engine.

Retry strategy (Divine Hindu spec):
  Attempt 1 — Immediately
  Attempt 2 — After 2 hours (only if no pickup / no response)
  Attempt 3 — After 2 more hours (only if no pickup / no response)
  Stop early as soon as the user picks up and presses any valid digit.

The early-stop signal is `CallLog.response is not None`. That gets set in
the webhook handler when the customer presses 1/2/3 on either the
CONFIRMATION or REJECTION IVR — so confirming an order, requesting
re-delivery, cancelling, or asking for help all halt the retry chain
immediately. After-hours "talk to agent" requests are queued for callback
by app/services/help_router.py and similarly do not trigger more retries.

Implementation: Celery `apply_async(countdown=…)` for time-based retries.
Each attempt:
  1. Checks if the user already responded → if yes, marks retry COMPLETED and exits.
  2. Otherwise places a new call via the Call Manager.
  3. Schedules the next attempt with the appropriate delay.
"""
from datetime import datetime, timedelta

from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import AuditLog, CallLog, RetryRecord
from app.services.call_manager import initiate_call
from app.workers.celery_worker import celery

log = get_logger(__name__)

# Three attempts total: the initial call + two retries at 2-hour intervals.
MAX_ATTEMPTS = 3

# Delay (in seconds) BEFORE attempt N is fired.
# attempt 1 → immediate; attempt 2 → 2 h after attempt 1; attempt 3 → 2 h after attempt 2.
_TWO_HOURS = 2 * 60 * 60
RETRY_DELAYS_SEC: dict[int, int] = {
    1: 0,
    2: _TWO_HOURS,
    3: _TWO_HOURS,
}


def _user_already_responded(db, order_id: int) -> bool:
    """If any CallLog for this order has a response captured, stop retrying."""
    return (
        db.query(CallLog)
        .filter(CallLog.order_id == order_id, CallLog.response.isnot(None))
        .first()
        is not None
    )


def schedule_retry_chain(
    order_id: int,
    user_phone: str,
    call_type: str,
    state: str | None = None,
) -> None:
    """Kick off attempt 1 immediately and let the chain self-perpetuate."""
    run_attempt.apply_async(
        kwargs={
            "order_id": order_id,
            "user_phone": user_phone,
            "call_type": call_type,
            "attempt": 1,
            "state": state,
        },
        countdown=RETRY_DELAYS_SEC[1],
    )


@celery.task(bind=True, name="retry.run_attempt", max_retries=0)
def run_attempt(
    self,
    order_id: int,
    user_phone: str,
    call_type: str,
    attempt: int,
    state: str | None = None,
) -> None:  # noqa: ARG001
    """Single retry attempt. Calls the Call Manager, then schedules the next one.

    Persists exactly ONE RetryRecord per attempt (status flips
    SCHEDULED → RUNNING → COMPLETED / STOPPED / EXHAUSTED). The next attempt
    is scheduled via Celery countdown but NOT pre-inserted as a separate row —
    earlier versions inserted both a COMPLETED and a SCHEDULED row per
    attempt, which produced 8+ rows per chain.
    """
    db = SessionLocal()
    try:
        if attempt > MAX_ATTEMPTS:
            log.info("retry exhausted: order=%s", order_id)
            db.query(RetryRecord).filter(
                RetryRecord.order_id == order_id,
                RetryRecord.call_type == call_type,
                RetryRecord.status == "SCHEDULED",
            ).update({"status": "EXHAUSTED"})
            db.add(
                AuditLog(
                    event_type="RETRY_EXHAUSTED",
                    description=f"order={order_id} after {MAX_ATTEMPTS} attempts",
                    source="retry_engine",
                )
            )
            db.commit()
            return

        # Stop early if the user already responded on a prior attempt.
        if _user_already_responded(db, order_id):
            log.info("user responded; stopping retries for order=%s", order_id)
            db.query(RetryRecord).filter(
                RetryRecord.order_id == order_id,
                RetryRecord.call_type == call_type,
                RetryRecord.status.in_(("SCHEDULED", "RUNNING")),
            ).update({"status": "STOPPED"})
            db.commit()
            return

        # Reuse ANY active row (SCHEDULED or RUNNING) for this (order_id,
        # call_type), regardless of stored attempt_count. The unique
        # constraint `ux_retries_active_chain` only allows one active row
        # per chain, so a stale RUNNING row from a crashed prior attempt
        # would otherwise block the INSERT here. Update its attempt_count
        # to the current value instead.
        retry = (
            db.query(RetryRecord)
            .filter(
                RetryRecord.order_id == order_id,
                RetryRecord.call_type == call_type,
                RetryRecord.status.in_(("SCHEDULED", "RUNNING")),
            )
            .order_by(RetryRecord.retry_id.desc())
            .first()
        )
        if retry is None:
            retry = RetryRecord(
                order_id=order_id,
                user_phone=user_phone,
                call_type=call_type,
                next_attempt_time=datetime.utcnow(),
                attempt_count=attempt,
                status="RUNNING",
            )
            db.add(retry)
        else:
            retry.status = "RUNNING"
            retry.attempt_count = attempt
            retry.next_attempt_time = datetime.utcnow()
            retry.user_phone = user_phone
        db.commit()

        # Place the call.
        initiate_call(
            db,
            order_id=order_id,
            user_phone=user_phone,
            call_type=call_type,
            attempt_no=attempt,
            state=state,
        )

        retry.status = "COMPLETED"
        db.commit()

        # Schedule next attempt if any remain.
        next_attempt = attempt + 1
        if next_attempt <= MAX_ATTEMPTS:
            delay = RETRY_DELAYS_SEC[next_attempt]
            run_attempt.apply_async(
                kwargs={
                    "order_id": order_id,
                    "user_phone": user_phone,
                    "call_type": call_type,
                    "attempt": next_attempt,
                    "state": state,
                },
                countdown=delay,
            )
            log.info(
                "scheduled retry: order=%s attempt=%s in %ss",
                order_id, next_attempt, delay,
            )
            # The DB has a unique constraint `ux_retries_active_chain` on
            # (order_id, call_type) for any row whose status is in
            # (SCHEDULED, RUNNING). If a stale SCHEDULED row from a prior
            # chain still exists (e.g. left over from an older code path
            # with different MAX_ATTEMPTS), inserting a fresh row here
            # raises IntegrityError and crashes the task. Reuse the
            # existing row instead so the constraint is respected and we
            # remain idempotent across config changes / worker restarts.
            scheduled = (
                db.query(RetryRecord)
                .filter(
                    RetryRecord.order_id == order_id,
                    RetryRecord.call_type == call_type,
                    RetryRecord.status.in_(("SCHEDULED", "RUNNING")),
                )
                .order_by(RetryRecord.retry_id.desc())
                .first()
            )
            new_next_attempt_time = datetime.utcnow() + timedelta(seconds=delay)
            if scheduled is not None:
                scheduled.attempt_count = next_attempt
                scheduled.next_attempt_time = new_next_attempt_time
                scheduled.user_phone = user_phone
                scheduled.status = "SCHEDULED"
            else:
                db.add(
                    RetryRecord(
                        order_id=order_id,
                        user_phone=user_phone,
                        call_type=call_type,
                        next_attempt_time=new_next_attempt_time,
                        attempt_count=next_attempt,
                        status="SCHEDULED",
                    )
                )
            db.commit()
    finally:
        db.close()
