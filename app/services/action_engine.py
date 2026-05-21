"""
Block 9 — Action Engine.

Responsibilities (per architecture diagram):
  • Process user response
  • Update order status (OMS)
  • Create ticket if needed (via TicketChain — Chatwoot OSS / generic HTTP)
  • Notify external systems (Notification Service: SMS/WhatsApp/Push)

External calls are best-effort. If no integration is configured, the
flow continues using local DB only — perfect for development.
"""
from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Order, Redelivery, Ticket
from app.services.greetings import DEFAULT_LANGUAGE
from app.services.tickets import TicketRequest, tickets
from app.services.translations import (
    P_AFTER_HOURS_TICKET,
    P_AGENT_TRANSFER,
    P_CANCELLED,
    P_INVALID_INPUT,
    P_ORDER_CONFIRMED,
    P_REATTEMPT,
    t,
)

log = get_logger(__name__)

_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


# ---------- OMS (Order Management System) ----------

def _update_local_order_status(db: Session, order_id: int, status: str) -> None:
    """Mirror the OMS status change in the local Order row, if it exists.

    The Order row exists if the order was imported via /rto/import or
    seeded manually. If not, we silently skip — keeps the IVR working
    for orders that were never put in the orders table.
    """
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if order:
        order.oms_status = status
        # Postgres trigger does this automatically; this line keeps SQLite working.
        db.commit()


def _ensure_redelivery_row(
    db: Session,
    order_id: int,
    call_id: int | None = None,
) -> None:
    """Create a redelivery row if one doesn't already exist for this order.

    Triggered when customer presses '1' on a REJECTION call (re-attempt).
    The Postgres trigger does this too — having it here as well means the
    flow works whether you're on Supabase Postgres or local SQLite.
    """
    existing = (
        db.query(Redelivery)
        .filter(Redelivery.order_id == order_id)
        .filter(Redelivery.delivery_status == "SCHEDULED")
        .first()
    )
    if existing:
        return
    db.add(Redelivery(
        order_id=order_id,
        triggered_by_call_id=call_id,
        delivery_status="SCHEDULED",
    ))
    db.commit()


def update_order_status(order_id: int, status: str) -> bool:
    """PATCH order status in OMS. Returns True on success."""
    if not settings.OMS_API_URL:
        log.info("[stub] OMS update: order=%s status=%s", order_id, status)
        return True
    try:
        r = httpx.patch(
            f"{settings.OMS_API_URL.rstrip('/')}/orders/{order_id}",
            headers={"Authorization": f"Bearer {settings.OMS_API_KEY}"},
            json={"status": status},
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.error("OMS update failed: order=%s err=%s", order_id, exc)
        return False


# ---------- Tickets (delegates to TicketChain) ----------

def create_ticket(
    db: Session,
    *,
    order_id: int,
    issue_type: str,
    user_phone: str = "",
    description: str = "",
    assigned_to: str | None = None,
) -> Ticket:
    """Create a ticket via the configured chain (Chatwoot first, then HTTP)."""
    if not description:
        description = (
            f"Automated call ticket. Order #{order_id}. "
            f"Reason: {issue_type.replace('_', ' ').title()}."
        )
    return tickets.create(
        db,
        TicketRequest(
            order_id=order_id,
            issue_type=issue_type,
            user_phone=user_phone,
            description=description,
            assigned_to=assigned_to,
        ),
    )


# ---------- Notification Service ----------

def notify(order_id: int, channel: str, message: str) -> None:
    """Fire-and-forget notification (SMS / WhatsApp / Push)."""
    if not settings.NOTIFICATION_API_URL:
        log.info("[stub] notify: order=%s channel=%s msg=%s", order_id, channel, message)
        return
    try:
        httpx.post(
            f"{settings.NOTIFICATION_API_URL.rstrip('/')}/send",
            headers={"Authorization": f"Bearer {settings.NOTIFICATION_API_KEY}"},
            json={"order_id": order_id, "channel": channel, "message": message},
            timeout=_TIMEOUT,
        )
    except httpx.HTTPError as exc:
        log.error("Notification failed: order=%s err=%s", order_id, exc)


# ---------- High-level handlers wired from Webhook Handler ----------

def handle_confirmation_response(
    db: Session,
    order_id: int,
    digit: str,
    user_phone: str = "",
    lang: str = DEFAULT_LANGUAGE,
) -> tuple[str, int | None]:
    """Confirmation IVR — Press 1 = Confirm, Press 2 = Need Help.

    Returns (spoken_message, ticket_id_or_None). The ticket_id is set
    when a help-ticket was created so the webhook can hand it to
    help_router for live-transfer-vs-queue routing. Retention score is
    recomputed on every order status change.
    """
    if digit == "1":
        update_order_status(order_id, "CONFIRMED")
        _update_local_order_status(db, order_id, "CONFIRMED")
        _recompute_retention(db, user_phone)
        notify(order_id, "sms", "Your order has been confirmed. Thank you!")
        return t(P_ORDER_CONFIRMED, lang), None
    if digit == "2":
        # Always create the help ticket; webhook + help_router decide whether
        # it's a live transfer or a queued callback. (No more is_working_hours
        # branching inside the action engine — that's help_router's job now.)
        ticket = create_ticket(
            db,
            order_id=order_id,
            issue_type="NEED_HELP",
            user_phone=user_phone,
            description=(
                f"Customer (lang={lang}) requested help during confirmation call "
                f"for order #{order_id}."
            ),
        )
        return t(P_AGENT_TRANSFER, lang), ticket.ticket_id
    return t(P_INVALID_INPUT, lang), None


def handle_rejection_response(
    db: Session,
    order_id: int,
    digit: str,
    user_phone: str = "",
    lang: str = DEFAULT_LANGUAGE,
) -> tuple[str, int | None]:
    """Rejection IVR — 1 = Re-attempt, 2 = Cancel, 3 = Need Help."""
    if digit == "1":
        update_order_status(order_id, "RE_ATTEMPT_DELIVERY")
        _update_local_order_status(db, order_id, "RE_ATTEMPT_DELIVERY")
        _ensure_redelivery_row(db, order_id)
        _recompute_retention(db, user_phone)
        notify(order_id, "sms", "We will re-attempt delivery of your order soon.")
        return t(P_REATTEMPT, lang), None
    if digit == "2":
        update_order_status(order_id, "CANCELLED")
        _update_local_order_status(db, order_id, "CANCELLED")
        _recompute_retention(db, user_phone)
        ticket = create_ticket(
            db,
            order_id=order_id,
            issue_type="CANCEL_REQUEST",
            user_phone=user_phone,
            description=(
                f"Customer (lang={lang}) cancelled order #{order_id} via "
                f"rejection-handling call."
            ),
        )
        notify(order_id, "sms", "Your order has been cancelled.")
        return t(P_CANCELLED, lang), ticket.ticket_id
    if digit == "3":
        ticket = create_ticket(
            db,
            order_id=order_id,
            issue_type="NEED_HELP",
            user_phone=user_phone,
            description=(
                f"Customer (lang={lang}) requested help during rejection call "
                f"for order #{order_id}."
            ),
        )
        return t(P_AGENT_TRANSFER, lang), ticket.ticket_id
    return t(P_INVALID_INPUT, lang), None


def _recompute_retention(db: Session, user_phone: str) -> None:
    """Best-effort retention recompute. Imported lazily to avoid cycles."""
    if not user_phone:
        return
    try:
        from app.services.retention import recompute_retention_score
        recompute_retention_score(db, user_phone)
    except Exception:  # noqa: BLE001
        log.exception("retention recompute failed for phone=%s", user_phone)
