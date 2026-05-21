"""
Block 12 — Analytics & Reporting.

Provides the metrics in the architecture diagram:
  • Total calls
  • Answer rate
  • Confirmation rate
  • Rejection rate
  • Working vs Non-working hours
  • Retry success rate
  • Excel export
"""
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import case, cast, Date, func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import CallLog, Order, RetryRecord, TeamCallLog, Ticket, User
from app.core.config import settings

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _safe_div(num: int, denom: int) -> float:
    return round(num / denom, 4) if denom else 0.0


@router.get("/summary")
def summary(db: Session = Depends(get_db)) -> dict:
    total = db.query(func.count(CallLog.call_id)).scalar() or 0
    answered = (
        db.query(func.count(CallLog.call_id))
        .filter(CallLog.status.in_(["ANSWERED", "COMPLETED"]))
        .scalar()
        or 0
    )
    confirmations = (
        db.query(func.count(CallLog.call_id))
        .filter(CallLog.call_type == "CONFIRMATION", CallLog.response == "1")
        .scalar()
        or 0
    )
    rejections = (
        db.query(func.count(CallLog.call_id))
        .filter(CallLog.call_type == "REJECTION", CallLog.response == "2")
        .scalar()
        or 0
    )
    retry_completed = (
        db.query(func.count(RetryRecord.retry_id))
        .filter(RetryRecord.status == "COMPLETED")
        .scalar()
        or 0
    )
    retry_total = db.query(func.count(RetryRecord.retry_id)).scalar() or 0
    tickets = db.query(func.count(Ticket.ticket_id)).scalar() or 0

    return {
        "total_calls": total,
        "answered_calls": answered,
        "answer_rate": _safe_div(answered, total),
        "confirmation_count": confirmations,
        "confirmation_rate": _safe_div(confirmations, total),
        "rejection_cancel_count": rejections,
        "rejection_cancel_rate": _safe_div(rejections, total),
        "retry_attempts_total": retry_total,
        "retry_success_rate": _safe_div(retry_completed, retry_total),
        "tickets_created": tickets,
        "working_hours": f"{settings.WORKING_HOURS_START}:00 – {settings.WORKING_HOURS_END}:00",
    }


@router.get("/export/excel")
def export_excel(db: Session = Depends(get_db)) -> StreamingResponse:
    """Download a multi-sheet .xlsx with all call data."""
    wb = Workbook()

    ws_calls = wb.active
    ws_calls.title = "Call Logs"
    ws_calls.append(
        ["call_id", "order_id", "phone", "type", "attempt", "status", "response", "timestamp"]
    )
    for c in db.query(CallLog).order_by(CallLog.timestamp.desc()).all():
        ws_calls.append(
            [
                c.call_id,
                c.order_id,
                c.user_phone,
                c.call_type,
                c.attempt_no,
                c.status,
                c.response or "",
                c.timestamp.isoformat(),
            ]
        )

    ws_retries = wb.create_sheet("Retries")
    ws_retries.append(
        ["retry_id", "order_id", "call_type", "attempt_count", "status", "next_attempt_time"]
    )
    for r in db.query(RetryRecord).order_by(RetryRecord.created_at.desc()).all():
        ws_retries.append(
            [
                r.retry_id,
                r.order_id,
                r.call_type,
                r.attempt_count,
                r.status,
                r.next_attempt_time.isoformat(),
            ]
        )

    ws_tickets = wb.create_sheet("Tickets")
    ws_tickets.append(["ticket_id", "order_id", "issue_type", "status", "created_at"])
    for t in db.query(Ticket).order_by(Ticket.created_at.desc()).all():
        ws_tickets.append(
            [t.ticket_id, t.order_id, t.issue_type, t.status, t.created_at.isoformat()]
        )

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="call_analytics.xlsx"'},
    )


# =====================================================================
# 6 ANALYTICS ENDPOINTS — what every team uses
# =====================================================================
# Each query is computed in Python so it works on both SQLite (dev) and
# Postgres (Supabase). On Postgres the matching v_* views in
# supabase/migrations/001_views_triggers_rls.sql produce identical numbers.

def _accepted_filter(call_type: str | None = None):
    """Predicate for "customer pressed the positive digit" — '1' for both
    CONFIRMATION (confirm) and REJECTION (re-attempt)."""
    if call_type == "REJECTION":
        return (CallLog.call_type == "REJECTION") & (CallLog.response == "1")
    if call_type == "CONFIRMATION":
        return (CallLog.call_type == "CONFIRMATION") & (CallLog.response == "1")
    return CallLog.response == "1"


@router.get("/funnel")
def funnel(
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Per (day, call_type): called → connected → responded → accepted + acceptance_pct."""
    q = db.query(
        cast(CallLog.timestamp, Date).label("day"),
        CallLog.call_type,
        func.count(CallLog.call_id).label("called"),
        func.sum(case((CallLog.status.in_(["ANSWERED", "COMPLETED"]), 1), else_=0)).label("connected"),
        func.sum(case((CallLog.response.isnot(None), 1), else_=0)).label("responded"),
        func.sum(case((CallLog.response == "1", 1), else_=0)).label("accepted"),
    )
    if date_from:
        q = q.filter(CallLog.timestamp >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(CallLog.timestamp < datetime.combine(date_to + timedelta(days=1), datetime.min.time()))
    rows = q.group_by("day", CallLog.call_type).order_by(func.max(CallLog.timestamp).desc()).all()

    out = []
    for r in rows:
        called = int(r.called or 0)
        accepted = int(r.accepted or 0)
        out.append({
            "day": r.day.isoformat() if r.day else None,
            "call_type": r.call_type,
            "called": called,
            "connected": int(r.connected or 0),
            "responded": int(r.responded or 0),
            "accepted": accepted,
            "acceptance_pct": round(100.0 * accepted / called, 2) if called else 0.0,
        })
    return out


@router.get("/hourly")
def hourly(db: Session = Depends(get_db)) -> dict:
    """24×7 grid of acceptance % over the last 30 days."""
    since = datetime.utcnow() - timedelta(days=30)
    rows = (
        db.query(
            func.extract("hour", CallLog.timestamp).label("hour"),
            func.extract("dow", CallLog.timestamp).label("dow"),
            func.count(CallLog.call_id).label("called"),
            func.sum(case((CallLog.response == "1", 1), else_=0)).label("accepted"),
        )
        .filter(CallLog.timestamp >= since)
        .group_by("hour", "dow")
        .all()
    )
    grid = {dow: {h: 0.0 for h in range(24)} for dow in range(7)}
    for r in rows:
        hour = int(r.hour) if r.hour is not None else 0
        dow = int(r.dow) if r.dow is not None else 0
        called = int(r.called or 0)
        accepted = int(r.accepted or 0)
        if dow in grid and hour in grid[dow]:
            grid[dow][hour] = round(100.0 * accepted / called, 2) if called else 0.0
    return {"window_days": 30, "acceptance_pct_by_dow_hour": grid}


@router.get("/retention")
def retention(limit: int = 100, db: Session = Depends(get_db)) -> list[dict]:
    """Top users by retention score with order counts and last-order timestamp."""
    sub_orders = (
        db.query(
            Order.user_phone.label("phone"),
            func.count(Order.order_id).label("lifetime_orders"),
            func.max(Order.updated_at).label("last_order_at"),
        )
        .group_by(Order.user_phone)
        .subquery()
    )
    rows = (
        db.query(
            User.phone_number,
            User.preferred_language,
            User.retention_score,
            sub_orders.c.lifetime_orders,
            sub_orders.c.last_order_at,
        )
        .outerjoin(sub_orders, sub_orders.c.phone == User.phone_number)
        .order_by(User.retention_score.desc().nullslast(), User.user_id.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "phone": r.phone_number,
            "preferred_language": r.preferred_language,
            "retention_score": float(r.retention_score) if r.retention_score is not None else 0.0,
            "lifetime_orders": int(r.lifetime_orders or 0),
            "last_order_at": r.last_order_at.isoformat() if r.last_order_at else None,
        }
        for r in rows
    ]


@router.get("/team-vs-ivr")
def team_vs_ivr(days: int = 90, db: Session = Depends(get_db)) -> dict:
    """Per-order resolution attribution + summary lift."""
    since = datetime.utcnow() - timedelta(days=days)
    orders = (
        db.query(Order)
        .filter(Order.created_at >= since)
        .order_by(Order.created_at.desc())
        .all()
    )
    out_rows = []
    counts = {"total": 0, "ivr_only": 0, "team_assisted": 0, "both": 0, "neither": 0}
    for o in orders:
        ivr_attempts = db.query(func.count(CallLog.call_id)).filter(CallLog.order_id == o.order_id).scalar() or 0
        team_attempts = db.query(func.count(TeamCallLog.id)).filter(TeamCallLog.order_id == o.order_id).scalar() or 0
        ivr_won = db.query(CallLog).filter(CallLog.order_id == o.order_id, CallLog.response == "1").first() is not None
        team_won = db.query(TeamCallLog).filter(TeamCallLog.order_id == o.order_id, TeamCallLog.outcome == "accepted").first() is not None
        out_rows.append({
            "order_id": o.order_id,
            "final_status": o.oms_status,
            "resolved_by_ivr": ivr_won,
            "resolved_by_team": team_won,
            "ivr_attempts": int(ivr_attempts),
            "team_attempts": int(team_attempts),
        })
        counts["total"] += 1
        if ivr_won and team_won: counts["both"] += 1
        elif ivr_won: counts["ivr_only"] += 1
        elif team_won: counts["team_assisted"] += 1
        else: counts["neither"] += 1

    ivr_only_pct = (100.0 * counts["ivr_only"] / counts["total"]) if counts["total"] else 0.0
    team_assist_pct = (100.0 * counts["team_assisted"] / counts["total"]) if counts["total"] else 0.0
    return {
        "window_days": days,
        "summary": {
            **counts,
            "ivr_only_pct": round(ivr_only_pct, 2),
            "team_assist_lift_pct": round(team_assist_pct, 2),
        },
        "orders": out_rows,
    }


@router.get("/language-performance")
def language_performance(db: Session = Depends(get_db)) -> list[dict]:
    """Per language: total calls, acceptance %, avg duration, retry count."""
    rows = (
        db.query(
            CallLog.language,
            func.count(CallLog.call_id).label("total_calls"),
            func.sum(case((CallLog.response == "1", 1), else_=0)).label("accepted"),
            func.sum(case((CallLog.attempt_no > 1, 1), else_=0)).label("retry_calls"),
        )
        .filter(CallLog.language.isnot(None))
        .group_by(CallLog.language)
        .order_by(func.count(CallLog.call_id).desc())
        .all()
    )
    out = []
    for r in rows:
        total = int(r.total_calls or 0)
        accepted = int(r.accepted or 0)
        out.append({
            "language": r.language,
            "total_calls": total,
            "acceptance_pct": round(100.0 * accepted / total, 2) if total else 0.0,
            "retry_count": int(r.retry_calls or 0),
        })
    return out


@router.get("/working-hours-split")
def working_hours_split(db: Session = Depends(get_db)) -> dict:
    """Live-transfer vs queued-callback outcomes (uses tickets.routing + team_call_logs)."""
    live_total = db.query(func.count(Ticket.ticket_id)).filter(Ticket.routing == "connected_to_team").scalar() or 0
    live_accepted = (
        db.query(func.count(TeamCallLog.id))
        .join(Ticket, Ticket.ticket_id == TeamCallLog.ticket_id)
        .filter(Ticket.routing == "connected_to_team", TeamCallLog.outcome == "accepted")
        .scalar() or 0
    )
    queued_total = db.query(func.count(Ticket.ticket_id)).filter(Ticket.routing == "queued_after_hours").scalar() or 0
    queued_accepted = (
        db.query(func.count(TeamCallLog.id))
        .join(Ticket, Ticket.ticket_id == TeamCallLog.ticket_id)
        .filter(Ticket.routing == "queued_after_hours", TeamCallLog.outcome == "accepted")
        .scalar() or 0
    )
    live_pct = round(100.0 * live_accepted / live_total, 2) if live_total else 0.0
    queued_pct = round(100.0 * queued_accepted / queued_total, 2) if queued_total else 0.0
    return {
        "live_transfer": {"attempts": int(live_total), "accepted": int(live_accepted), "acceptance_pct": live_pct},
        "queued_callback": {"attempts": int(queued_total), "accepted": int(queued_accepted), "acceptance_pct": queued_pct},
        "lift_pct": round(live_pct - queued_pct, 2),
    }
