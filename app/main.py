"""Minimal tracking endpoint used as the target for the regression test suite."""
from datetime import datetime

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


@app.post("/track", status_code=status.HTTP_201_CREATED)
def track_event(event: TrackingEvent) -> dict:
    if event.event_id in _seen_event_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Duplicate event_id: {event.event_id}",
        )
    _seen_event_ids.add(event.event_id)
    return {"status": "accepted", "event_id": event.event_id}
