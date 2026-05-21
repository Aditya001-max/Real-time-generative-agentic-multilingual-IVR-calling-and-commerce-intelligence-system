"""User DB — fields: user_id, phone_number, preferences, timezone."""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, Numeric, String

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    preferences = Column(String(255), nullable=True)  # JSON-encoded preferences
    # Preferred IVR language (ISO 639-1 code: en, hi, ta, te, kn, ml, bn, mr, gu).
    # NULL = user has not picked yet → trigger language menu on next call.
    preferred_language = Column(String(8), nullable=True)
    # ISO 3166-2:IN code (2 letters, e.g. GJ, TN, UP). Drives the region-aware
    # IVR language picker via app/services/regions.py.
    delivery_state = Column(String(2), nullable=True)
    timezone = Column(String(64), default="Asia/Kolkata", nullable=False)
    # Lifetime confirmed / lifetime orders (0.000–1.000). Recomputed on every
    # order status change by app/services/retention.py.
    retention_score = Column(Numeric(4, 3), nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
