import pytest

from agents.specialists import traces_agent
from tests.fakes import FakeLLM, FakeOpenObserve


def test_query_uses_service_trace_and_window():
    llm = FakeLLM(replies=["erro em quote"])
    client = FakeOpenObserve(traces=[{"operation_name": "POST /cart/quote", "span_status": "ERROR"}])

    state = traces_agent.run(
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
    assert kwargs["only_errors"] is False
    assert state["traces_summary"] == "erro em quote"
    assert "cupom" in llm.prompts[0]


def test_without_trace_id_asks_only_errors():
    client = FakeOpenObserve()
    traces_agent.run({"service": "shop-api"}, FakeLLM(replies=["vazio"]), client)

    assert client.queries[0][1]["only_errors"] is True
    assert client.queries[0][1]["trace_id"] is None


def test_query_error_propagates():
    llm = FakeLLM()
    client = FakeOpenObserve(traces_error=RuntimeError("traces down"))

    with pytest.raises(RuntimeError, match="traces down"):
        traces_agent.run({}, llm, client)

    assert llm.prompts == []
