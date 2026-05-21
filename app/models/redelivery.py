"""Redelivery DB — fields: redelivery_id, order_id, schedule, courier, export status.

Block 10 addition. Created automatically when call_logs.response = '1'
on a REJECTION call (i.e. customer accepted re-attempt). Holds the
redelivery instructions to push back to the courier via Excel export.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String, Text

from app.db.session import Base


class Redelivery(Base):
    __tablename__ = "redeliveries"

    redelivery_id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, nullable=False, index=True)
    triggered_by_call_id = Column(
        Integer,
        ForeignKey("call_logs.call_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Updated address (if customer requested change during IVR)
    delivery_address_line1 = Column(Text)
    delivery_address_line2 = Column(Text)
    delivery_city = Column(String(64))
    delivery_state = Column(String(64))
    delivery_pincode = Column(String(12))

    # Schedule
    preferred_date = Column(Date)
    preferred_time_slot = Column(String(32))
    scheduled_at = Column(DateTime)

    # Courier
    courier_partner = Column(String(64))
    new_awb_number = Column(String(64))
    pickup_at = Column(DateTime)
    delivered_at = Column(DateTime)
    delivery_status = Column(String(32), default="SCHEDULED", index=True)
    # SCHEDULED | PICKED_UP | IN_TRANSIT | DELIVERED | FAILED
    failure_reason = Column(Text)

    # Excel sync (the "update Excel and database to redeliver" workflow)
    exported_to_excel = Column(Boolean, default=False, index=True)
    excel_export_at = Column(DateTime)
    excel_file_name = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
