import pytest

import agents.orchestrator as orchestrator
import agents.report_store as report_store
from tests.fakes import FakeDecision, FakeLLM, FakeOpenObserve

REPLIES = [
    "resumo de logs",
    "resumo de métricas",
    "resumo de traces",
    "1. ZeroDivisionError em pricing.py — confiança: alta — evidência: logs",
    "VEREDITO: SUPORTADO\nNOTAS: o log cita a exceção.",
    "CAUSA: divisão por zero no cupom\nACAO: corrigir pricing.py",
]


def _node_name(system):
    text = system or ""
    # O resumo simples cita "especialista em logs" ao proibir esse nome.
    # Essa frase tem de ser testada antes das outras.
    if "NÃO são de TI" in text:
        return "plain_summary"
    if "verificador final" in text:
        return "verifier"
    if "consolida evidências" in text:
        return "diagnosis"
    if "especialista em logs" in text:
        return "logs"
    if "especialista em métricas" in text:
        return "metrics"
    if "especialista em traces" in text:
        return "traces"
    raise AssertionError(system)


def _install(monkeypatch, client, llm, decision, calls):
    original_report = orchestrator.report_node

    def report_node(state):
        calls.append("report")
        return original_report(state)

    real_generate = llm.generate

    def generate(prompt, **kwargs):
        calls.append(_node_name(kwargs.get("system")))
        return real_generate(prompt, **kwargs)

    llm.generate = generate
    monkeypatch.setattr(orchestrator, "get_provider", lambda: llm)
    monkeypatch.setattr(orchestrator, "OpenObserveClient", lambda: client)
    monkeypatch.setattr(orchestrator, "DecisionProvider", lambda: decision)
    monkeypatch.setattr(orchestrator, "report_node", report_node)


def test_run_investigation_walks_the_graph_and_stores_done(monkeypatch):
    calls = []
    client = FakeOpenObserve(logs=[{
        "exception_type": "ZeroDivisionError",
        "exception_message": "division by zero",
        "exception_stacktrace": "File pricing.py",
        "code_file_path": "pricing.py",
        "code_function_name": "calcular_economia",
        "code_line_number": 42,
    }])
    llm = FakeLLM(replies=list(REPLIES))
    decision = FakeDecision(value=0.81)
    _install(monkeypatch, client, llm, decision, calls)

    record = orchestrator.run_investigation(
        "não consegui aplicar o cupom",
        service="shop-api",
        investigation_id="inv-ok",
    )

    assert calls == ["logs", "metrics", "traces", "diagnosis", "verifier", "plain_summary", "report"]
    assert [name for name, _ in client.queries] == ["logs", "metrics", "traces"]
    assert client.queries[0][1]["service"] == "shop-api"
    assert record["status"] == "done"
    assert record["verified"] is True
    assert "ZeroDivisionError" in record["hypotheses"]
    assert "pricing.py" in record["fix_prompt"]
    assert "divisão por zero no cupom" in record["report"]
    assert report_store.load("inv-ok")["status"] == "done"
    assert decision.calls


def test_empty_service_is_omitted_from_the_initial_state(monkeypatch):
    client = FakeOpenObserve()
    llm = FakeLLM(replies=list(REPLIES))
    _install(monkeypatch, client, llm, FakeDecision(), [])

    orchestrator.run_investigation("relato", service="", investigation_id="inv-all")

    for _, kwargs in client.queries:
        assert kwargs["service"] is None


def test_mid_graph_error_is_stored_and_reraised(monkeypatch):
    client = FakeOpenObserve(traces_error=RuntimeError("traces down"))
    llm = FakeLLM(replies=list(REPLIES))
    _install(monkeypatch, client, llm, FakeDecision(), [])

    with pytest.raises(RuntimeError, match="traces down"):
        orchestrator.run_investigation("relato", service="shop-api", investigation_id="inv-err")

    saved = report_store.load("inv-err")
    assert saved["status"] == "error"
    assert "traces down" in saved["error"]
