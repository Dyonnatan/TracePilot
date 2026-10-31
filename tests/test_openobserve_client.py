import httpx

from agents.tools.openobserve_client import OpenObserveClient


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _install(monkeypatch, hits=None):
    captured = {}

    def fake_post(url, params=None, json=None, headers=None, auth=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["json"] = json
        captured["headers"] = headers
        return _Response({"hits": [{"body": "boom"}] if hits is None else hits})

    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenObserveClient(base_url="http://oo.test", org="acme", token="tok")
    return client, captured


def _sql(captured):
    return captured["json"]["query"]["sql"]


def test_query_logs_filters_escape_and_hits(monkeypatch):
    client, captured = _install(monkeypatch, hits=[{"body": "erro"}])
    hits = client.query_logs(
        query_text="o'hara",
        severities=["ERROR", "WARNING"],
        service="shop'api",
        trace_id="abc",
        start_time=10,
        end_time=20,
        size=7,
    )

    assert hits == [{"body": "erro"}]
    assert captured["url"] == "http://oo.test/api/acme/_search"
    assert captured["params"] == {"type": "logs"}
    assert captured["headers"]["Authorization"] == "Bearer tok"
    sql = _sql(captured)
    assert "body ILIKE '%o''hara%'" in sql
    assert "exception_type ILIKE '%o''hara%'" in sql
    assert "exception_message ILIKE '%o''hara%'" in sql
    assert "severity IN ('ERROR', 'WARNING')" in sql
    assert "service_name = 'shop''api'" in sql
    assert "trace_id = 'abc'" in sql
    assert 'FROM "default"' in sql
    assert captured["json"]["query"]["start_time"] == 10
    assert captured["json"]["query"]["end_time"] == 20
    assert captured["json"]["query"]["size"] == 7


def test_query_logs_open_window_is_microseconds(monkeypatch):
    monkeypatch.setattr("agents.tools.openobserve_client.time.time", lambda: 1_700_000_000)
    client, captured = _install(monkeypatch)
    client.query_logs()

    end_us = 1_700_000_000 * 1_000_000
    start_us = end_us - 60 * 60 * 1_000_000
    assert captured["json"]["query"]["end_time"] == end_us
    assert captured["json"]["query"]["start_time"] == start_us
    assert "WHERE 1=1" in _sql(captured)


def test_query_traces_only_errors(monkeypatch):
    client, captured = _install(monkeypatch, hits=[{"span_status": "ERROR"}])
    hits = client.query_traces(service="payment-service", only_errors=True, trace_id="tid")

    assert hits == [{"span_status": "ERROR"}]
    assert captured["params"] == {"type": "traces"}
    sql = _sql(captured)
    assert "service_name = 'payment-service'" in sql
    assert "trace_id = 'tid'" in sql
    assert "span_status = 'ERROR'" in sql


def test_query_metrics_stream_and_identifier_escape(monkeypatch):
    client, captured = _install(monkeypatch, hits=[{"value": 3}])
    hits = client.query_metrics(metric_name='shop"checkout', service="shop-api", size=4)

    assert hits == [{"value": 3}]
    assert captured["params"] == {"type": "metrics"}
    sql = _sql(captured)
    assert 'FROM "shop""checkout"' in sql
    assert "service_name = 'shop-api'" in sql
    assert captured["json"]["query"]["size"] == 4
