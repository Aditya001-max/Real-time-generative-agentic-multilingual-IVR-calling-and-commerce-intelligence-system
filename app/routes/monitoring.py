"""
Block 11 — Monitoring & Alerts.

Endpoints:
  GET  /monitoring/health           — liveness
  GET  /monitoring/system-health    — DB + Redis + Ozonetel + AI-voice snapshot
  GET  /monitoring/alerts/failures  — recent failed calls (alertable)
  GET  /monitoring/alerts/retries   — orders nearing retry exhaustion
  POST /monitoring/tts-test         — synthesize a one-off phrase to verify AI voice
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models import CallLog, RetryRecord
from app.services.tickets import tickets
from app.services.tts import tts

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/system-health")
def system_health(db: Session = Depends(get_db)) -> dict:
    db_ok = True
    try:
        db.execute(func.count(CallLog.call_id).select())
    except Exception:  # noqa: BLE001
        db_ok = False

    return {
        "database": "ok" if db_ok else "error",
        "redis_configured": bool(settings.REDIS_URL),
        "ozonetel_configured": bool(settings.OZONETEL_API_KEY and settings.OZONETEL_DID),
        "ai_voice_enabled": tts.enabled,
        "ai_voice_active_backends": tts.active_backends,
        "ai_voice_priority_order": settings.TTS_PROVIDERS,
        "ticket_active_backends": tickets.active_backends,
        "ticket_priority_order": settings.TICKET_PROVIDERS,
        "base_url": settings.BASE_URL,
    }


class TTSTestIn(BaseModel):
    text: str = "Hello, this is a test of the AI voice system."


@router.post("/tts-test")
def tts_test(payload: TTSTestIn) -> dict:
    """Synthesize a phrase and return the public audio URL (or fallback note)."""
    url = tts.synth_url(payload.text)
    if url:
        return {
            "status": "ok",
            "audio_url": url,
            "active_backends": tts.active_backends,
        }
    return {
        "status": "fallback",
        "audio_url": None,
        "reason": (
            "AI voice disabled, no backend available, or all backends failed — "
            "Ozonetel native <playtext> would be used"
        ),
    }



@router.get("/alerts/failures")
def call_failure_alerts(db: Session = Depends(get_db)) -> dict:
    """Calls that failed in the last 24h."""
    since = datetime.utcnow() - timedelta(hours=24)
    failed = (
        db.query(CallLog)
        .filter(CallLog.status.in_(["FAILED", "NO_ANSWER"]), CallLog.timestamp >= since)
        .order_by(CallLog.timestamp.desc())
        .limit(100)
        .all()
    )
    return {
        "window_hours": 24,
        "count": len(failed),
        "items": [
            {
                "call_id": c.call_id,
                "order_id": c.order_id,
                "attempt_no": c.attempt_no,
                "status": c.status,
                "timestamp": c.timestamp.isoformat(),
            }
            for c in failed
        ],
    }


@router.get("/alerts/retries")
def high_retry_alerts(db: Session = Depends(get_db)) -> dict:
    """Orders that have hit attempt 3 or 4 — likely to need manual outreach."""
    high = (
        db.query(RetryRecord)
        .filter(RetryRecord.attempt_count >= 3)
        .order_by(RetryRecord.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "count": len(high),
        "items": [
            {
                "order_id": r.order_id,
                "attempt_count": r.attempt_count,
                "status": r.status,
                "next_attempt_time": r.next_attempt_time.isoformat(),
            }
            for r in high
        ],
    }
