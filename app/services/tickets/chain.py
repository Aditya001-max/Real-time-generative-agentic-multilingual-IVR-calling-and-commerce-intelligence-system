"""
TicketChain — try backends in priority order, fall back on failure.
Always persists locally regardless of which backend succeeded (or even if
none succeeded — the local DB row is the source of truth).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.models import AuditLog, Ticket
from app.services.tickets.base import TicketBackend, TicketRequest, TicketResult
from app.services.tickets.chatwoot_backend import ChatwootBackend
from app.services.tickets.http_backend import HttpTicketBackend

log = get_logger(__name__)

_REGISTRY: dict[str, type[TicketBackend]] = {
    "chatwoot": ChatwootBackend,
    "http": HttpTicketBackend,
}


class TicketChain:
    def __init__(self) -> None:
        self._backends: list[TicketBackend] = self._build_chain()

    @property
    def active_backends(self) -> list[str]:
        return [b.name for b in self._backends if b.available]

    def create(self, db: Session, req: TicketRequest) -> Ticket:
        """Always create a local Ticket. Try external backends best-effort."""
        ticket = Ticket(
            order_id=req.order_id,
            issue_type=req.issue_type,
            status="OPEN",
            assigned_to=req.assigned_to,
        )
        db.add(ticket)
        db.flush()

        external_id, backend_name = self._try_backends(req)
        if external_id:
            ticket.external_ticket_id = external_id

        db.add(
            AuditLog(
                event_type="TICKET_CREATED",
                description=(
                    f"order={req.order_id} issue={req.issue_type} "
                    f"local_id={ticket.ticket_id} backend={backend_name or 'local_only'} "
                    f"external_id={external_id or '-'}"
                ),
                source="ticket_chain",
            )
        )
        db.commit()
        db.refresh(ticket)
        return ticket

    # ---------- internals ----------

    def _build_chain(self) -> list[TicketBackend]:
        names = [
            n.strip().lower()
            for n in settings.TICKET_PROVIDERS.split(",")
            if n.strip() and n.strip().lower() != "none"
        ]
        chain: list[TicketBackend] = []
        for name in names:
            cls = _REGISTRY.get(name)
            if cls is None:
                log.warning("tickets: unknown backend %r — skipping", name)
                continue
            chain.append(cls())
        return chain

    def _try_backends(self, req: TicketRequest) -> tuple[str | None, str | None]:
        for backend in self._backends:
            if not backend.available:
                continue
            try:
                result: TicketResult = backend.create(req)
                log.info(
                    "tickets: created via %s external_id=%s",
                    result.backend,
                    result.external_id,
                )
                return result.external_id, result.backend
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "tickets: backend=%s failed for order=%s — trying next. err=%s",
                    backend.name,
                    req.order_id,
                    exc,
                )
                continue
        return None, None


tickets = TicketChain()
