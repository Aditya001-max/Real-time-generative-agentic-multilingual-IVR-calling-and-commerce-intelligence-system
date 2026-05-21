"""
Block 13 — RTO Recovery & Excel Sync.

Three endpoints that complete the order-recovery loop:

  POST /rto/import             — upload courier Excel of RTO orders
  GET  /rto/redeliveries/export — download Excel of pending redeliveries
  GET  /rto/insights           — extra metrics on top of /analytics/summary

Flow:
  1. Courier sends RTO list as Excel
  2. POST /rto/import populates orders table
  3. /event/ triggers IVR call (existing block 2)
  4. Customer presses 1 on REJECTION call → action_engine creates a
     redeliveries row (and DB trigger does the same on Postgres)
  5. Daily, your team hits /rto/redeliveries/export to get the Excel
     file to send to the courier; rows get marked exported_to_excel=true
"""
from __future__ import annotations

from datetime import datetime
from io import BytesIO

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from openpyxl import Workbook, load_workbook
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.session import get_db
from app.models import FileImport, Order, Redelivery, User

router = APIRouter(prefix="/rto", tags=["rto"])
log = get_logger(__name__)


# =====================================================================
# 1. EXCEL IMPORT — Upload RTO orders from courier dashboard
# =====================================================================
@router.post("/import")
async def import_rto_orders(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """Upload an .xlsx with RTO orders.

    Expected columns (case-insensitive, missing columns are tolerated):
      order_id, user_phone, product_name, sku, quantity, order_value,
      cod_amount, address, city, state, pincode, awb_number,
      courier, rto_reason, rto_date, payment_mode

    Behavior:
      - Upserts a User row keyed by phone (preserves preferred_language)
      - Inserts a new Order row; existing order_ids are skipped (idempotent)
      - Logs row counts and errors to file_imports table
    """
    if not file.filename or not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only .xlsx files supported")

    contents = await file.read()
    fi = FileImport(
        file_name=file.filename,
        file_type="xlsx",
        file_size_bytes=len(contents),
        status="processing",
    )
    db.add(fi)
    db.commit()
    db.refresh(fi)

    try:
        wb = load_workbook(BytesIO(contents), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise ValueError("Empty file")

        headers = [str(h).strip().lower() if h else "" for h in rows[0]]
        idx = {h: i for i, h in enumerate(headers)}

        def cell(row, col, default=None):
            if col not in idx or idx[col] >= len(row):
                return default
            return row[idx[col]]

        imported = skipped = failed = 0
        errors: list[dict] = []

        for r_no, row in enumerate(rows[1:], start=2):
            try:
                order_id = cell(row, "order_id")
                phone = str(cell(row, "user_phone") or "").strip()
                if not order_id or not phone:
                    skipped += 1
                    continue

                # Upsert user (preserves preferred_language across orders)
                user = db.query(User).filter(User.phone_number == phone).first()
                if not user:
                    user = User(phone_number=phone)
                    db.add(user)
                    db.flush()

                # Skip if order already imported (idempotent)
                if db.query(Order).filter(Order.order_id == int(order_id)).first():
                    skipped += 1
                    continue

                rto_date_val = cell(row, "rto_date")
                if isinstance(rto_date_val, datetime):
                    rto_date_val = rto_date_val.date()

                order = Order(
                    order_id=int(order_id),
                    user_phone=phone,
                    user_id=user.user_id,
                    product_name=cell(row, "product_name"),
                    product_sku=cell(row, "sku"),
                    quantity=int(cell(row, "quantity") or 1),
                    order_value=cell(row, "order_value") or 0,
                    cod_amount=cell(row, "cod_amount"),
                    payment_mode=cell(row, "payment_mode") or "COD",
                    address_line1=cell(row, "address"),
                    city=cell(row, "city"),
                    state=cell(row, "state"),
                    pincode=str(cell(row, "pincode") or ""),
                    awb_number=cell(row, "awb_number"),
                    courier_partner=cell(row, "courier"),
                    is_rto=True,
                    rto_reason=cell(row, "rto_reason"),
                    rto_date=rto_date_val,
                    oms_status="RTO_PENDING",
                    source_file=file.filename,
                )
                db.add(order)
                imported += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                errors.append({"row": r_no, "error": str(exc)})

        db.commit()

        fi.rows_total = len(rows) - 1
        fi.rows_imported = imported
        fi.rows_skipped = skipped
        fi.rows_failed = failed
        fi.status = "completed"
        fi.error_log = errors or None
        fi.completed_at = datetime.utcnow()
        db.commit()

        return {
            "import_id": fi.id,
            "file_name": file.filename,
            "imported": imported,
            "skipped": skipped,
            "failed": failed,
            "errors": errors[:10],  # only return first 10 to keep response small
        }
    except Exception as exc:
        log.exception("import failed: %s", exc)
        fi.status = "failed"
        fi.error_log = [{"error": str(exc)}]
        fi.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(500, f"Import failed: {exc}") from exc


# =====================================================================
# 2. EXCEL EXPORT — Pending redeliveries to send to courier
# =====================================================================
@router.get("/redeliveries/export")
def export_pending_redeliveries(db: Session = Depends(get_db)) -> StreamingResponse:
    """Download an .xlsx of all redeliveries waiting to be picked up
    that haven't been exported yet, then mark them as exported."""
    pending = (
        db.query(Redelivery, Order)
        .join(Order, Order.order_id == Redelivery.order_id)
        .filter(Redelivery.exported_to_excel.is_(False))
        .filter(Redelivery.delivery_status == "SCHEDULED")
        .all()
    )
    if not pending:
        raise HTTPException(404, "No pending redeliveries to export")

    wb = Workbook()
    ws = wb.active
    ws.title = "Pending Redeliveries"
    ws.append([
        "redelivery_id", "order_id", "user_phone", "product", "sku", "qty",
        "cod_amount", "address", "city", "state", "pincode",
        "preferred_date", "preferred_slot", "courier", "original_awb",
        "scheduled_at",
    ])

    redelivery_ids: list[int] = []
    for r, o in pending:
        ws.append([
            r.redelivery_id, o.order_id, o.user_phone, o.product_name,
            o.product_sku, o.quantity, float(o.cod_amount or 0),
            r.delivery_address_line1 or o.address_line1,
            r.delivery_city or o.city,
            r.delivery_state or o.state,
            r.delivery_pincode or o.pincode,
            r.preferred_date.isoformat() if r.preferred_date else "",
            r.preferred_time_slot or "",
            r.courier_partner or o.courier_partner or "",
            o.awb_number or "",
            r.created_at.isoformat() if r.created_at else "",
        ])
        redelivery_ids.append(r.redelivery_id)

    file_name = f"redeliveries_{datetime.utcnow():%Y%m%d_%H%M%S}.xlsx"

    # Mark as exported. Use the SQL helper if available (Postgres),
    # else fall back to ORM update (works on SQLite too).
    try:
        db.execute(
            text("SELECT mark_redeliveries_exported(:ids, :name)"),
            {"ids": redelivery_ids, "name": file_name},
        )
    except Exception:  # noqa: BLE001
        # SQLite or Postgres without the helper function — do it via ORM
        now = datetime.utcnow()
        db.query(Redelivery).filter(
            Redelivery.redelivery_id.in_(redelivery_ids)
        ).update(
            {
                "exported_to_excel": True,
                "excel_export_at": now,
                "excel_file_name": file_name,
                "updated_at": now,
            },
            synchronize_session=False,
        )
    db.commit()

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


# =====================================================================
# 3. INSIGHTS — extends /analytics/summary with RTO-specific metrics
# =====================================================================
@router.get("/insights")
def rto_insights(db: Session = Depends(get_db)) -> dict:
    """RTO-specific dashboard metrics.

    Tries Postgres views first (created in the migration). Falls back to
    inline aggregations if those views don't exist (e.g. on SQLite).
    """
    # ----- Call quality breakdown -----
    quality_row = db.execute(text(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN status IN ('ANSWERED','COMPLETED') THEN 1 END) AS working,
            COUNT(CASE WHEN status NOT IN ('ANSWERED','COMPLETED') THEN 1 END) AS non_working,
            COUNT(CASE WHEN response IN ('1','confirm','accept') THEN 1 END) AS beneficial
        FROM call_logs
        """
    )).mappings().first()

    # ----- RTO funnel -----
    rto_row = db.execute(text(
        """
        SELECT
            COUNT(CASE WHEN is_rto = 1 OR is_rto = TRUE THEN 1 END) AS rto_orders,
            COUNT(CASE WHEN oms_status = 'RE_ATTEMPT_DELIVERY' THEN 1 END) AS recovery_in_progress,
            COUNT(CASE WHEN oms_status = 'REDELIVERED' THEN 1 END) AS recovered,
            COUNT(CASE WHEN oms_status = 'CANCELLED' AND (is_rto = 1 OR is_rto = TRUE) THEN 1 END) AS lost
        FROM orders
        """
    )).mappings().first()

    # ----- Redelivery stats -----
    redel_row = db.execute(text(
        """
        SELECT
            COUNT(*) AS total,
            COUNT(CASE WHEN delivery_status = 'DELIVERED' THEN 1 END) AS delivered,
            COUNT(CASE WHEN delivery_status = 'FAILED' THEN 1 END) AS failed,
            COUNT(CASE WHEN exported_to_excel = 0 OR exported_to_excel = FALSE THEN 1 END) AS pending_export
        FROM redeliveries
        """
    )).mappings().first()

    # ----- Language usage -----
    language_rows = db.execute(text(
        """
        SELECT
            language,
            COUNT(*) AS calls,
            COUNT(CASE WHEN status IN ('ANSWERED','COMPLETED') THEN 1 END) AS answered,
            COUNT(CASE WHEN response = '1' THEN 1 END) AS positive_responses
        FROM call_logs
        WHERE language IS NOT NULL
        GROUP BY language
        ORDER BY calls DESC
        """
    )).mappings().all()

    total = (quality_row or {}).get("total", 0) or 0
    working = (quality_row or {}).get("working", 0) or 0
    beneficial = (quality_row or {}).get("beneficial", 0) or 0

    return {
        "calls": {
            "total": total,
            "working": working,
            "non_working": (quality_row or {}).get("non_working", 0) or 0,
            "beneficial": beneficial,
            "answer_rate": round(100.0 * working / total, 2) if total else 0,
            "beneficial_rate": round(100.0 * beneficial / total, 2) if total else 0,
        },
        "rto_funnel": dict(rto_row) if rto_row else {},
        "redeliveries": dict(redel_row) if redel_row else {},
        "language_usage": [dict(r) for r in language_rows],
    }
