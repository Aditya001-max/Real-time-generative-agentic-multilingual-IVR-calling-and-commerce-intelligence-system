"""
Generic HTTP ticket backend.

Posts to a configurable URL — works as a thin adapter for Zendesk,
Freshdesk, or any in-house ticket API. Uses bearer-token auth.
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.services.tickets.base import TicketBackend, TicketRequest, TicketResult


class HttpTicketBackend(TicketBackend):
    name = "http"

    @property
    def available(self) -> bool:
        return bool(settings.TICKET_API_URL)

    def create(self, req: TicketRequest) -> TicketResult:
        headers = {"Content-Type": "application/json"}
        if settings.TICKET_API_KEY:
            headers["Authorization"] = f"Bearer {settings.TICKET_API_KEY}"

        with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            r = client.post(
                f"{settings.TICKET_API_URL.rstrip('/')}/tickets",
                headers=headers,
                json={
                    "order_id": req.order_id,
                    "issue_type": req.issue_type,
                    "phone": req.user_phone,
                    "description": req.description,
                    "assigned_to": req.assigned_to,
                },
            )
            r.raise_for_status()
            data = r.json() if r.content else {}
            return TicketResult(backend=self.name, external_id=str(data.get("id", "")))
