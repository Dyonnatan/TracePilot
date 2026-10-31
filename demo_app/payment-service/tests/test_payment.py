import random

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    with TestClient(main.app) as test_client:
        yield test_client
    main.faults.clear()


def authorize(client, order_ref="ORD-1"):
    return client.post("/authorize", json={"order_ref": order_ref, "amount_cents": 1000})


def test_acquirer_failure_returns_configured_status(client):
    response = client.post("/internal/faults/acquirer_failure", json={"enabled": True, "config": {"rate": 1, "status": 503}})
    assert response.json() == {"name": "acquirer_failure", "enabled": True, "config": {"rate": 1, "status": 503}}
    response = authorize(client)
    assert response.status_code == 503
    assert response.json() == {"detail": "adquirente indisponível"}

    client.post("/internal/faults/acquirer_failure", json={"enabled": False})
    assert authorize(client).status_code == 200


def test_acquirer_failure_hits_a_share_of_calls(client, monkeypatch):
    monkeypatch.setattr(main, "fault_rng", random.Random(42))
    client.post("/internal/faults/acquirer_failure", json={"enabled": True, "config": {"rate": 0.3}})
    failures = sum(authorize(client, f"ORD-{i}").status_code == 503 for i in range(200))
    assert 40 <= failures <= 80


def test_unknown_fault_is_rejected(client):
    assert client.post("/internal/faults/nope", json={"enabled": True}).status_code == 404
    assert client.get("/internal/faults").json() == [{"name": "acquirer_failure", "enabled": False, "config": {}}]


def test_authorize(client):
    response = client.post("/authorize", json={"order_ref": "ORD-1", "amount_cents": 1000})
    assert response.status_code == 200
    body = response.json()
    assert body["authorized"] is True
    assert body["authorization_id"].startswith("AUTH-")


def test_fraud_score_is_deterministic():
    assert main.fraud_score("ORD-1", 1000) == main.fraud_score("ORD-1", 1000)


def test_authorize_rejects_non_positive_amount(client):
    assert client.post("/authorize", json={"order_ref": "ORD-1", "amount_cents": 0}).status_code == 422


def test_cpu_burn_toggle(client):
    response = client.post("/internal/cpu-burn", json={"enabled": True, "workers": 1})
    assert response.json() == {"enabled": True, "workers": 1}

    response = client.post("/internal/cpu-burn", json={"enabled": False})
    assert response.json() == {"enabled": False, "workers": 0}
    assert client.get("/internal/cpu-burn").json() == {"enabled": False, "workers": 0}
