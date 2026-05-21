"""Ticket DB — fields: ticket_id, order_id, issue_type, status, assigned_to."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.db.session import Base


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, index=True, nullable=False)
    issue_type = Column(String(64), nullable=False)
    # NEED_HELP | CANCEL_REQUEST | NO_RESPONSE | OUT_OF_HOURS
    status = Column(String(32), default="OPEN", nullable=False)
    assigned_to = Column(String(64), nullable=True)
    external_ticket_id = Column(String(64), nullable=True)
    # Set by app/services/help_router.py when a customer presses the help digit:
    #   'connected_to_team'   — live transferred to ops during business hours
    #   'queued_after_hours'  — scheduled for callback (see scheduled_callback_at)
    routing = Column(String(32), nullable=True)
    scheduled_callback_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
