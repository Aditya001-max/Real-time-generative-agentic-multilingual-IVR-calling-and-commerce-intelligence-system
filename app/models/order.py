"""Order DB — fields: order_id, user_phone, product details, OMS status, RTO info.

Block 10 addition. Stores the e-commerce order data so RTO recovery
insights are possible. Linked to call_logs/users via order_id and user_phone.
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String, Text

from app.db.session import Base


class Order(Base):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True)  # explicit, not autoincrement — matches your shop's order IDs
    user_phone = Column(String(20), nullable=False, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.user_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Order details
    product_name = Column(Text)
    product_sku = Column(String(64))
    quantity = Column(Integer, default=1)
    order_value = Column(Numeric(12, 2), default=0)
    cod_amount = Column(Numeric(12, 2))
    payment_mode = Column(String(32), default="COD")

    # Address (used as default for redelivery if customer didn't change it)
    address_line1 = Column(Text)
    address_line2 = Column(Text)
    city = Column(String(64))
    state = Column(String(64))
    pincode = Column(String(12))

    # OMS lifecycle — strings already used by action_engine.py
    oms_status = Column(String(32), default="PLACED", index=True)
    # PLACED | CONFIRMED | RE_ATTEMPT_DELIVERY | CANCELLED | REDELIVERED | RTO_PENDING

    # RTO tracking
    is_rto = Column(Boolean, default=False)
    rto_reason = Column(Text)
    rto_date = Column(Date)
    awb_number = Column(String(64))
    courier_partner = Column(String(64))

    # Source tracking
    source_file = Column(Text)
    imported_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
