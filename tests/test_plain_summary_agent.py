from agents import plain_summary_agent
from tests.fakes import FakeLLM


def test_parses_cause_and_actions():
    llm = FakeLLM(replies=[
        "CAUSA: divisão por zero no cupom\n"
        "ACAO: corrigir pricing.py\n"
        "ACAO: cobrir o cupom com teste\n"
    ])

    state = plain_summary_agent.run(
        {"hypotheses": "H1 pricing", "verification_notes": "suportado"},
        llm,
    )

    assert state["plain_cause"] == "divisão por zero no cupom"
    assert state["plain_actions"] == ["corrigir pricing.py", "cobrir o cupom com teste"]
    assert "H1 pricing" in llm.prompts[0]
    assert "suportado" in llm.prompts[0]


def test_lowercase_prefixes_and_raw_fallback_cut_at_400():
    llm = FakeLLM(replies=["causa: texto curto\nacao: uma ação"])
    state = plain_summary_agent.run({}, llm)
    assert state["plain_cause"] == "texto curto"
    assert state["plain_actions"] == ["uma ação"]

    raw = "sem prefixo " + ("x" * 500)
    llm = FakeLLM(replies=[raw])
    state = plain_summary_agent.run({}, llm)
    assert state["plain_cause"] == raw.strip()[:400]
    assert len(state["plain_cause"]) == 400
    assert state["plain_actions"] == []
