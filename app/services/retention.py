"""
Retention scoring.

Score = (positive lifetime orders) / max(1, total lifetime orders)
        clamped to [0.000, 1.000].

Positive statuses: CONFIRMED, REDELIVERED, RE_ATTEMPT_DELIVERY, DELIVERED
Negative statuses count toward the denominator: CANCELLED, RTO_PENDING

Called from:
  - action_engine.handle_confirmation_response (after status update)
  - action_engine.handle_rejection_response   (after status update)
  - team.call_result                           (after status update)

Cheap (1 query). Idempotent. Safe to call repeatedly.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Order, User

log = get_logger(__name__)

POSITIVE_STATUSES = ("CONFIRMED", "REDELIVERED", "RE_ATTEMPT_DELIVERY", "DELIVERED")
COUNTING_STATUSES = POSITIVE_STATUSES + ("CANCELLED", "RTO_PENDING")


def recompute_retention_score(db: Session, user_phone: str) -> float:
    """Recompute and persist the user's retention score. Returns the new score."""
    if not user_phone:
        return 0.0

    user = db.query(User).filter(User.phone_number == user_phone).first()
    if not user:
        return 0.0

    row = (
        db.query(
            func.count(Order.order_id).label("total"),
            func.sum(
                case((Order.oms_status.in_(POSITIVE_STATUSES), 1), else_=0)
            ).label("positive"),
        )
        .filter(Order.user_phone == user_phone)
        .filter(Order.oms_status.in_(COUNTING_STATUSES))
        .one()
    )
    total = int(row.total or 0)
    positive = int(row.positive or 0)
    score = round(positive / total, 3) if total else 0.0
    score = max(0.0, min(1.0, score))

    user.retention_score = Decimal(str(score))
    db.commit()
    log.info(
        "retention: phone=%s positive=%d/%d score=%.3f",
        user_phone, positive, total, score,
    )
    return score
