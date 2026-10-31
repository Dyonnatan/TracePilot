from agents import verifier_agent
from tests.fakes import FakeDecision, FakeLLM


def test_supported_verdict_is_case_insensitive_and_records_confidence():
    llm = FakeLLM(replies=["  veredito: suportado\nNOTAS: o log cita a exceção"])
    decision = FakeDecision(value=0.42)

    state = verifier_agent.run(
        {"hypotheses": "H", "logs_summary": "L", "metrics_summary": "M", "traces_summary": "T"},
        llm,
        decision,
    )

    assert state["verified"] is True
    assert state["verification_notes"].startswith("  veredito:")
    assert state["decision_model_confidence"] == 0.42
    assert len(decision.calls) == 1
    assert "H" in llm.prompts[0]
    assert "L" in llm.prompts[0]


def test_insufficient_verdict():
    llm = FakeLLM(replies=["VEREDITO: INSUFICIENTE\nNOTAS: falta o trace"])
    state = verifier_agent.run({}, llm, FakeDecision())

    assert state["verified"] is False


def test_decision_provider_failure_does_not_abort():
    llm = FakeLLM(replies=["VEREDITO: SUPORTADO\nNOTAS: ok"])
    decision = FakeDecision(error=RuntimeError("laya down"))

    state = verifier_agent.run({}, llm, decision)

    assert state["verified"] is True
    assert state["decision_model_confidence"] is None
    assert state["decision_model_error"] == "laya down"
