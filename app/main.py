"""
FastAPI application entry point.

Wires together all 12 architecture blocks:
  Event Listener → Decision Engine → Call Manager → Telephony Provider
  Webhook Handler → Action Engine → Data Storage
  Retry Engine (Celery)
  Monitoring & Alerts → Analytics & Reporting

On startup, pre-warms the AI voice cache so the first real call has
zero TTS latency.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.logging import get_logger, setup_logging
from app.db.session import Base, engine
from app.routes import analytics, audio, customer_care, event, monitoring, rto, team, webhook
from app.services.greetings import LANGUAGE_MENU_LINES, SUPPORTED_LANGUAGES
from app.services.translations import all_prompt_strings_for
from app.services.tts import tts

setup_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    # Create tables (use Alembic in real production).
    Base.metadata.create_all(bind=engine)

    # Seed default working_hours_config row if missing (read by help_router).
    from app.db.session import SessionLocal
    from app.models import WorkingHoursConfig
    with SessionLocal() as _seed_db:
        if not _seed_db.query(WorkingHoursConfig).filter(
            WorkingHoursConfig.team_name == "default"
        ).first():
            _seed_db.add(WorkingHoursConfig(
                team_name="default",
                start_hour=9,
                end_hour=19,
                days_of_week="mon,tue,wed,thu,fri,sat",
                timezone="Asia/Kolkata",
                live_transfer_enabled=True,
            ))
            _seed_db.commit()
            log.info("seeded default working_hours_config")

    # Pre-warm the TTS cache for static prompts. Done at startup so the
    # first real call doesn't pay the synthesis latency. We pre-warm for
    # ALL supported languages so a Tamil-speaking caller hears no synthesis
    # delay either.
    if tts.enabled:
        log.info(
            "AI voice enabled — pre-warming static prompts for %d languages",
            len(SUPPORTED_LANGUAGES),
        )
        # Pre-warm each (text, lang) pair so the first real call has zero
        # synthesis latency in any chosen language.
        items: list[tuple[str, str]] = []
        for lang in SUPPORTED_LANGUAGES:
            for text in all_prompt_strings_for(lang):
                items.append((text, lang))
        # Plus the language-picker menu lines (each one in its own language).
        for _digit, lang_code, _locale, menu_text in LANGUAGE_MENU_LINES:
            items.append((menu_text, lang_code))
        # De-duplicate while preserving order.
        unique_items = list(dict.fromkeys(items))
        results = tts.prewarm(unique_items)
        ok = sum(1 for v in results.values() if v)
        log.info(
            "pre-warmed %d/%d static prompts across %d languages",
            ok, len(unique_items), len(SUPPORTED_LANGUAGES),
        )
    else:
        log.info("AI voice disabled — using Ozonetel native <playtext> fallback")

    yield


app = FastAPI(
    title="AI Call Automation Microservice",
    description=(
        "Order Confirmation & Rejection Handling — implementation of the "
        "Automated Call System architecture, with open-source TTS (Coqui) "
        "and ticketing (Chatwoot) replacing paid services."
    ),
    version="1.2.0",
    lifespan=lifespan,
)

app.include_router(event.router)        # Block 2 — Event Listener
app.include_router(webhook.router)      # Block 6 — Webhook Handler
app.include_router(audio.router)        # Audio cache server (for AI voice)
app.include_router(monitoring.router)   # Block 11 — Monitoring & Alerts
app.include_router(analytics.router)    # Block 12 — Analytics & Reporting
app.include_router(rto.router)          # Block 13 — RTO Recovery & Excel Sync
app.include_router(team.router)         # Block 14 — Ops team callback results
app.include_router(customer_care.router)  # Block 15 — Need-Help follow-up dashboard


@app.get("/", tags=["meta"])
def root() -> dict:
    from app.services.tickets import tickets

    return {
        "service": "AI Call Automation Microservice",
        "status": "running",
        "ai_voice": {
            "enabled": tts.enabled,
            "active_backends": tts.active_backends,
        },
        "tickets": {
            "active_backends": tickets.active_backends,
        },
        "docs": "/docs",
    }
