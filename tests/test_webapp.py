import threading

import pytest
from fastapi.testclient import TestClient

import agents.report_store as report_store
import webapp.main as webapp


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(webapp, "_demo_app_status", lambda: {"up": False, "url": "http://demo.test"})
    monkeypatch.setattr(webapp, "_openobserve_status", lambda: {"up": False, "streams": [], "url": "http://oo.test"})
    return TestClient(webapp.app)


def _done_record():
    return {
        "id": "done1",
        "status": "done",
        "created_at": 2,
        "error_report": "cupom quebrado",
        "verified": True,
        "plain_cause": "divisão por zero no cupom",
        "plain_actions": ["corrigir pricing.py"],
        "fix_prompt": "CORRIJA pricing.py",
        "hypotheses": "ZeroDivisionError",
        "verification_notes": "suportado",
        "logs_summary": "log sum",
        "metrics_summary": "met sum",
        "traces_summary": "tr sum",
        "evidence_logs": [],
        "evidence_metrics": [],
        "evidence_traces": [],
        "decision_model_confidence": 0.81,
        "report": "# Relatório",
    }


def test_health_reflects_up_and_down(monkeypatch):
    monkeypatch.setattr(webapp, "_demo_app_status", lambda: {"up": True, "url": "http://demo.test"})
    monkeypatch.setattr(
        webapp,
        "_openobserve_status",
        lambda: {"up": True, "streams": [{"name": "default", "type": "logs", "doc_count": 3}], "url": "http://oo.test"},
    )
    client = TestClient(webapp.app)
    body = client.get("/api/health").json()
    assert body["demo_app"]["up"] is True
    assert body["openobserve"]["streams"][0]["doc_count"] == 3

    monkeypatch.setattr(webapp, "_demo_app_status", lambda: {"up": False, "url": "http://demo.test"})
    monkeypatch.setattr(webapp, "_openobserve_status", lambda: {"up": False, "streams": [], "url": "http://oo.test"})
    body = client.get("/api/health").json()
    assert body["demo_app"]["up"] is False
    assert body["openobserve"]["up"] is False


def test_dashboard_renders_running_and_done(client):
    report_store.save("run1", {
        "id": "run1",
        "status": "running",
        "created_at": 1,
        "error_report": "ainda roda",
    })
    report_store.save("done1", _done_record())

    html = client.get("/").text

    assert "ainda roda" in html
    assert "rodando" in html
    assert "cupom quebrado" in html
    assert "sustentado" in html


def test_detail_renders_running_and_done(client):
    report_store.save("run1", {
        "id": "run1",
        "status": "running",
        "created_at": 1,
        "error_report": "não fechou o pedido",
    })
    running = client.get("/investigations/run1").text
    assert "Investigando" in running
    assert "não fechou o pedido" in running

    report_store.save("done1", _done_record())
    done = client.get("/investigations/done1").text
    assert "Causa encontrada" in done
    assert "divisão por zero no cupom" in done
    assert "Ver detalhes técnicos" in done
    assert "Copiar" in done
    assert "CORRIJA pricing.py" in done
    assert "ZeroDivisionError" in done
    assert "81%" in done


def test_investigation_api_returns_record_or_not_found(client):
    report_store.save("abc", {"id": "abc", "status": "done", "created_at": 1})

    assert client.get("/api/investigations/abc").json()["status"] == "done"
    assert client.get("/api/investigations/missing").json() == {"status": "not_found"}


def test_post_redirects_and_passes_service(client, monkeypatch):
    seen = {}
    gate = threading.Event()

    def fake_run(**kwargs):
        seen.update(kwargs)
        gate.set()

    monkeypatch.setattr(webapp, "run_investigation", fake_run)
    response = client.post(
        "/investigations",
        data={"error_report": "cupom", "service": "shop-api"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert gate.wait(5)
    assert seen["error_report"] == "cupom"
    assert seen["service"] == "shop-api"
    assert seen["investigation_id"] in response.headers["location"]


def test_blank_service_becomes_none(client, monkeypatch):
    seen = {}
    gate = threading.Event()

    def fake_run(**kwargs):
        seen.update(kwargs)
        gate.set()

    monkeypatch.setattr(webapp, "run_investigation", fake_run)
    response = client.post(
        "/investigations",
        data={"error_report": "x", "service": ""},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert gate.wait(5)
    assert seen["service"] is None
