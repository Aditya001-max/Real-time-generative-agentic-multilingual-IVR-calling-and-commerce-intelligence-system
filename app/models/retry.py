"""Retry DB — fields: retry_id, order_id, next_attempt_time, attempt_count, status."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.db.session import Base


class RetryRecord(Base):
    __tablename__ = "retries"

    retry_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, index=True, nullable=False)
    user_phone = Column(String(20), nullable=False)
    call_type = Column(String(32), nullable=False)
    next_attempt_time = Column(DateTime, nullable=False)
    attempt_count = Column(Integer, default=1, nullable=False)
    status = Column(String(32), default="SCHEDULED", nullable=False)
    # SCHEDULED | RUNNING | COMPLETED | STOPPED | EXHAUSTED
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
