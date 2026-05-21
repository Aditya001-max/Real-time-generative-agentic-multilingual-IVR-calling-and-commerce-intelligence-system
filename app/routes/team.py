"""
Team route — POST /team/call-result.

Called by the ops dashboard after an agent completes a callback. Mirrors
what the IVR action_engine would do, but driven by a human:

  outcome=accepted on REJECTION ticket + next_action=create_redelivery
       → INSERT redeliveries (SCHEDULED), Order.oms_status=RE_ATTEMPT_DELIVERY
  outcome=accepted on CONFIRMATION ticket
       → Order.oms_status=CONFIRMED
  outcome=rejected
       → Order.oms_status=CANCELLED (CONFIRMATION) or CANCELLED (REJECTION)
  outcome=wants_callback
       → Schedule a RetryRecord +2h
  outcome=no_response / wrong_number
       → just record the team_call_log; ticket stays OPEN

Always inserts a team_call_logs row + audit log entry, recomputes
users.retention_score for that phone, and closes the ticket on terminal
outcomes (accepted / rejected / wrong_number).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.models import (
    AuditLog,
    CallLog,
    Order,
    Redelivery,
    RetryRecord,
    TeamCallLog,
    Ticket,
    User,
)
from app.schemas import TeamCallResultIn, TeamCallResultOut
from app.services.help_router import is_within_working_hours_now
from app.services.retention import recompute_retention_score

router = APIRouter(prefix="/team", tags=["team"])
log = get_logger(__name__)


def _latest_call_for_order(db: Session, order_id: int) -> CallLog | None:
    return (
        db.query(CallLog)
        .filter(CallLog.order_id == order_id)
        .order_by(CallLog.call_id.desc())
        .first()
    )


@router.post("/call-result", response_model=TeamCallResultOut)
def call_result(
    payload: TeamCallResultIn,
    db: Session = Depends(get_db),
) -> TeamCallResultOut:
    """Record the outcome of an ops-team callback. Mirrors IVR action_engine."""
    ticket = db.get(Ticket, payload.ticket_id)
    if not ticket:
        raise HTTPException(404, f"Ticket {payload.ticket_id} not found")

    order_id = ticket.order_id
    order = db.query(Order).filter(Order.order_id == order_id).first()
    user_phone = order.user_phone if order else ""
    latest_call = _latest_call_for_order(db, order_id)
    is_rejection_ticket = (latest_call.call_type == "REJECTION") if latest_call else False

    # Always log the team call attempt.
    tcl = TeamCallLog(
        ticket_id=payload.ticket_id,
        order_id=order_id,
        call_log_id=latest_call.call_id if latest_call else None,
        agent_id=payload.agent_id,
        called_at=datetime.utcnow(),
        duration_seconds=payload.duration_seconds,
        outcome=payload.outcome,
        notes=payload.notes,
        is_within_working_hours=is_within_working_hours_now(db),
    )
    db.add(tcl)
    db.flush()  # get tcl.id

    redelivery_id: int | None = None
    new_order_status: str | None = order.oms_status if order else None

    # --- Outcome routing (mirrors IVR action_engine) ---
    if payload.outcome == "accepted":
        if is_rejection_ticket and payload.next_action == "create_redelivery":
            # Phase-2: customer confirmed they want redelivery
            existing = (
                db.query(Redelivery)
                .filter(Redelivery.order_id == order_id)
                .filter(Redelivery.delivery_status == "SCHEDULED")
                .first()
            )
            if existing:
                redelivery_id = existing.redelivery_id
            else:
                rd = Redelivery(
                    order_id=order_id,
                    triggered_by_call_id=latest_call.call_id if latest_call else None,
                    delivery_status="SCHEDULED",
                )
                db.add(rd)
                db.flush()
                redelivery_id = rd.redelivery_id
            if order:
                order.oms_status = "RE_ATTEMPT_DELIVERY"
                new_order_status = "RE_ATTEMPT_DELIVERY"
        else:
            # Phase-1: confirmation accepted by phone
            if order:
                order.oms_status = "CONFIRMED"
                new_order_status = "CONFIRMED"
        ticket.status = "CLOSED"

    elif payload.outcome == "rejected":
        if order:
            order.oms_status = "CANCELLED"
            new_order_status = "CANCELLED"
        ticket.status = "CLOSED"

    elif payload.outcome == "wants_callback":
        # Re-queue: schedule a retry +2h via the existing RetryRecord table.
        db.add(RetryRecord(
            order_id=order_id,
            user_phone=user_phone,
            call_type=latest_call.call_type if latest_call else "CONFIRMATION",
            next_attempt_time=datetime.utcnow() + timedelta(hours=2),
            attempt_count=(latest_call.attempt_no + 1) if latest_call else 1,
            status="SCHEDULED",
        ))
        # Ticket stays OPEN — retry will resolve it.

    elif payload.outcome == "no_response":
        # Ticket stays OPEN; ops will try again later.
        pass

    elif payload.outcome == "wrong_number":
        ticket.status = "CLOSED"
        if user_phone:
            user = db.query(User).filter(User.phone_number == user_phone).first()
            if user and user.preferences:
                user.preferences = (user.preferences or "") + ";invalid_phone=true"
            elif user:
                user.preferences = "invalid_phone=true"

    ticket.assigned_to = payload.agent_id

    # Retention score
    score: float | None = None
    if user_phone:
        try:
            score = recompute_retention_score(db, user_phone)
        except Exception:  # noqa: BLE001
            log.exception("retention recompute failed for %s", user_phone)

    db.add(AuditLog(
        event_type="TEAM_CALL_LOGGED",
        description=(
            f"ticket={payload.ticket_id} order={order_id} agent={payload.agent_id} "
            f"outcome={payload.outcome} next_action={payload.next_action or '-'}"
        ),
        source="team",
    ))
    db.commit()

    log.info(
        "team call-result: ticket=%s outcome=%s order=%s next=%s tcl=%s",
        payload.ticket_id, payload.outcome, order_id, payload.next_action, tcl.id,
    )

    return TeamCallResultOut(
        status="ok",
        team_call_log_id=tcl.id,
        ticket_status=ticket.status,
        order_status=new_order_status,
        redelivery_id=redelivery_id,
        retention_score=float(score) if score is not None else None,
    )
