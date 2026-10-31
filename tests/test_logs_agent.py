import pytest

from agents.specialists import logs_agent
from tests.fakes import FakeLLM, FakeOpenObserve


def test_query_uses_service_trace_and_window():
    llm = FakeLLM(replies=["exceção no pricing"])
    client = FakeOpenObserve(logs=[{"severity": "ERROR", "body": "boom"}])

    state = logs_agent.run(
        {
            "error_report": "cupom",
            "service": "shop-api",
            "trace_id": "tid",
            "start_time": 5,
            "end_time": 8,
        },
        llm,
        client,
    )

    _, kwargs = client.queries[0]
    assert kwargs["service"] == "shop-api"
    assert kwargs["trace_id"] == "tid"
    assert kwargs["start_time"] == 5
    assert kwargs["end_time"] == 8
    assert kwargs["severities"] == ["ERROR", "WARNING", "WARN"]
    assert state["evidence_logs"] == [{"severity": "ERROR", "body": "boom"}]
    assert state["logs_summary"] == "exceção no pricing"
    assert "cupom" in llm.prompts[0]


def test_query_error_propagates():
    llm = FakeLLM(replies=["não deve rodar"])
    client = FakeOpenObserve(logs_error=RuntimeError("openobserve down"))

    with pytest.raises(RuntimeError, match="openobserve down"):
        logs_agent.run({}, llm, client)

    assert llm.prompts == []
