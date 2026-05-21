"""Pydantic schemas for /team/* routes."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


TeamOutcome = Literal["accepted", "rejected", "wants_callback", "no_response", "wrong_number"]
NextAction = Literal["create_redelivery", "cancel_order"]


class TeamCallResultIn(BaseModel):
    ticket_id: int = Field(..., gt=0, description="The OPEN help ticket the team called for")
    agent_id: str = Field(..., min_length=1, max_length=64)
    duration_seconds: int = Field(..., ge=0)
    outcome: TeamOutcome
    notes: Optional[str] = None
    # Only meaningful when outcome='accepted' on a REJECTION-flow ticket.
    next_action: Optional[NextAction] = None


class TeamCallResultOut(BaseModel):
    status: str
    team_call_log_id: int
    ticket_status: str
    order_status: Optional[str] = None
    redelivery_id: Optional[int] = None
    retention_score: Optional[float] = None
