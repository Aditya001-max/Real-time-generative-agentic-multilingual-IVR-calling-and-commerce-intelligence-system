"""Celery app — backbone of block 5 (Retry Engine) + block 13 (Excel beat)."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery = Celery(
    "ai_call_system",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.workers.retry_tasks",
        "app.workers.excel_export",
    ],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone=settings.TIMEZONE,
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    beat_schedule={
        # 16:30 UTC = 22:00 IST (Asia/Kolkata is UTC+5:30, no DST)
        "daily-redelivery-export": {
            "task": "rto.daily_redelivery_export",
            "schedule": crontab(hour=16, minute=30),
        },
    },
)
