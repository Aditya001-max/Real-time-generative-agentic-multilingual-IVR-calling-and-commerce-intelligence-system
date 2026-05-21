"""Ticket subsystem with provider chain (Chatwoot OSS → generic HTTP → local-only)."""
from app.services.tickets.base import TicketRequest, TicketResult
from app.services.tickets.chain import TicketChain, tickets

__all__ = ["TicketChain", "tickets", "TicketRequest", "TicketResult"]
