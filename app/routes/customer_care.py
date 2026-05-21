"""
Customer-Care Dashboard — single source of truth for Need-Help follow-ups.

When a customer presses the "Need Help" digit during the IVR (digit 2 on
CONFIRMATION calls, digit 3 on REJECTION calls), help_router writes a row
into the `help_requests` table with:
  • their phone number, preferred language, call time
  • the product / order / payment / address details
  • a bucket: 'working_hours' or 'next_working_day'
  • a callback_due_at timestamp

This module exposes that table to the support team:

  GET  /customer-care/dashboard          → JSON, two lists side by side
  GET  /customer-care/dashboard.html     → simple browser view, auto-refresh
  POST /customer-care/{id}/status        → flip status (IN_PROGRESS, RESOLVED…)
  GET  /customer-care/{id}               → row detail (for the call screen)

Times are returned in both UTC (raw ISO) and Asia/Kolkata (display string)
so the team always sees a sensible local time.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import pytz
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.models import AuditLog, HelpRequest

log = get_logger(__name__)

router = APIRouter(prefix="/customer-care", tags=["customer-care"])

_IST = pytz.timezone("Asia/Kolkata")

OPEN_STATUSES = ("PENDING", "IN_PROGRESS")


def _to_ist_str(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    return pytz.utc.localize(dt).astimezone(_IST).strftime("%Y-%m-%d %H:%M IST")


def _row_to_dict(row: HelpRequest) -> dict:
    return {
        "help_request_id": row.help_request_id,
        "ticket_id": row.ticket_id,
        "call_log_id": row.call_log_id,
        "order_id": row.order_id,
        "user_phone": row.user_phone,
        "preferred_language": row.preferred_language,
        "call_type": row.call_type,
        "requested_at_utc": row.requested_at.isoformat() if row.requested_at else None,
        "requested_at_ist": _to_ist_str(row.requested_at),
        "callback_due_at_utc": (
            row.callback_due_at.isoformat() if row.callback_due_at else None
        ),
        "callback_due_at_ist": _to_ist_str(row.callback_due_at),
        "product": {
            "name": row.product_name,
            "sku": row.product_sku,
            "quantity": row.quantity,
            "order_value": float(row.order_value) if row.order_value is not None else None,
            "cod_amount": float(row.cod_amount) if row.cod_amount is not None else None,
            "payment_mode": row.payment_mode,
        },
        "address": {
            "city": row.city,
            "state": row.state,
            "pincode": row.pincode,
        },
        "bucket": row.bucket,
        "status": row.status,
        "assigned_to": row.assigned_to,
        "resolved_at_ist": _to_ist_str(row.resolved_at),
        "notes": row.notes,
    }


# ---------- JSON dashboard ----------

@router.get("/dashboard")
def dashboard(
    include_resolved: bool = Query(
        False,
        description="Set true to include RESOLVED / WRONG_NUMBER rows in each list.",
    ),
    db: Session = Depends(get_db),
) -> dict:
    """Return the two follow-up lists in one payload.

    Polling this endpoint every few seconds is the simplest way for the
    team's dashboard to stay real-time.
    """
    base = db.query(HelpRequest)
    if not include_resolved:
        base = base.filter(HelpRequest.status.in_(OPEN_STATUSES))

    working = (
        base.filter(HelpRequest.bucket == "working_hours")
        .order_by(HelpRequest.callback_due_at.asc(), HelpRequest.help_request_id.asc())
        .all()
    )
    next_day = (
        base.filter(HelpRequest.bucket == "next_working_day")
        .order_by(HelpRequest.callback_due_at.asc(), HelpRequest.help_request_id.asc())
        .all()
    )

    return {
        "generated_at_ist": _to_ist_str(datetime.utcnow()),
        "include_resolved": include_resolved,
        "working_hour_followups": {
            "count": len(working),
            "items": [_row_to_dict(r) for r in working],
        },
        "next_working_hour_followups": {
            "count": len(next_day),
            "items": [_row_to_dict(r) for r in next_day],
        },
    }


# ---------- Status update (team flips this from the dashboard) ----------

class StatusIn(BaseModel):
    status: str           # PENDING | IN_PROGRESS | RESOLVED | WRONG_NUMBER
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


_VALID_STATUSES = {"PENDING", "IN_PROGRESS", "RESOLVED", "WRONG_NUMBER"}


@router.post("/{help_request_id}/status")
def update_status(
    help_request_id: int,
    payload: StatusIn,
    db: Session = Depends(get_db),
) -> dict:
    if payload.status not in _VALID_STATUSES:
        raise HTTPException(400, f"status must be one of {sorted(_VALID_STATUSES)}")
    row = db.get(HelpRequest, help_request_id)
    if not row:
        raise HTTPException(404, f"help_request {help_request_id} not found")

    row.status = payload.status
    if payload.assigned_to is not None:
        row.assigned_to = payload.assigned_to
    if payload.notes is not None:
        row.notes = payload.notes
    if payload.status in ("RESOLVED", "WRONG_NUMBER"):
        row.resolved_at = datetime.utcnow()
    row.updated_at = datetime.utcnow()

    db.add(AuditLog(
        event_type="HELP_REQUEST_STATUS_CHANGED",
        description=(
            f"help_request={help_request_id} status={payload.status} "
            f"agent={payload.assigned_to or '-'}"
        ),
        source="customer_care",
    ))
    db.commit()

    return _row_to_dict(row)


# ---------- Tiny browser dashboard ----------

_HTML = """<!doctype html>
<html><head>
<meta charset="utf-8">
<title>Divine Hindu — Customer Care</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: -apple-system, system-ui, Segoe UI, sans-serif; margin: 16px; color: #222; }
  h1 { margin: 0 0 4px; font-size: 22px; }
  .meta { color: #666; font-size: 13px; margin-bottom: 16px; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 900px) { .cols { grid-template-columns: 1fr; } }
  .col { border: 1px solid #ddd; border-radius: 6px; padding: 12px; }
  .col h2 { margin: 0 0 8px; font-size: 16px; }
  .col.work h2 { color: #0a7; }
  .col.next h2 { color: #b60; }
  .item { border-top: 1px solid #eee; padding: 10px 0; }
  .item:first-of-type { border-top: 0; }
  .row1 { font-weight: 600; }
  .row2, .row3 { color: #555; font-size: 13px; }
  .pill { display: inline-block; padding: 1px 6px; border-radius: 3px;
          background: #eef; color: #225; font-size: 11px; margin-left: 6px; }
  .pill.pending { background: #ffe; color: #770; }
  .pill.in_progress { background: #def; color: #036; }
  .empty { color: #888; font-style: italic; padding: 8px 0; }
  .actions { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
  .actions .label { font-size: 11px; color: #888; align-self: center; margin-right: 4px; }
  button { font-size: 12px; padding: 3px 8px; cursor: pointer; border-radius: 3px;
           border: 1px solid #bbb; background: #f7f7f7; }
  button:hover { background: #ececec; }
  button.primary { background: #0a7; color: #fff; border-color: #086; }
  button.primary:hover { background: #086; }
  button.danger  { background: #c33; color: #fff; border-color: #a22; }
  button.danger:hover { background: #a22; }
  button.warn    { background: #fb0; color: #333; border-color: #d90; }
  button.warn:hover { background: #d90; }
  button.muted   { background: #eee; color: #555; }
  button:disabled { opacity: 0.5; cursor: wait; }
</style>
</head><body>
<h1>Customer Care — Need-Help Follow-ups</h1>
<div class="meta" id="meta">loading…</div>
<div class="cols">
  <div class="col work"><h2 id="h-work">Working-hour follow-ups</h2><div id="work"></div></div>
  <div class="col next"><h2 id="h-next">Next working-day follow-ups</h2><div id="next"></div></div>
</div>
<script>
async function refresh() {
  const r = await fetch('/customer-care/dashboard');
  const d = await r.json();
  document.getElementById('meta').textContent = 'updated ' + d.generated_at_ist + ' — auto-refresh every 10s';
  document.getElementById('h-work').textContent = 'Working-hour follow-ups (' + d.working_hour_followups.count + ')';
  document.getElementById('h-next').textContent = 'Next working-day follow-ups (' + d.next_working_hour_followups.count + ')';
  render('work', d.working_hour_followups.items);
  render('next', d.next_working_hour_followups.items);
}
function render(slot, items) {
  const el = document.getElementById(slot);
  if (!items.length) { el.innerHTML = '<div class="empty">No open follow-ups.</div>'; return; }
  el.innerHTML = items.map(i => {
    const product = i.product.name ? (i.product.name + (i.product.quantity ? ' × ' + i.product.quantity : '')) : '(no product on file)';
    const cod = i.product.cod_amount ? ' • COD ₹' + i.product.cod_amount : '';
    const addr = [i.address.city, i.address.state, i.address.pincode].filter(Boolean).join(', ');
    const cls = i.status === 'IN_PROGRESS' ? 'in_progress' : 'pending';
    const isReject = i.call_type === 'REJECTION';
    // Context-aware "what did the customer say" buttons. Each fires
    // recordOutcome(...) which calls /team/call-result (updates Order
    // status in DB) and then marks the follow-up RESOLVED.
    const orderActions = isReject
      ? `
        <button class="primary" onclick="recordOutcome(${i.help_request_id}, ${i.ticket_id || 'null'}, 'accepted', 'create_redelivery')">Re-attempt delivery</button>
        <button class="danger"  onclick="recordOutcome(${i.help_request_id}, ${i.ticket_id || 'null'}, 'rejected')">Cancel order</button>`
      : `
        <button class="primary" onclick="recordOutcome(${i.help_request_id}, ${i.ticket_id || 'null'}, 'accepted')">Customer confirmed</button>
        <button class="danger"  onclick="recordOutcome(${i.help_request_id}, ${i.ticket_id || 'null'}, 'rejected')">Customer cancelled</button>`;
    return `<div class="item">
      <div class="row1">${i.user_phone} <span class="pill ${cls}">${i.status}</span> <span class="pill">${i.preferred_language || '-'}</span> <span class="pill">${i.call_type}</span></div>
      <div class="row2">${product}${cod} • Order #${i.order_id}</div>
      <div class="row3">requested ${i.requested_at_ist} • due ${i.callback_due_at_ist} ${addr ? '• ' + addr : ''}</div>
      <div class="actions">
        <span class="label">After call:</span>
        ${orderActions}
        <button class="warn"  onclick="recordOutcome(${i.help_request_id}, ${i.ticket_id || 'null'}, 'wants_callback')">Call back later</button>
        <button class="muted" onclick="recordOutcome(${i.help_request_id}, ${i.ticket_id || 'null'}, 'no_response')">No response</button>
        <button class="muted" onclick="recordOutcome(${i.help_request_id}, ${i.ticket_id || 'null'}, 'wrong_number')">Wrong #</button>
        <button class="muted" onclick="setStatus(${i.help_request_id}, 'IN_PROGRESS')">Calling…</button>
      </div>
    </div>`;
  }).join('');
}
function getAgent() {
  let agent = localStorage.getItem('cc_agent');
  if (!agent) {
    agent = prompt('Your name / agent id:') || 'unknown';
    localStorage.setItem('cc_agent', agent);
  }
  return agent;
}
async function setStatus(id, status) {
  const agent = getAgent();
  await fetch('/customer-care/' + id + '/status', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({status: status, assigned_to: agent}),
  });
  refresh();
}
async function recordOutcome(helpId, ticketId, outcome, nextAction) {
  // Disable buttons inside the item to prevent double-clicks.
  const ev = window.event;
  if (ev && ev.target) {
    const item = ev.target.closest('.item');
    if (item) item.querySelectorAll('button').forEach(b => b.disabled = true);
  }
  const agent = getAgent();
  // Step 1 — update the Order in DB via the existing team route, but only
  // if we have a ticket_id linked. (HelpRequests created defensively
  // without a ticket can still be marked resolved manually.)
  let orderUpdate = null;
  if (ticketId) {
    try {
      const body = {
        ticket_id: ticketId,
        agent_id: agent,
        duration_seconds: 0,
        outcome: outcome,
      };
      if (nextAction) body.next_action = nextAction;
      const r = await fetch('/team/call-result', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      });
      if (r.ok) {
        orderUpdate = await r.json();
      } else {
        const txt = await r.text();
        alert('Could not update order: ' + txt);
      }
    } catch (e) {
      alert('Could not update order: ' + e.message);
    }
  }
  // Step 2 — flip the follow-up row status. Terminal outcomes close it;
  // non-terminal outcomes keep it visible so the team can try again.
  const terminal = (outcome === 'accepted' || outcome === 'rejected' || outcome === 'wrong_number');
  let helpStatus = 'IN_PROGRESS';
  if (terminal) helpStatus = (outcome === 'wrong_number') ? 'WRONG_NUMBER' : 'RESOLVED';
  await fetch('/customer-care/' + helpId + '/status', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      status: helpStatus,
      assigned_to: agent,
      notes: outcome + (nextAction ? (' / ' + nextAction) : '')
              + (orderUpdate && orderUpdate.order_status ? (' → order: ' + orderUpdate.order_status) : ''),
    }),
  });
  refresh();
}
refresh();
setInterval(refresh, 10000);
</script>
</body></html>
"""


@router.get("/dashboard.html", response_class=HTMLResponse, include_in_schema=False)
def dashboard_html() -> HTMLResponse:
    """Browser-friendly view of /customer-care/dashboard. Auto-refreshes."""
    return HTMLResponse(_HTML)


# ---------- Row detail (registered LAST so the literal /dashboard*
# routes above match first; otherwise '/dashboard.html' would be
# coerced into the int path param). ----------

@router.get("/{help_request_id}")
def detail(help_request_id: int, db: Session = Depends(get_db)) -> dict:
    row = db.get(HelpRequest, help_request_id)
    if not row:
        raise HTTPException(404, f"help_request {help_request_id} not found")
    return _row_to_dict(row)
