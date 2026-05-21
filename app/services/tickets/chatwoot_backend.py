"""
Chatwoot ticket backend (open source, self-hosted, FREE).

Chatwoot models tickets as 'conversations' attached to 'contacts' inside an 'inbox'.
We use the Application API (api_access_token in header).

Flow:
  1. Search for contact by phone → reuse if found
  2. Else create contact
  3. Create conversation with the issue description as the first message

Docs: https://developers.chatwoot.com/api-reference/
"""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.tickets.base import TicketBackend, TicketRequest, TicketResult

log = get_logger(__name__)


class ChatwootBackend(TicketBackend):
    name = "chatwoot"

    @property
    def available(self) -> bool:
        return bool(
            settings.CHATWOOT_BASE_URL
            and settings.CHATWOOT_API_TOKEN
            and settings.CHATWOOT_ACCOUNT_ID
            and settings.CHATWOOT_INBOX_ID
        )

    def create(self, req: TicketRequest) -> TicketResult:
        with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
            contact_id = self._upsert_contact(client, req)
            conv_id = self._create_conversation(client, contact_id, req)
            return TicketResult(backend=self.name, external_id=str(conv_id))

    # ---------- internals ----------

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "api_access_token": settings.CHATWOOT_API_TOKEN,
            "Content-Type": "application/json",
        }

    @property
    def _account_path(self) -> str:
        return (
            f"{settings.CHATWOOT_BASE_URL.rstrip('/')}"
            f"/api/v1/accounts/{settings.CHATWOOT_ACCOUNT_ID}"
        )

    def _upsert_contact(self, client: httpx.Client, req: TicketRequest) -> int:
        # 1. Try to find existing by phone
        r = client.get(
            f"{self._account_path}/contacts/search",
            headers=self._headers,
            params={"q": req.user_phone, "include": "contact_inboxes"},
        )
        r.raise_for_status()
        meta = r.json().get("meta", {})
        payload = r.json().get("payload", [])
        if meta.get("count", 0) > 0 and payload:
            return int(payload[0]["id"])

        # 2. Create new contact
        r = client.post(
            f"{self._account_path}/contacts",
            headers=self._headers,
            json={
                "inbox_id": settings.CHATWOOT_INBOX_ID,
                "name": f"Order #{req.order_id}",
                "phone_number": req.user_phone,
            },
        )
        r.raise_for_status()
        return int(r.json()["payload"]["contact"]["id"])

    def _create_conversation(
        self,
        client: httpx.Client,
        contact_id: int,
        req: TicketRequest,
    ) -> int:
        body = {
            "inbox_id": settings.CHATWOOT_INBOX_ID,
            "contact_id": contact_id,
            "status": "open",
            "additional_attributes": {
                "order_id": req.order_id,
                "issue_type": req.issue_type,
            },
            "message": {
                "content": req.description,
                "message_type": "incoming",
            },
        }
        if req.assigned_to:
            body["assignee_id"] = req.assigned_to

        r = client.post(
            f"{self._account_path}/conversations",
            headers=self._headers,
            json=body,
        )
        r.raise_for_status()
        return int(r.json()["id"])
