"""TeamCallLog — recorded when the ops team calls a customer back.

Created by POST /team/call-result after the agent completes the callback.
Lets analytics compare 'IVR-only' vs 'IVR + team-assisted' resolution.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.db.session import Base


class TeamCallLog(Base):
    __tablename__ = "team_call_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(
        Integer,
        ForeignKey("tickets.ticket_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    order_id = Column(Integer, nullable=False, index=True)
    call_log_id = Column(
        Integer,
        ForeignKey("call_logs.call_id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_id = Column(String(64), nullable=False)
    called_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    duration_seconds = Column(Integer)
    outcome = Column(String(32), nullable=False)
    # accepted | rejected | wants_callback | no_response | wrong_number
    notes = Column(Text)
    is_within_working_hours = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
