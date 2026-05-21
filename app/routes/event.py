"""
Block 2 — Event Listener (REST API entry point).

Receives ORDER_PLACED / ORDER_REJECTED events from the existing system,
validates the payload, and hands off to the Decision Engine + Retry Engine.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.models import AuditLog, Order, RetryRecord, User
from app.schemas import EventIn, EventOut
from app.services.decision_engine import decide
from app.workers.retry_tasks import schedule_retry_chain

log = get_logger(__name__)

router = APIRouter(prefix="/event", tags=["events"])

# State strings longer than 2 chars are stored as NULL (the column is VARCHAR(2)).
_VALID_STATE_LEN = 2


def _ensure_user(db: Session, phone: str, state: str | None = None) -> User:
    """Lazy-create the User row, and remember/refresh the latest delivery state."""
    safe_state = state if state and len(state) == _VALID_STATE_LEN else None
    user = db.query(User).filter(User.phone_number == phone).first()
    if user is None:
        user = User(phone_number=phone, delivery_state=safe_state)
        db.add(user)
        db.flush()
        return user
    if safe_state and user.delivery_state != safe_state:
        user.delivery_state = safe_state
    return user


def _ensure_order(
    db: Session,
    *,
    order_id: int,
    user_phone: str,
    user_id: int | None,
    state: str | None,
    event_type: str,
) -> None:
    """Lazy-create a minimal Order row so action_engine OMS updates aren't no-ops.

    Without this, every confirmation/rejection IVR ran against a non-existent
    Order — the customer pressed 1 to confirm, but the order status never moved.
    """
    if db.query(Order).filter(Order.order_id == order_id).first():
        return
    db.add(Order(
        order_id=order_id,
        user_phone=user_phone,
        user_id=user_id,
        state=state,
        oms_status="RTO_PENDING" if event_type == "ORDER_REJECTED" else "PLACED",
        is_rto=(event_type == "ORDER_REJECTED"),
    ))


def _has_active_chain(db: Session, order_id: int, call_type: str) -> bool:
    """True if a retry chain is already running for this (order_id, call_type)."""
    return (
        db.query(RetryRecord)
        .filter(
            RetryRecord.order_id == order_id,
            RetryRecord.call_type == call_type,
            RetryRecord.status.in_(("SCHEDULED", "RUNNING")),
        )
        .first()
        is not None
    )


@router.post("/", response_model=EventOut)
def receive_event(payload: EventIn, db: Session = Depends(get_db)) -> EventOut:
    log.info("event received: %s", payload.model_dump())

    user = _ensure_user(db, payload.user_phone, payload.state)

    decision = decide(payload.event_type)
    if not decision.proceed:
        raise HTTPException(status_code=400, detail=decision.reason)

    _ensure_order(
        db,
        order_id=payload.order_id,
        user_phone=payload.user_phone,
        user_id=user.user_id,
        state=payload.state,
        event_type=payload.event_type,
    )

    # Idempotency — refuse a second event while a chain is still active for
    # this (order, call_type). Prevents the duplicate-retry-rows pattern that
    # produced 8+ retry rows per order in test data.
    if _has_active_chain(db, payload.order_id, decision.call_type):
        db.add(AuditLog(
            event_type="EVENT_DUPLICATE_IGNORED",
            description=(
                f"order={payload.order_id} type={payload.event_type} "
                f"call_type={decision.call_type} reason=active_chain_exists"
            ),
            source="event_listener",
        ))
        db.commit()
        return EventOut(
            status="ignored",
            message=(
                f"{decision.call_type} chain already active for order "
                f"{payload.order_id}; not queuing duplicate."
            ),
        )

    db.add(
        AuditLog(
            event_type="EVENT_RECEIVED",
            description=(
                f"order={payload.order_id} type={payload.event_type} "
                f"state={payload.state or '-'} call_type={decision.call_type} "
                f"working_hours={decision.is_within_working_hours}"
            ),
            source="event_listener",
        )
    )
    db.commit()

    schedule_retry_chain(
        order_id=payload.order_id,
        user_phone=payload.user_phone,
        call_type=decision.call_type,
        state=payload.state,
    )

    return EventOut(
        status="accepted",
        message=f"{decision.call_type} call queued for order {payload.order_id}",
    )
