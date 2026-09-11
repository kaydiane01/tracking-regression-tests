"""Minimal tracking endpoint used as the target for the regression test suite."""
from datetime import datetime
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

app = FastAPI(title="Tracking Regression Test Server")

# In-memory dedup store. A real conversion-tracking backend would back this
# with a persistent, shared store (e.g. Redis/DB) so dedup survives restarts
# and works across multiple server instances; a process-local set is enough
# for a reference server whose only job is to be tested against.
_seen_event_ids: set[str] = set()


class TrackingEvent(BaseModel):
    event_id: str = Field(..., min_length=1)
    event_type: str = Field(..., min_length=1)
    timestamp: datetime
    # Optional (not required) so that a *missing* consent field is a policy
    # rejection (403) we control, not a schema error (422) raised for us.
    # An outright invalid value (e.g. "maybe") still fails schema validation.
    consent: Optional[Literal["granted", "denied"]] = None


@app.post("/track", status_code=status.HTTP_201_CREATED)
def track_event(event: TrackingEvent) -> dict:
    # Consent is checked before dedup, and before the event_id is recorded
    # as seen, so that an event rejected for lack of consent never blocks a
    # later, properly-consented retry with the same event_id -- and so a
    # request that itself declares no consent can't learn from a 409 that
    # this event_id was already tracked.
    if event.consent != "granted":
        detail = "Consent is required" if event.consent is None else "Consent was denied"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)

    if event.event_id in _seen_event_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate event_id: {event.event_id}",
        )
    _seen_event_ids.add(event.event_id)
    return {"status": "accepted", "event_id": event.event_id}
