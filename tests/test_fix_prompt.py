from agents.fix_prompt import MAX_STACKTRACE_CHARS, build_fix_prompt


def test_prompt_without_stacktrace_still_includes_the_report():
    text = build_fix_prompt({"error_report": "não consegui aplicar o cupom"})

    assert "não consegui aplicar o cupom" in text
    assert "Serviço: (não informado)" in text
    assert "Stacktrace" not in text
    assert "O que fazer:" in text


def test_prompt_uses_the_first_log_with_stacktrace():
    state = {
        "error_report": "cupom",
        "service": "shop-api",
        "hypotheses": "divisão por zero",
        "evidence_logs": [
            {"body": "sem stack"},
            {
                "exception_type": "ZeroDivisionError",
                "exception_message": "division by zero",
                "code_file_path": "pricing.py",
                "code_function_name": "calcular_economia",
                "code_line_number": 42,
                "exception_stacktrace": "trace-A",
            },
            {"exception_stacktrace": "trace-B", "exception_type": "Outro"},
        ],
    }

    text = build_fix_prompt(state)

    assert "Serviço: shop-api" in text
    assert "divisão por zero" in text
    assert "ZeroDivisionError: division by zero" in text
    assert "pricing.py" in text
    assert "calcular_economia" in text
    assert "linha 42" in text
    assert "trace-A" in text
    assert "trace-B" not in text


def test_stacktrace_is_cut_at_the_limit():
    trace = "Z" * (MAX_STACKTRACE_CHARS + 1)
    text = build_fix_prompt({"evidence_logs": [{"exception_stacktrace": trace}]})

    assert "Z" * MAX_STACKTRACE_CHARS in text
    assert "Z" * (MAX_STACKTRACE_CHARS + 1) not in text
