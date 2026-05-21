"""Call Logs DB — fields: call_id, order_id, call_type, attempt_no, status, response, timestamp."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from app.db.session import Base


class CallLog(Base):
    __tablename__ = "call_logs"

    call_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, index=True, nullable=False)
    user_phone = Column(String(20), nullable=False)
    call_type = Column(String(32), nullable=False)  # CONFIRMATION | REJECTION
    attempt_no = Column(Integer, default=1, nullable=False)
    status = Column(String(32), default="INITIATED", nullable=False)
    # INITIATED | RINGING | ANSWERED | NO_ANSWER | FAILED | COMPLETED
    response = Column(String(64), nullable=True)  # confirm | accept | cancel | help | None
    # Language the IVR was conducted in (set when language picker resolves
    # or copied from User.preferred_language for returning callers).
    language = Column(String(8), nullable=True, index=True)
    # State at the time of THIS call (audit trail; user may move later).
    delivery_state = Column(String(2), nullable=True, index=True)
    # Ozonetel KooKoo session ID. The DB column is still named `twilio_sid`
    # from this codebase's Twilio days; the Python attribute is now
    # `provider_sid` so application code reads cleanly. SQLAlchemy maps
    # Python `provider_sid` → SQL `twilio_sid` via the explicit name arg,
    # so no migration is required.
    provider_sid = Column("twilio_sid", String(64), nullable=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
