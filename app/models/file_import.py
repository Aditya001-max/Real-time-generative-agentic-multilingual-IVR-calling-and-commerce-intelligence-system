"""FileImport DB — audit log of every Excel/CSV upload.

Block 10 addition. Tracks every Excel/CSV upload of RTO orders for
debugging and compliance. Logs row counts and any per-row errors.
"""
from datetime import datetime

from sqlalchemy import JSON, BigInteger, Column, DateTime, Integer, String, Text

from app.db.session import Base


class FileImport(Base):
    __tablename__ = "file_imports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    file_name = Column(Text, nullable=False)
    file_type = Column(String(8))  # 'xlsx' | 'csv'
    file_size_bytes = Column(BigInteger)
    storage_path = Column(Text)
    uploaded_by = Column(String(64))

    rows_total = Column(Integer)
    rows_imported = Column(Integer, default=0)
    rows_skipped = Column(Integer, default=0)
    rows_failed = Column(Integer, default=0)

    status = Column(String(16), default="processing")  # processing | completed | failed
    error_log = Column(JSON)

    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime)
