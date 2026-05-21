"""HelpRequest DB — single source of truth for the customer-care dashboard.

Created every time a customer presses the "Need Help" digit during the IVR
(digit '2' on CONFIRMATION calls, digit '3' on REJECTION calls). Denormalizes
the user, order, product, and timing context into one row so the support
team has everything they need to call the customer back without joining
across tables.

Two buckets the dashboard separates on:
  • bucket='working_hours'    → request received during working hours.
                                Team contacts the customer immediately.
  • bucket='next_working_day' → request received outside working hours.
                                Team contacts the customer on the next
                                working day (callback_due_at is set).

Status lifecycle:
  PENDING → IN_PROGRESS → RESOLVED
                       ↘ WRONG_NUMBER (terminal)
"""
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)

from app.db.session import Base


class HelpRequest(Base):
    __tablename__ = "help_requests"

    help_request_id = Column(Integer, primary_key=True, autoincrement=True)

    # Foreign-ish links (kept nullable so a help row is never lost if the
    # parent record is missing — the team still needs to see it).
    ticket_id = Column(
        Integer,
        ForeignKey("tickets.ticket_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    call_log_id = Column(
        Integer,
        ForeignKey("call_logs.call_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    order_id = Column(Integer, nullable=False, index=True)

    # Who to call back
    user_phone = Column(String(20), nullable=False, index=True)
    preferred_language = Column(String(8), nullable=True)

    # Why they pressed help (CONFIRMATION or REJECTION call)
    call_type = Column(String(32), nullable=False)

    # When they pressed it (UTC). The dashboard renders this in IST.
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Product context — denormalized from the orders row at request time so
    # the team can see exactly what the customer was asking about, even if
    # the order is later edited or deleted.
    product_name = Column(Text, nullable=True)
    product_sku = Column(String(64), nullable=True)
    quantity = Column(Integer, nullable=True)
    order_value = Column(Numeric(12, 2), nullable=True)
    cod_amount = Column(Numeric(12, 2), nullable=True)
    payment_mode = Column(String(32), nullable=True)

    # Address context (helpful for the agent when greeting the customer)
    city = Column(String(64), nullable=True)
    state = Column(String(64), nullable=True)
    pincode = Column(String(12), nullable=True)

    # Dashboard separation: which list this row appears under.
    bucket = Column(String(32), nullable=False, index=True)
    # 'working_hours' | 'next_working_day'

    # When the team should contact the customer. For working-hours requests
    # this is roughly "now"; for after-hours it is the next working slot
    # (computed by help_router._next_working_slot).
    callback_due_at = Column(DateTime, nullable=False, index=True)

    # Workflow state the team flips from the dashboard.
    status = Column(String(32), default="PENDING", nullable=False, index=True)
    # PENDING | IN_PROGRESS | RESOLVED | WRONG_NUMBER

    assigned_to = Column(String(64), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
