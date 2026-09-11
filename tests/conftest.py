import pytest
from fastapi.testclient import TestClient

from app.main import _seen_event_ids, app


@pytest.fixture()
def client():
    """A TestClient with a clean dedup store, so tests don't leak state into each other."""
    _seen_event_ids.clear()
    yield TestClient(app)
    _seen_event_ids.clear()
