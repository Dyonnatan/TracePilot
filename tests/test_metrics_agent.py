from agents.specialists import metrics_agent
from tests.fakes import FakeLLM, FakeOpenObserve


def test_query_uses_state_and_returns_the_summary():
    llm = FakeLLM(replies=["latência alta"])
    client = FakeOpenObserve(metrics=[{"value": 9}])

    state = metrics_agent.run(
        {
            "error_report": "checkout lento",
            "service": "shop-api",
            "metric_name": "shop_checkout_requests",
            "start_time": 1,
            "end_time": 2,
        },
        llm,
        client,
    )

    kind, kwargs = client.queries[0]
    assert kind == "metrics"
    assert kwargs["metric_name"] == "shop_checkout_requests"
    assert kwargs["service"] == "shop-api"
    assert kwargs["start_time"] == 1
    assert kwargs["end_time"] == 2
    assert state["evidence_metrics"] == [{"value": 9}]
    assert state["metrics_summary"] == "latência alta"
    assert "checkout lento" in llm.prompts[0]


def test_query_error_becomes_empty_evidence_and_llm_still_runs():
    llm = FakeLLM(replies=["sem métricas"])
    client = FakeOpenObserve(metrics_error=RuntimeError("stream ausente"))

    state = metrics_agent.run({"metric_name": "ausente"}, llm, client)

    assert state["evidence_metrics"] == []
    assert state["metrics_summary"] == "sem métricas"
    assert "nenhuma métrica encontrada" in llm.prompts[0]
