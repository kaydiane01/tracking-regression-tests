VALID_EVENT = {
    "event_id": "evt-001",
    "event_type": "purchase",
    "timestamp": "2026-09-11T12:00:00Z",
    "consent": "granted",
}


def test_valid_event_is_accepted(client):
    response = client.post("/track", json=VALID_EVENT)

    assert response.status_code == 201
    assert response.json() == {"status": "accepted", "event_id": "evt-001"}


def test_duplicate_event_id_is_rejected(client):
    first = client.post("/track", json=VALID_EVENT)
    assert first.status_code == 201

    second = client.post("/track", json=VALID_EVENT)

    assert second.status_code == 409
    assert "evt-001" in second.json()["detail"]


def test_duplicate_is_rejected_even_with_different_other_fields(client):
    """The dedup key is event_id alone -- a repeat event_id must be caught
    even if the rest of the payload differs, since that's the real-world
    failure mode (e.g. a retried request with a slightly different timestamp)."""
    client.post("/track", json=VALID_EVENT)

    retried = {**VALID_EVENT, "event_type": "refund", "timestamp": "2026-09-11T12:05:00Z"}
    response = client.post("/track", json=retried)

    assert response.status_code == 409


def test_malformed_timestamp_is_rejected(client):
    bad_event = {**VALID_EVENT, "timestamp": "not-a-timestamp"}

    response = client.post("/track", json=bad_event)

    assert response.status_code == 422
    body = response.json()
    assert any(err["loc"][-1] == "timestamp" for err in body["detail"])


def test_empty_event_id_is_rejected(client):
    bad_event = {**VALID_EVENT, "event_id": ""}

    response = client.post("/track", json=bad_event)

    assert response.status_code == 422


def test_wrong_type_for_event_type_is_rejected(client):
    bad_event = {**VALID_EVENT, "event_type": 12345}

    response = client.post("/track", json=bad_event)

    assert response.status_code == 422


def test_missing_event_id_is_rejected(client):
    bad_event = {k: v for k, v in VALID_EVENT.items() if k != "event_id"}

    response = client.post("/track", json=bad_event)

    assert response.status_code == 422
    body = response.json()
    assert any(err["loc"][-1] == "event_id" for err in body["detail"])


def test_missing_event_type_is_rejected(client):
    bad_event = {k: v for k, v in VALID_EVENT.items() if k != "event_type"}

    response = client.post("/track", json=bad_event)

    assert response.status_code == 422
    body = response.json()
    assert any(err["loc"][-1] == "event_type" for err in body["detail"])


def test_missing_timestamp_is_rejected(client):
    bad_event = {k: v for k, v in VALID_EVENT.items() if k != "timestamp"}

    response = client.post("/track", json=bad_event)

    assert response.status_code == 422
    body = response.json()
    assert any(err["loc"][-1] == "timestamp" for err in body["detail"])


def test_empty_body_is_rejected(client):
    response = client.post("/track", json={})

    assert response.status_code == 422


def test_non_json_body_is_rejected(client):
    response = client.post(
        "/track",
        data="this is not json",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422


def test_granted_consent_is_accepted(client):
    response = client.post("/track", json=VALID_EVENT)

    assert response.status_code == 201


def test_denied_consent_is_rejected(client):
    event = {**VALID_EVENT, "consent": "denied"}

    response = client.post("/track", json=event)

    assert response.status_code == 403


def test_missing_consent_is_rejected(client):
    event = {k: v for k, v in VALID_EVENT.items() if k != "consent"}

    response = client.post("/track", json=event)

    assert response.status_code == 403


def test_invalid_consent_value_is_rejected_as_malformed(client):
    """A value outside "granted"/"denied" is a schema problem (422), distinct
    from the policy rejections (403) for denied or missing consent."""
    event = {**VALID_EVENT, "consent": "maybe"}

    response = client.post("/track", json=event)

    assert response.status_code == 422


def test_denied_consent_does_not_block_a_later_granted_retry(client):
    """An event rejected for lack of consent must not be recorded as seen,
    so a legitimate retry with the same event_id and consent granted still
    succeeds -- consent rejection and dedup are independent checks."""
    denied = {**VALID_EVENT, "consent": "denied"}
    first = client.post("/track", json=denied)
    assert first.status_code == 403

    retry = {**VALID_EVENT, "consent": "granted"}
    second = client.post("/track", json=retry)

    assert second.status_code == 201


def test_duplicate_with_denied_consent_returns_403_not_409(client):
    """Consent takes precedence over dedup: a resend that is both a
    duplicate and consent-denied should not confirm via 409 that the
    event_id was already tracked."""
    client.post("/track", json=VALID_EVENT)

    resend = {**VALID_EVENT, "consent": "denied"}
    response = client.post("/track", json=resend)

    assert response.status_code == 403
