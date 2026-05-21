"""Base interface every ticket backend implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TicketRequest:
    order_id: int
    issue_type: str           # NEED_HELP | CANCEL_REQUEST | NO_RESPONSE | OUT_OF_HOURS
    user_phone: str
    description: str
    assigned_to: str | None = None


@dataclass
class TicketResult:
    backend: str
    external_id: str | None   # ID in the external system (None if backend doesn't return one)


class TicketBackend(ABC):
    name: str = "base"

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def create(self, req: TicketRequest) -> TicketResult: ...
