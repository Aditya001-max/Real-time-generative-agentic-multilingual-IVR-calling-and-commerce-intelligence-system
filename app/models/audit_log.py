"""Audit Logs DB — fields: event_type, description, created_at, source."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from app.db.session import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(64), nullable=False, index=True)
    description = Column(Text, nullable=True)
    source = Column(String(64), nullable=False)
    # event_listener | decision_engine | call_manager | webhook | retry_engine | action_engine
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
