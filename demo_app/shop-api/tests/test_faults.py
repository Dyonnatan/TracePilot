import httpx
import pytest

import faults
import payment_client


def test_registry_rejects_unknown_flag():
    with pytest.raises(faults.UnknownFlag):
        faults.FaultRegistry().set("nope", True)


def test_registry_notifies_only_on_change():
    registry = faults.FaultRegistry()
    changes = []
    registry.on_change(lambda name, enabled, config: changes.append((name, enabled, config)))
    registry.set(faults.AUDIT_SYNC_WRITE, True, {"sleep_ms": 10})
    registry.set(faults.AUDIT_SYNC_WRITE, True, {"sleep_ms": 20})
    registry.set(faults.AUDIT_SYNC_WRITE, False)
    assert changes == [(faults.AUDIT_SYNC_WRITE, True, {"sleep_ms": 10}), (faults.AUDIT_SYNC_WRITE, False, {})]
    assert registry.config(faults.AUDIT_SYNC_WRITE) is None


def test_faults_server_toggles_flags():
    registry = faults.FaultRegistry()
    server = faults.start_server(registry, port=0)
    try:
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        response = httpx.post(f"{base_url}/faults/{faults.DEBUG_PAYLOAD_LOGGING}", json={"enabled": True, "config": {"lines": 3}})
        assert response.json() == {"name": faults.DEBUG_PAYLOAD_LOGGING, "enabled": True, "config": {"lines": 3}}
        assert registry.config(faults.DEBUG_PAYLOAD_LOGGING) == {"lines": 3}
        assert httpx.post(f"{base_url}/faults/nope", json={"enabled": True}).status_code == 404
        assert httpx.post(f"{base_url}/faults/{faults.AUDIT_SYNC_WRITE}", json={}).status_code == 400
        assert len(httpx.get(f"{base_url}/faults").json()) == len(faults.KNOWN_FLAGS)
    finally:
        server.shutdown()


class PaymentCalls(list):
    def __init__(self, monkeypatch):
        super().__init__()
        self._monkeypatch = monkeypatch

    def use_status(self, status):
        def handler(request):
            self.append(request.url.path)
            return httpx.Response(status, json={"authorization_id": "AUTH-1"})

        client = httpx.Client(base_url="http://payment", transport=httpx.MockTransport(handler))
        self._monkeypatch.setattr(payment_client, "_client", lambda: client)


@pytest.fixture
def payment_calls(monkeypatch):
    return PaymentCalls(monkeypatch)


def test_authorize_without_flag_does_not_retry(payment_calls):
    payment_calls.use_status(503)
    with pytest.raises(httpx.HTTPStatusError):
        payment_client.authorize("ORD-1", 1000)
    assert len(payment_calls) == 1


def test_retry_no_backoff_repeats_5xx_immediately(payment_calls, monkeypatch):
    sleeps = []
    monkeypatch.setattr(payment_client.time, "sleep", sleeps.append)
    faults.registry.set(faults.PAYMENT_RETRY_NO_BACKOFF, True, {"attempts": 3})
    payment_calls.use_status(503)
    with pytest.raises(httpx.HTTPStatusError):
        payment_client.authorize("ORD-1", 1000)
    assert len(payment_calls) == 3
    assert sleeps == []


def test_retry_no_backoff_does_not_retry_4xx(payment_calls):
    faults.registry.set(faults.PAYMENT_RETRY_NO_BACKOFF, True, {"attempts": 3})
    payment_calls.use_status(422)
    with pytest.raises(httpx.HTTPStatusError):
        payment_client.authorize("ORD-1", 1000)
    assert len(payment_calls) == 1


def test_retry_no_backoff_returns_first_success(payment_calls):
    faults.registry.set(faults.PAYMENT_RETRY_NO_BACKOFF, True)
    payment_calls.use_status(200)
    assert payment_client.authorize("ORD-1", 1000) == {"authorization_id": "AUTH-1"}
    assert len(payment_calls) == 1
