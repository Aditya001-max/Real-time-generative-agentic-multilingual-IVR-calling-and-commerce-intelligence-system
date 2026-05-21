"""Unit tests for app/services/help_router.py."""
from datetime import datetime
from unittest.mock import patch

import pytest
import pytz

from app.services.help_router import _next_working_slot, _parse_days


IST = pytz.timezone("Asia/Kolkata")
DAYS_MON_SAT = {0, 1, 2, 3, 4, 5}  # Mon..Sat


def _ist(year, month, day, hour, minute=0):
    return IST.localize(datetime(year, month, day, hour, minute))


# ---------- pure helpers ----------

def test_parse_days_csv():
    assert _parse_days("mon,tue,wed,thu,fri,sat") == DAYS_MON_SAT
    assert _parse_days("MON, sun ") == {0, 6}
    assert _parse_days("") == set()
    assert _parse_days("garbage,mon") == {0}


def test_next_slot_today_before_open():
    # Tuesday 07:00 IST, business opens at 09:00 → today 09:00.
    now = _ist(2026, 5, 5, 7, 0)
    assert now.weekday() == 1  # Tue
    nxt = _next_working_slot(now, DAYS_MON_SAT, 9)
    assert nxt.weekday() == 1
    assert nxt.hour == 9 and nxt.minute == 0


def test_next_slot_after_close_on_weekday():
    # Tuesday 22:00 IST → next is Wednesday 09:00.
    now = _ist(2026, 5, 5, 22, 0)
    nxt = _next_working_slot(now, DAYS_MON_SAT, 9)
    assert nxt.weekday() == 2  # Wed
    assert nxt.hour == 9


def test_next_slot_saturday_late_skips_sunday():
    # Saturday 22:00 IST. Sun is closed → next is Monday 09:00.
    now = _ist(2026, 5, 9, 22, 0)
    assert now.weekday() == 5  # Sat
    nxt = _next_working_slot(now, DAYS_MON_SAT, 9)
    assert nxt.weekday() == 0  # Mon
    assert nxt.hour == 9


def test_next_slot_on_sunday_goes_to_monday():
    # Sunday any time → Monday 09:00.
    now = _ist(2026, 5, 10, 14, 0)
    assert now.weekday() == 6  # Sun
    nxt = _next_working_slot(now, DAYS_MON_SAT, 9)
    assert nxt.weekday() == 0  # Mon
    assert nxt.hour == 9


# ---------- end-to-end route_help_request, mocking time and DB ----------

class _FakeTicket:
    def __init__(self):
        self.routing = None
        self.scheduled_callback_at = None


class _FakeDB:
    """Minimal stand-in for sqlalchemy Session — only methods help_router calls."""
    def __init__(self, cfg):
        self._cfg = cfg
        self._tk = _FakeTicket()
        self.added = []
        self.committed = False

    def query(self, model):
        outer = self
        class _Q:
            def filter(self, *a, **k): return self
            def first(self_inner): return outer._cfg
        return _Q()

    def get(self, model, _id):
        return self._tk

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


def _cfg(**overrides):
    from app.models import WorkingHoursConfig
    base = dict(
        team_name="default",
        start_hour=9,
        end_hour=19,
        days_of_week="mon,tue,wed,thu,fri,sat",
        timezone="Asia/Kolkata",
        live_transfer_enabled=True,
    )
    base.update(overrides)
    return WorkingHoursConfig(**base)


def _utc_for_ist(y, m, d, hour):
    return IST.localize(datetime(y, m, d, hour)).astimezone(pytz.utc).replace(tzinfo=None)


@patch("app.services.help_router.settings")
@patch("app.services.help_router.datetime")
def test_route_live_transfer_in_business_hours(mock_dt, mock_settings):
    from app.services.help_router import route_help_request
    mock_dt.utcnow.return_value = _utc_for_ist(2026, 5, 5, 14)  # Tue 14:00 IST
    mock_settings.TEAM_HUNT_GROUP = "+919999999999"
    db = _FakeDB(_cfg())
    out = route_help_request(db, ticket_id=1, call_id=1, order_id=1, user_phone="+91", lang="en")
    assert out["mode"] == "live_transfer"
    assert out["dial_number"] == "+919999999999"
    assert db._tk.routing == "connected_to_team"


@patch("app.services.help_router.settings")
@patch("app.services.help_router.datetime")
def test_route_queued_after_hours(mock_dt, mock_settings):
    from app.services.help_router import route_help_request
    mock_dt.utcnow.return_value = _utc_for_ist(2026, 5, 5, 22)  # Tue 22:00 IST
    mock_settings.TEAM_HUNT_GROUP = "+919999999999"
    db = _FakeDB(_cfg())
    out = route_help_request(db, ticket_id=1, call_id=1, order_id=1, user_phone="+91", lang="hi")
    assert out["mode"] == "queued"
    assert db._tk.routing == "queued_after_hours"
    assert db._tk.scheduled_callback_at is not None


@patch("app.services.help_router.settings")
@patch("app.services.help_router.datetime")
def test_route_queued_on_sunday(mock_dt, mock_settings):
    from app.services.help_router import route_help_request
    mock_dt.utcnow.return_value = _utc_for_ist(2026, 5, 10, 12)  # Sun 12:00 IST
    mock_settings.TEAM_HUNT_GROUP = "+919999999999"
    db = _FakeDB(_cfg())
    out = route_help_request(db, ticket_id=1, call_id=1, order_id=1, user_phone="+91", lang="ta")
    assert out["mode"] == "queued"


@patch("app.services.help_router.settings")
@patch("app.services.help_router.datetime")
def test_route_queued_when_team_hunt_group_empty(mock_dt, mock_settings):
    from app.services.help_router import route_help_request
    mock_dt.utcnow.return_value = _utc_for_ist(2026, 5, 5, 14)  # Tue 14:00 IST (open)
    mock_settings.TEAM_HUNT_GROUP = ""  # but no number configured
    db = _FakeDB(_cfg())
    out = route_help_request(db, ticket_id=1, call_id=1, order_id=1, user_phone="+91", lang="en")
    assert out["mode"] == "queued"
