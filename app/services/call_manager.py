"""
Block 4 — Call Manager.

Responsibilities (per architecture diagram):
  • Create call request
  • Select IVR script
  • Save call attempt
  • Send to Telephony API

This is the orchestrator that the Event Listener and Retry Engine both call.
"""
from datetime import datetime

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import AuditLog, CallLog
from app.services.telephony import telephony

log = get_logger(__name__)


def initiate_call(
    db: Session,
    *,
    order_id: int,
    user_phone: str,
    call_type: str,
    attempt_no: int = 1,
    state: str | None = None,
) -> CallLog:
    """Create a CallLog row, place the call, persist the SID. Returns the CallLog.

    `state` is a 2-letter ISO 3166-2:IN code (e.g. GJ, TN). It pins the
    region-aware language picker to a specific menu shape for this call.
    """
    call = CallLog(
        order_id=order_id,
        user_phone=user_phone,
        call_type=call_type,
        attempt_no=attempt_no,
        status="INITIATED",
        delivery_state=state,
        timestamp=datetime.utcnow(),
    )
    db.add(call)
    db.flush()  # assign call_id

    try:
        sid = telephony.place_call(
            to_phone=user_phone,
            call_id=call.call_id,
            call_type=call_type,
            state=state,
            order_id=order_id,
        )
        call.provider_sid = sid
        call.status = "RINGING"
        db.add(
            AuditLog(
                event_type="CALL_INITIATED",
                description=f"order={order_id} type={call_type} attempt={attempt_no} sid={sid}",
                source="call_manager",
            )
        )
    except Exception as exc:  # noqa: BLE001
        call.status = "FAILED"
        log.exception("Call placement failed for order=%s", order_id)
        db.add(
            AuditLog(
                event_type="CALL_FAILED",
                description=f"order={order_id} error={exc}",
                source="call_manager",
            )
        )
    finally:
        db.commit()
        db.refresh(call)

    return call
