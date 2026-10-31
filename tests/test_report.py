from agents.report import build_report


def test_report_includes_plain_summary_actions_and_fix_prompt():
    text = build_report({
        "verified": True,
        "plain_cause": "divisão por zero no cupom",
        "plain_actions": ["corrigir pricing.py"],
        "fix_prompt": "PROMPT-FIX",
        "error_report": "não apliquei o cupom",
        "hypotheses": "ZeroDivisionError",
        "logs_summary": "log do pricing",
        "metrics_summary": "sem métrica",
        "traces_summary": "span de quote",
        "verification_notes": "VEREDITO: SUPORTADO",
        "decision_model_confidence": 0.5,
    })

    assert "divisão por zero no cupom" in text
    assert "corrigir pricing.py" in text
    assert "PROMPT-FIX" in text
    assert "Diagnóstico sustentado por evidência" in text
    assert "50%" in text
    assert "log do pricing" in text


def test_report_marks_insufficient_evidence_and_decision_error():
    text = build_report({
        "verified": False,
        "decision_model_error": "laya fora",
    })

    assert "Evidência insuficiente" in text
    assert "(nenhuma ação sugerida)" in text
    assert "laya fora" in text
    assert "(não gerado)" in text
