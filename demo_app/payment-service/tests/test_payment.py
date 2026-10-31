import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture
def client():
    with TestClient(main.app) as test_client:
        yield test_client


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
