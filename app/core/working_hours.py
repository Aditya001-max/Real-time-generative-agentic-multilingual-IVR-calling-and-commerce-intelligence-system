"""
Working Hours Logic (architecture diagram side-panel).

Working Hours (default 10 AM – 6 PM):
    → User chooses 'Need Help' → Connect to live agent

Non-working Hours:
    → Play message "We will call you during working hours"
    → Create ticket
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def is_working_hours(now: datetime | None = None) -> bool:
    """Return True if current time is within configured working hours."""
    tz = ZoneInfo(settings.TIMEZONE)
    now = now or datetime.now(tz)
    if now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    return settings.WORKING_HOURS_START <= now.hour < settings.WORKING_HOURS_END
