"""
Block 3 — Decision Engine.

Responsibilities (per architecture diagram):
  • Identify event type
  • Select call flow
  • Check user status
  • Working hours check
"""
from dataclasses import dataclass
from typing import Literal

from app.core.logging import get_logger
from app.core.working_hours import is_working_hours

log = get_logger(__name__)

CallType = Literal["CONFIRMATION", "REJECTION"]


@dataclass
class Decision:
    call_type: CallType
    is_within_working_hours: bool
    proceed: bool
    reason: str


_EVENT_TO_CALL: dict[str, CallType] = {
    "ORDER_PLACED": "CONFIRMATION",
    "ORDER_REJECTED": "REJECTION",
}


def decide(event_type: str) -> Decision:
    """Map an event into a call flow + context flags."""
    call_type = _EVENT_TO_CALL.get(event_type)
    if call_type is None:
        return Decision(
            call_type="CONFIRMATION",
            is_within_working_hours=False,
            proceed=False,
            reason=f"Unknown event_type={event_type!r}",
        )

    in_hours = is_working_hours()
    log.info("decision: event=%s -> %s, working_hours=%s", event_type, call_type, in_hours)

    # We still place calls outside working hours; the IVR will just route
    # 'Need Help' to ticket creation instead of agent connect.
    return Decision(
        call_type=call_type,
        is_within_working_hours=in_hours,
        proceed=True,
        reason="ok",
    )
