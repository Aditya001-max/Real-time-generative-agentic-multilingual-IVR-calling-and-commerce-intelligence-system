"""Tests for the ticket provider chain — fakes, no real Chatwoot calls."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base
from app.models import Ticket
from app.services.tickets.base import TicketBackend, TicketRequest, TicketResult
from app.services.tickets.chain import TicketChain


class _FakeTicketBackend(TicketBackend):
    def __init__(self, name: str, *, available: bool = True, fail: bool = False) -> None:
        self.name = name
        self._available = available
        self._fail = fail
        self.call_count = 0

    @property
    def available(self) -> bool:
        return self._available

    def create(self, req: TicketRequest) -> TicketResult:
        self.call_count += 1
        if self._fail:
            raise RuntimeError(f"{self.name} boom")
        return TicketResult(backend=self.name, external_id=f"ext-{self.name}-{req.order_id}")


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _chain(*backends: TicketBackend) -> TicketChain:
    c = TicketChain.__new__(TicketChain)
    c._backends = list(backends)
    return c


def _req(order_id: int = 1) -> TicketRequest:
    return TicketRequest(
        order_id=order_id,
        issue_type="NEED_HELP",
        user_phone="+15551111111",
        description="test",
    )


def test_first_available_backend_used(db_session: Session):
    a = _FakeTicketBackend("primary")
    b = _FakeTicketBackend("fallback")
    chain = _chain(a, b)

    ticket = chain.create(db_session, _req())
    assert ticket.external_ticket_id == "ext-primary-1"
    assert a.call_count == 1
    assert b.call_count == 0


def test_failed_backend_falls_through(db_session: Session):
    a = _FakeTicketBackend("primary", fail=True)
    b = _FakeTicketBackend("fallback")
    chain = _chain(a, b)

    ticket = chain.create(db_session, _req())
    assert ticket.external_ticket_id == "ext-fallback-1"
    assert a.call_count == 1
    assert b.call_count == 1


def test_all_backends_fail_still_creates_local_ticket(db_session: Session):
    a = _FakeTicketBackend("primary", fail=True)
    b = _FakeTicketBackend("fallback", fail=True)
    chain = _chain(a, b)

    ticket = chain.create(db_session, _req(order_id=42))
    # Local ticket persists even when every external backend fails.
    assert ticket.ticket_id is not None
    assert ticket.order_id == 42
    assert ticket.external_ticket_id is None  # nobody returned an ID


def test_no_backends_configured_local_only(db_session: Session):
    chain = _chain()  # empty list = no external integrations
    ticket = chain.create(db_session, _req())
    assert ticket.ticket_id is not None
    assert ticket.external_ticket_id is None


def test_unavailable_backend_skipped(db_session: Session):
    a = _FakeTicketBackend("primary", available=False)
    b = _FakeTicketBackend("fallback")
    chain = _chain(a, b)

    ticket = chain.create(db_session, _req())
    assert a.call_count == 0
    assert b.call_count == 1
    assert ticket.external_ticket_id == "ext-fallback-1"


def test_local_ticket_always_persisted(db_session: Session):
    chain = _chain(_FakeTicketBackend("primary"))
    chain.create(db_session, _req())
    chain.create(db_session, _req(order_id=2))

    rows = db_session.query(Ticket).all()
    assert len(rows) == 2
