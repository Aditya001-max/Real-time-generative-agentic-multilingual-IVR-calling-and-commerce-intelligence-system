"""WorkingHoursConfig — per-team start/end/days, replaces .env-only config.

Read by app/services/help_router.py to decide live transfer vs queued
callback when a customer presses the 'help' digit during an IVR call.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.db.session import Base


class WorkingHoursConfig(Base):
    __tablename__ = "working_hours_config"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_name = Column(String(64), unique=True, nullable=False, index=True)
    start_hour = Column(Integer, nullable=False, default=9)
    end_hour = Column(Integer, nullable=False, default=19)
    # Comma-separated lowercase 3-letter day codes: 'mon,tue,wed,thu,fri,sat'
    days_of_week = Column(String(32), nullable=False, default="mon,tue,wed,thu,fri,sat")
    timezone = Column(String(64), nullable=False, default="Asia/Kolkata")
    live_transfer_enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
