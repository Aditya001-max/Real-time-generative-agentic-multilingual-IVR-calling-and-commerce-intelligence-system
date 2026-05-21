"""Pydantic schemas for incoming events (block 1 → block 2)."""
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class EventIn(BaseModel):
    """Payload received from external system (REST API or Kafka/RabbitMQ consumer)."""

    order_id: int = Field(..., gt=0)
    user_phone: str = Field(..., min_length=8, max_length=20)
    event_type: Literal["ORDER_PLACED", "ORDER_REJECTED"]
    # Optional ISO 3166-2:IN state code (e.g. GJ, TN, UP). Drives the
    # region-aware language picker. Falls back to all 9 languages if missing.
    state: Optional[str] = Field(None, min_length=2, max_length=2)

    @field_validator("state")
    @classmethod
    def _upper_state(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class EventOut(BaseModel):
    status: str
    call_id: int | None = None
    # Ozonetel KooKoo session ID returned by the outbound API.
    provider_sid: str | None = None
    message: str
