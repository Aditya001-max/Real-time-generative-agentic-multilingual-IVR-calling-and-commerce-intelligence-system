"""
Daily Excel export — Celery beat task scheduled at 22:00 IST (16:30 UTC).

Generates redeliveries_YYYYMMDD.xlsx of all SCHEDULED redeliveries that
have not yet been exported, writes it to settings.EXCEL_EXPORT_DIR, marks
the rows exported_to_excel=TRUE, and (optionally) emails the file to the
ops team via SMTP.

Wiring: app.workers.celery_worker.celery picks this up via the include=
list (added below in celery_worker.py).
"""
from __future__ import annotations

import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage
from io import BytesIO
from pathlib import Path

from openpyxl import Workbook

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import AuditLog, FileImport, Order, Redelivery
from app.workers.celery_worker import celery

log = get_logger(__name__)

EXPORT_COLUMNS = [
    "redelivery_id", "order_id", "user_phone",
    "address_line1", "city", "state", "pincode",
    "preferred_date", "preferred_time_slot",
    "courier_partner", "original_awb", "scheduled_at",
]


@celery.task(name="rto.daily_redelivery_export")
def daily_redelivery_export() -> dict:
    """Run nightly. Returns a summary dict (also logged + audit-logged)."""
    db = SessionLocal()
    try:
        rows = (
            db.query(Redelivery, Order)
            .outerjoin(Order, Order.order_id == Redelivery.order_id)
            .filter(Redelivery.delivery_status == "SCHEDULED")
            .filter(Redelivery.exported_to_excel.is_(False))
            .all()
        )

        if not rows:
            log.info("daily export: nothing to export")
            return {"status": "noop", "exported": 0, "file": None}

        # Build workbook
        wb = Workbook()
        ws = wb.active
        ws.title = "Redeliveries"
        ws.append(EXPORT_COLUMNS)
        ids: list[int] = []
        for rd, order in rows:
            ws.append([
                rd.redelivery_id,
                rd.order_id,
                order.user_phone if order else None,
                rd.delivery_address_line1 or (order.address_line1 if order else None),
                rd.delivery_city or (order.city if order else None),
                rd.delivery_state or (order.state if order else None),
                rd.delivery_pincode or (order.pincode if order else None),
                rd.preferred_date.isoformat() if rd.preferred_date else None,
                rd.preferred_time_slot,
                rd.courier_partner,
                order.awb_number if order else None,
                rd.created_at.isoformat() if rd.created_at else None,
            ])
            ids.append(rd.redelivery_id)

        # Persist to disk
        out_dir = Path(settings.EXCEL_EXPORT_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.utcnow().strftime("%Y%m%d")
        file_path = out_dir / f"redeliveries_{stamp}.xlsx"
        wb.save(file_path)
        log.info("daily export: wrote %d rows to %s", len(ids), file_path)

        # Mark exported
        for rd, _ in rows:
            rd.exported_to_excel = True
            rd.excel_export_at = datetime.utcnow()
            rd.excel_file_name = file_path.name

        # Audit
        db.add(AuditLog(
            event_type="EXCEL_EXPORT_DAILY",
            description=f"file={file_path.name} redeliveries={len(ids)}",
            source="excel_export",
        ))
        db.add(FileImport(
            file_name=file_path.name,
            file_type="xlsx",
            file_size_bytes=file_path.stat().st_size,
            storage_path=str(file_path),
            uploaded_by="celery_beat",
            rows_total=len(ids),
            rows_imported=len(ids),
            status="completed",
            completed_at=datetime.utcnow(),
        ))
        db.commit()

        # Email (optional)
        emailed = False
        if settings.EXCEL_EXPORT_EMAIL and settings.SMTP_HOST:
            try:
                _email_file(file_path)
                emailed = True
                log.info("daily export: emailed %s to %s", file_path.name, settings.EXCEL_EXPORT_EMAIL)
            except Exception:  # noqa: BLE001
                log.exception("daily export: email failed (file still saved)")

        return {
            "status": "ok",
            "exported": len(ids),
            "file": str(file_path),
            "emailed": emailed,
        }
    finally:
        db.close()


def _email_file(path: Path) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"Redelivery export — {path.name}"
    msg["From"] = settings.SMTP_FROM
    msg["To"] = settings.EXCEL_EXPORT_EMAIL
    msg.set_content(
        f"Daily redelivery export attached: {path.name}\n\n"
        "Please process via your courier dashboard."
    )
    with path.open("rb") as f:
        msg.add_attachment(
            f.read(),
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename=path.name,
        )

    ctx = ssl.create_default_context()
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
        s.starttls(context=ctx)
        if settings.SMTP_USER:
            s.login(settings.SMTP_USER, settings.SMTP_PASS)
        s.send_message(msg)
