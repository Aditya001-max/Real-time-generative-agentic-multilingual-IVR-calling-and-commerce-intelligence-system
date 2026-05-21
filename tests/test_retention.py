"""Unit tests for app/services/retention.py against an in-memory SQLite DB."""
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
import app.models  # noqa: F401 -- register tables
from app.models import Order, User
from app.services.retention import recompute_retention_score


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed(db, phone: str, statuses: list[str]) -> None:
    db.add(User(phone_number=phone))
    db.flush()
    for i, s in enumerate(statuses):
        db.add(Order(
            order_id=hash((phone, i)) % 10**8,
            user_phone=phone,
            oms_status=s,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        ))
    db.commit()


def test_no_orders_yields_zero(db):
    db.add(User(phone_number="+910000000001"))
    db.commit()
    assert recompute_retention_score(db, "+910000000001") == 0.0


def test_all_confirmed_yields_one(db):
    _seed(db, "+910000000002", ["CONFIRMED", "CONFIRMED", "CONFIRMED"])
    assert recompute_retention_score(db, "+910000000002") == 1.0


def test_four_of_five_confirmed_yields_0_8(db):
    _seed(db, "+910000000003", ["CONFIRMED"] * 4 + ["CANCELLED"])
    assert recompute_retention_score(db, "+910000000003") == 0.8


def test_redelivered_counts_positive(db):
    _seed(db, "+910000000004", ["REDELIVERED", "RE_ATTEMPT_DELIVERY", "CANCELLED"])
    # 2 positive of 3 counting = 0.667
    assert recompute_retention_score(db, "+910000000004") == 0.667


def test_score_persisted_on_user(db):
    _seed(db, "+910000000005", ["CONFIRMED", "CANCELLED"])
    score = recompute_retention_score(db, "+910000000005")
    user = db.query(User).filter(User.phone_number == "+910000000005").first()
    assert float(user.retention_score) == score == 0.5


def test_unknown_phone_returns_zero(db):
    assert recompute_retention_score(db, "+910000000099") == 0.0


def test_blank_phone_safe(db):
    assert recompute_retention_score(db, "") == 0.0
