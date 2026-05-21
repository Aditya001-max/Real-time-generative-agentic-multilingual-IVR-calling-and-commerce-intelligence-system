"""
Block 7 — Telephony Provider adapter (Ozonetel KooKoo).

Replaces the previous Twilio integration. Public API is unchanged so the
Call Manager (block 4) is untouched: `telephony.place_call(...)` returns
a provider call SID string, just like before.

Outbound flow:
  1. We hit Ozonetel's outbound API over HTTPS with: phone_no, api_key,
     caller_id (DID), and `url` (our webhook).
  2. Ozonetel rings the customer.
  3. When the customer answers, KooKoo fetches our `url` with
     event=NewCall — see app/routes/webhook.py /voice-start.

Endpoint configuration:
  • Default base/path target Ozonetel CloudAgent (the user's account).
  • Override OZONETEL_API_BASE / OZONETEL_OUTBOUND_PATH in .env if your
    plan uses raw KooKoo (in1-cpaas.ozonetel.com /outbound/outbound.php).
"""
from __future__ import annotations

import base64
import re
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


def _normalize_phone(raw: str) -> str:
    """Ozonetel expects digits-only Indian numbers (10 digits, no +91).

    Accepts +918736001557, 918736001557, 08736001557, 8736001557.
    Returns 10-digit Indian number ('8736001557'). Raises if it can't.
    """
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError(f"could not normalize phone {raw!r} → {digits!r} (need 10 digits)")
    return digits


class TelephonyProvider:
    """Thin adapter over Ozonetel KooKoo's outbound HTTP API."""

    def __init__(self) -> None:
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            # follow_redirects=True so KooKoo's http→https 301 (May 2026)
            # doesn't surface as an HTTPStatusError. Stays correct if they
            # ever flip back too.
            self._client = httpx.Client(timeout=_TIMEOUT, follow_redirects=True)
        return self._client

    def _outbound_url(self) -> str:
        base = settings.OZONETEL_API_BASE.rstrip("/")
        path = "/" + settings.OZONETEL_OUTBOUND_PATH.lstrip("/")
        return f"{base}{path}"

    def place_call(
        self,
        to_phone: str,
        call_id: int,
        call_type: str,
        state: str | None = None,
        order_id: int | None = None,
    ) -> str:
        """Place an outbound IVR call. Returns the provider's call SID.

        Routing (first match wins):
          1. OZONETEL_CAMPAIGN_NAME set → POST to CloudAgent
             AddCampaignData API. Ozonetel runs the campaign's pre-built
             IVR Flow (prompts, menus, agent transfer). This is the only
             path that uses CloudAgent IVR Flows — confirmed by Ozonetel
             docs and support.
          2. OZONETEL_APP_ID set → CPaaS outbound.php with app_id (legacy
             KooKoo CPaaS path; does NOT route through CloudAgent flows).
          3. Otherwise → CPaaS outbound.php with `url` pointing to our
             /webhook/voice-start which serves the IVR XML ourselves.
        """
        if not settings.OZONETEL_API_KEY or not settings.OZONETEL_DID:
            raise RuntimeError("Ozonetel credentials not configured")

        if settings.OZONETEL_CAMPAIGN_NAME:
            return self._place_call_via_campaign(
                to_phone=to_phone,
                call_id=call_id,
                call_type=call_type,
                state=state,
                order_id=order_id,
            )

        status_callback = f"{settings.BASE_URL}/webhook/status?call_id={call_id}"

        params: dict[str, Any] = {
            "api_key": settings.OZONETEL_API_KEY,
            "phone_no": _normalize_phone(to_phone),
            "outbound_version": "2",
            "caller_id": settings.OZONETEL_DID,
            "callback_url": status_callback,
        }
        if settings.OZONETEL_USERNAME:
            params["username"] = settings.OZONETEL_USERNAME

        if settings.OZONETEL_APP_ID:
            # CloudAgent IVR Flow path. extra_data is a pipe-delimited list
            # of key:value pairs that the IVR Flow can reference inside
            # Play/Condition/Transfer nodes.
            extra: list[str] = [
                f"call_id:{call_id}",
                f"call_type:{call_type}",
            ]
            if order_id is not None:
                extra.append(f"order_id:{order_id}")
            if state:
                extra.append(f"delivery_state:{state}")
            params["app_id"] = settings.OZONETEL_APP_ID
            params["extra_data"] = "|".join(extra)
        else:
            params["url"] = (
                f"{settings.BASE_URL}/webhook/voice-start"
                f"?call_id={call_id}&call_type={call_type}"
            )

        outbound = self._outbound_url()
        log.info(
            "placing call via ozonetel: to=%s call_id=%s type=%s endpoint=%s",
            to_phone, call_id, call_type, outbound,
        )

        resp = self.client.get(outbound, params=params)
        resp.raise_for_status()
        body = resp.text or ""
        log.info("ozonetel response: status=%d body=%s", resp.status_code, body[:300])

        # If the endpoint returned HTML instead of the expected XML/JSON
        # response, we hit the wrong URL (e.g. an admin UI page). Fail
        # loudly with a useful message so the user fixes OZONETEL_API_BASE
        # / OZONETEL_OUTBOUND_PATH instead of saving HTML as a SID.
        body_head = body.lstrip()[:50].lower()
        if body_head.startswith(("<!doctype html", "<html")):
            raise RuntimeError(
                "ozonetel: the configured endpoint returned an HTML page, not an API "
                "response. Check OZONETEL_API_BASE and OZONETEL_OUTBOUND_PATH in .env. "
                f"Endpoint hit: {outbound}"
            )

        sid = (
            _extract_xml_value(body, "sid")
            or _extract_xml_value(body, "callid")
            or _extract_xml_value(body, "call_id")
            or _extract_json_value(body, "sid")
            or _extract_json_value(body, "callid")
            or body.strip()
        )
        if not sid:
            raise RuntimeError(f"ozonetel: empty response, status={resp.status_code}")
        # DB column is varchar(64) — never store more than that, regardless
        # of what the provider returned.
        return sid[:64]


    def _place_call_via_campaign(
        self,
        to_phone: str,
        call_id: int,
        call_type: str,
        state: str | None = None,
        order_id: int | None = None,
    ) -> str:
        """Add a phone number to the configured CloudAgent Campaign so
        Ozonetel dials it and runs the campaign's IVR Flow.

        Endpoint (per Ozonetel docs):
          POST https://api.cloudagent.ozonetel.com/ca_apis/AddCampaignData
        Auth:
          apiKey header (NOT in body or query string)
        Body:
          JSON. campaignName + phoneNumber + userName are required.
          action="start" kicks off dialling immediately. CustomFields1-3
          carry our per-call context to the IVR Flow.
        """
        if not settings.OZONETEL_USERNAME:
            raise RuntimeError(
                "OZONETEL_USERNAME is required when using a CloudAgent campaign"
            )

        endpoint = (
            settings.OZONETEL_CLOUDAGENT_API_BASE.rstrip("/")
            + "/ca_apis/AddCampaignData"
        )

        body: dict[str, Any] = {
            "campaignName": settings.OZONETEL_CAMPAIGN_NAME,
            "phoneNumber": to_phone,
            "userName": settings.OZONETEL_USERNAME,
            "action": "start",
            "priority": 50,
            "checkDuplicate": False,
            "CustomFields1": f"call_id:{call_id}",
            "CustomFields2": f"call_type:{call_type}",
        }
        if order_id is not None or state:
            extras = []
            if order_id is not None:
                extras.append(f"order_id:{order_id}")
            if state:
                extras.append(f"delivery_state:{state}")
            body["CustomFields3"] = "|".join(extras)

        # CloudAgent supports two auth modes. We send BOTH the custom
        # `apiKey` header (legacy) AND the standard `Authorization: Basic`
        # header (per the "Basic Authentication" mode in CloudAgent admin
        # settings). Whichever the account is configured for will work;
        # the other is silently ignored.
        basic_token = base64.b64encode(
            f"{settings.OZONETEL_USERNAME}:{settings.OZONETEL_API_KEY}".encode()
        ).decode()
        headers = {
            "apiKey": settings.OZONETEL_API_KEY,
            "Authorization": f"Basic {basic_token}",
            "Content-Type": "application/json",
        }

        log.info(
            "placing call via CloudAgent campaign: to=%s call_id=%s type=%s campaign=%s endpoint=%s",
            to_phone, call_id, call_type, settings.OZONETEL_CAMPAIGN_NAME, endpoint,
        )

        resp = self.client.post(endpoint, json=body, headers=headers)
        body_text = resp.text or ""
        log.info("CloudAgent response: status=%d body=%s", resp.status_code, body_text[:500])

        # AddCampaignData typically returns a JSON envelope like
        # {"Success": "Data added successfully", "id": "..."} on 200,
        # or {"Error": "..."} on failure. Surface failures so the call
        # manager marks the call FAILED rather than storing junk as SID.
        if resp.status_code >= 400:
            raise RuntimeError(
                f"CloudAgent AddCampaignData failed: HTTP {resp.status_code} body={body_text[:300]}"
            )
        if '"Error"' in body_text or "error" in body_text.lower()[:50]:
            raise RuntimeError(f"CloudAgent rejected the request: {body_text[:300]}")

        # Best-effort SID extraction. CloudAgent doesn't return a call
        # SID upfront (the actual call_id arrives later via status
        # callback), so we use the lead id or a synthetic marker.
        sid = (
            _extract_json_value(body_text, "id")
            or _extract_json_value(body_text, "leadId")
            or _extract_json_value(body_text, "callId")
            or f"campaign:{settings.OZONETEL_CAMPAIGN_NAME}:{call_id}"
        )
        return sid[:64]


def _extract_xml_value(xml: str, tag: str) -> Optional[str]:
    m = re.search(rf"<{tag}>(.*?)</{tag}>", xml, re.IGNORECASE | re.DOTALL)
    return m.group(1).strip() if m else None


def _extract_json_value(text: str, key: str) -> Optional[str]:
    m = re.search(rf'"{key}"\s*:\s*"([^"]+)"', text)
    return m.group(1) if m else None


telephony = TelephonyProvider()
