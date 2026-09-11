# tracking-regression-tests

An automated regression test suite for server-side conversion tracking, built
against a small reference tracking endpoint. The goal is to catch the class
of bugs that commonly break real tracking pipelines — malformed payloads,
missing required fields, duplicate event delivery, and consent violations —
before they reach production.

## What's here

- **`app/main.py`** — a minimal `POST /track` endpoint (FastAPI) that stands
  in for a real conversion-tracking server. It validates incoming events,
  enforces consent, and rejects duplicate `event_id`s.
- **`tests/`** — a pytest suite that fires synthetic requests at the endpoint
  and asserts on the responses.
- **`.github/workflows/test.yml`** — runs the suite automatically on every
  pull request into `main`.

## The `/track` endpoint

Accepts a JSON body:

```json
{
  "event_id": "evt-001",
  "event_type": "purchase",
  "timestamp": "2026-09-11T12:00:00Z",
  "consent": "granted"
}
```

- `201 Created` — event accepted.
- `422 Unprocessable Entity` — payload is missing a required field, a field
  has the wrong type, or a value fails validation (e.g. an unparseable
  timestamp, or a `consent` value other than `"granted"`/`"denied"`).
- `403 Forbidden` — `consent` is `"denied"` or missing entirely. Only
  `consent: "granted"` events proceed to dedup and get accepted.
- `409 Conflict` — an event with the same `event_id` was already accepted.

### Consent handling

`consent` is checked immediately after schema validation and **before** the
dedup check, and an event that fails the consent check is never recorded
into the dedup store. Two things fall out of that ordering:

- An event rejected for lack of consent doesn't block a later, legitimately
  consented retry with the same `event_id` — it was never marked as seen.
- If a resent request happens to be both a duplicate and consent-denied, it
  gets `403`, not `409`. Consent is treated as taking priority: a request
  that itself declares no consent shouldn't get a `409` back, since that
  would confirm the event_id was already tracked, regardless of the fact it
  was also a dup.

An invalid `consent` value (anything other than `"granted"`/`"denied"`) is
treated as a schema error (`422`) rather than a policy rejection (`403`),
since it's malformed input rather than a real consent decision.

### Why FastAPI over Flask

The whole point of this project is asserting validation behavior, so the
framework's validation story matters more than usual. FastAPI uses Pydantic
models to validate request bodies automatically: a missing field, wrong
type, or bad value produces a structured `422` response with no extra code.
Flask doesn't validate request bodies out of the box — getting the same
behavior would mean hand-writing field checks (or bolting on a separate
library like Marshmallow), and it's easy for that hand-rolled validation to
drift from what the tests expect. FastAPI's validation is declared once, in
the `TrackingEvent` model, and both the endpoint and the test suite trust it.

### How deduplication works

Deduplication is deliberately simple: an in-memory `set` of `event_id`s seen
by the running process. A second request with an `event_id` already in the
set is rejected with `409 Conflict`, regardless of whether the rest of the
payload matches — a retried or replayed request is exactly the real-world
case this is meant to catch, and it often arrives with a slightly different
timestamp or payload, not an identical one.

This is intentionally the simplest implementation that can be correct for a
single process, and it's a reasonable fit for a reference server used only
in tests. It is **not** what you'd want in production: the set is
per-process and in-memory, so it doesn't survive a restart and doesn't work
across multiple server instances behind a load balancer. A real system would
back this with a shared, persistent store (e.g. Redis with a TTL, or a
unique constraint in a database) so dedup holds across restarts and scales
horizontally.

## Running locally

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the server:

```bash
uvicorn app.main:app --reload
```

Try it with curl:

```bash
curl -X POST http://localhost:8000/track \
  -H "Content-Type: application/json" \
  -d '{"event_id": "evt-001", "event_type": "purchase", "timestamp": "2026-09-11T12:00:00Z", "consent": "granted"}'

# Send it again to see the dedup check kick in:
curl -X POST http://localhost:8000/track \
  -H "Content-Type: application/json" \
  -d '{"event_id": "evt-001", "event_type": "purchase", "timestamp": "2026-09-11T12:00:00Z", "consent": "granted"}'
```

## Running the tests

```bash
pytest -v
```

The tests use FastAPI's `TestClient`, so they call the app directly in-process
— no server needs to be running first. Each test gets a fresh dedup store via
a fixture in `tests/conftest.py`, so tests don't leak duplicate-event state
into each other.

### Coverage

```bash
pytest --cov=app --cov-report=term-missing
```

`pytest-cov` reports coverage scoped to `app/` only (see
`[tool.coverage.run]` in `pyproject.toml`) — coverage of the test files
themselves isn't meaningful signal here.

## CI

`.github/workflows/test.yml` installs dependencies and runs `pytest` with
coverage on every pull request targeting `main`, so a regression in
validation, consent, or deduplication behavior fails the PR check instead of
reaching production. The coverage percentage is printed as part of the test
step's output in the workflow log.
