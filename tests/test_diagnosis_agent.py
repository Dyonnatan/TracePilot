from agents import diagnosis_agent
from tests.fakes import FakeLLM


def test_prompt_receives_the_three_summaries():
    llm = FakeLLM(replies=["1. ZeroDivisionError — confiança: alta — evidência: logs"])

    state = diagnosis_agent.run(
        {
            "error_report": "cupom GRATIS100",
            "logs_summary": "LOGS-X",
            "metrics_summary": "MET-Y",
            "traces_summary": "TR-Z",
        },
        llm,
    )

    assert state["hypotheses"] == "1. ZeroDivisionError — confiança: alta — evidência: logs"
    prompt = llm.prompts[0]
    assert "cupom GRATIS100" in prompt
    assert "LOGS-X" in prompt
    assert "MET-Y" in prompt
    assert "TR-Z" in prompt
