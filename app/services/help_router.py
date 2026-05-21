"""
Help Router — decides whether a help-press connects live to the team or
queues a callback for the next working window.

Used by the webhook /handle endpoint when a customer presses the "help"
digit ("2" on CONFIRMATION calls, "3" on REJECTION calls).

Logic:
  1. Read working_hours_config WHERE team_name='default'.
  2. Convert datetime.utcnow() to that timezone (default Asia/Kolkata).
  3. is_open = (today's weekday in days_of_week)
              AND (start_hour <= hour < end_hour)
              AND live_transfer_enabled
              AND TEAM_HUNT_GROUP is configured
  4. If open  → mode='live_transfer'  ; ticket.routing='connected_to_team'
                                       ; spoken_message = P_AGENT_TRANSFER
  5. If closed → mode='queued'        ; ticket.routing='queued_after_hours'
                                       ; ticket.scheduled_callback_at = next slot
                                       ; spoken_message = P_CALLBACK_QUEUED

Returns a dict the webhook then plays / dials.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pytz
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models import (
    AuditLog,
    CallLog,
    HelpRequest,
    Order,
    Ticket,
    User,
    WorkingHoursConfig,
)
from app.services.translations import (
    P_AGENT_TRANSFER,
    P_CALLBACK_QUEUED,
    P_TEAM_WILL_CALLBACK,
    t,
)

log = get_logger(__name__)

# 0 = Monday, 6 = Sunday (matches Python's datetime.weekday())
_DAY_CODE_TO_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _parse_days(days_csv: str) -> set[int]:
    return {
        _DAY_CODE_TO_INDEX[d.strip().lower()]
        for d in days_csv.split(",")
        if d.strip().lower() in _DAY_CODE_TO_INDEX
    }


def _next_working_slot(now_local: datetime, days: set[int], start_hour: int) -> datetime:
    """Return the next datetime when the team is reachable, in `now_local`'s tz."""
    # If today is a working day and we're before start_hour, today's start is next.
    if now_local.weekday() in days and now_local.hour < start_hour:
        return now_local.replace(hour=start_hour, minute=0, second=0, microsecond=0)

    # Otherwise scan up to 7 days ahead.
    candidate = now_local.replace(hour=start_hour, minute=0, second=0, microsecond=0)
    for offset in range(1, 8):
        candidate = candidate + timedelta(days=1)
        if candidate.weekday() in days:
            return candidate
    # Should never hit this — week always has at least one working day.
    return now_local + timedelta(days=1)


def _load_config(db: Session) -> WorkingHoursConfig:
    cfg = (
        db.query(WorkingHoursConfig)
        .filter(WorkingHoursConfig.team_name == "default")
        .first()
    )
    if cfg:
        return cfg
    # Fallback: build a transient default object (don't persist).
    # 10:00–18:00 IST, Mon–Sat — matches Divine Hindu customer support hours.
    fallback = WorkingHoursConfig(
        team_name="default",
        start_hour=10,
        end_hour=18,
        days_of_week="mon,tue,wed,thu,fri,sat",
        timezone="Asia/Kolkata",
        live_transfer_enabled=True,
    )
    return fallback


def is_within_working_hours_now(db: Session, when_utc: Optional[datetime] = None) -> bool:
    """Standalone helper used by /team/call-result to record context."""
    cfg = _load_config(db)
    tz = pytz.timezone(cfg.timezone or "Asia/Kolkata")
    when_utc = when_utc or datetime.utcnow()
    local = pytz.utc.localize(when_utc).astimezone(tz)
    days = _parse_days(cfg.days_of_week)
    return (
        local.weekday() in days
        and cfg.start_hour <= local.hour < cfg.end_hour
        and cfg.live_transfer_enabled
    )


def route_help_request(
    db: Session,
    *,
    ticket_id: int,
    call_id: int,
    order_id: int,
    user_phone: str,
    lang: str = "en",
) -> dict:
    """Decide live transfer vs queued callback. Updates the ticket row.

    Returns:
        {
          'mode': 'live_transfer' | 'queued',
          'dial_number': str | None,        # only set when mode=='live_transfer'
          'next_slot_iso': str | None,      # only set when mode=='queued'
          'spoken_message': str,            # localized text to speak via the IVR
        }
    """
    cfg = _load_config(db)
    tz = pytz.timezone(cfg.timezone or "Asia/Kolkata")
    now_utc = datetime.utcnow()
    now_local = pytz.utc.localize(now_utc).astimezone(tz)
    days = _parse_days(cfg.days_of_week)

    in_working_hours = (
        now_local.weekday() in days
        and cfg.start_hour <= now_local.hour < cfg.end_hour
    )
    can_live_transfer = (
        in_working_hours
        and cfg.live_transfer_enabled
        and bool(settings.TEAM_HUNT_GROUP)
    )

    ticket = db.get(Ticket, ticket_id) if ticket_id else None

    if can_live_transfer:
        if ticket:
            ticket.routing = "connected_to_team"
            ticket.scheduled_callback_at = None
        bucket = "working_hours"
        callback_due_utc = now_utc
        result = {
            "mode": "live_transfer",
            "dial_number": settings.TEAM_HUNT_GROUP,
            "next_slot_iso": None,
            "spoken_message": t(P_AGENT_TRANSFER, lang),
        }
    elif in_working_hours:
        # We're inside working hours but no live-transfer destination is
        # configured (or live transfer is disabled). Queue the callback for
        # the team to handle now and tell the caller we'll reach out shortly,
        # NOT the after-hours "we'll call you back during working hours" line.
        callback_due_utc = now_utc
        if ticket:
            ticket.routing = "queued_in_hours"
            ticket.scheduled_callback_at = callback_due_utc
        bucket = "working_hours"
        result = {
            "mode": "queued",
            "dial_number": None,
            "next_slot_iso": now_local.isoformat(),
            "spoken_message": t(P_TEAM_WILL_CALLBACK, lang),
        }
    else:
        next_slot = _next_working_slot(now_local, days, cfg.start_hour)
        callback_due_utc = next_slot.astimezone(pytz.utc).replace(tzinfo=None)
        if ticket:
            ticket.routing = "queued_after_hours"
            # Store as naive UTC to match the rest of the schema's TIMESTAMP cols.
            ticket.scheduled_callback_at = callback_due_utc
        bucket = "next_working_day"
        result = {
            "mode": "queued",
            "dial_number": None,
            "next_slot_iso": next_slot.isoformat(),
            "spoken_message": t(P_CALLBACK_QUEUED, lang),
        }

    # Customer-care dashboard row: denormalize order + user context so the
    # support team has everything needed to call the customer back from a
    # single table. See app/models/help_request.py.
    _insert_help_request(
        db,
        ticket_id=ticket_id,
        call_id=call_id,
        order_id=order_id,
        user_phone=user_phone,
        lang=lang,
        bucket=bucket,
        callback_due_utc=callback_due_utc,
        requested_at_utc=now_utc,
    )

    db.add(AuditLog(
        event_type="HELP_ROUTED",
        description=(
            f"ticket={ticket_id} call={call_id} order={order_id} "
            f"phone={user_phone} mode={result['mode']} bucket={bucket} "
            f"next={result.get('next_slot_iso') or '-'}"
        ),
        source="help_router",
    ))
    db.commit()

    log.info(
        "help_router: ticket=%s mode=%s in_hours=%s live_transfer=%s now_local=%s",
        ticket_id, result["mode"], in_working_hours, can_live_transfer,
        now_local.isoformat(),
    )
    return result


def _insert_help_request(
    db: Session,
    *,
    ticket_id: int,
    call_id: int,
    order_id: int,
    user_phone: str,
    lang: str,
    bucket: str,
    callback_due_utc: datetime,
    requested_at_utc: datetime,
) -> None:
    """Write the dashboard-facing row for a Need-Help press.

    Pulls product + address details off the Order row (if present) and the
    preferred language off the User row (falls back to the IVR's `lang`).
    Failures are swallowed — the row is best-effort context for the team
    and must never break the IVR flow.
    """
    try:
        call = db.get(CallLog, call_id) if call_id else None
        call_type = call.call_type if call else "CONFIRMATION"

        order = (
            db.query(Order).filter(Order.order_id == order_id).first()
            if order_id else None
        )
        user = (
            db.query(User).filter(User.phone_number == user_phone).first()
            if user_phone else None
        )

        row = HelpRequest(
            ticket_id=ticket_id or None,
            call_log_id=call_id or None,
            order_id=order_id,
            user_phone=user_phone or "",
            preferred_language=(user.preferred_language if user else None) or lang,
            call_type=call_type,
            requested_at=requested_at_utc,
            product_name=order.product_name if order else None,
            product_sku=order.product_sku if order else None,
            quantity=order.quantity if order else None,
            order_value=order.order_value if order else None,
            cod_amount=order.cod_amount if order else None,
            payment_mode=order.payment_mode if order else None,
            city=order.city if order else None,
            state=order.state if order else None,
            pincode=order.pincode if order else None,
            bucket=bucket,
            callback_due_at=callback_due_utc,
            status="PENDING",
        )
        db.add(row)
    except Exception:  # noqa: BLE001
        log.exception(
            "failed to insert help_request row for order=%s phone=%s",
            order_id, user_phone,
        )
