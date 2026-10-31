from agents.evidence_format import MAX_FIELD_CHARS, MAX_RECORDS, format_logs, format_metrics, format_traces


def test_empty_evidence_messages():
    assert format_logs([]) == "(nenhum log encontrado para o filtro/período)"
    assert format_traces([]) == "(nenhum span encontrado para o filtro/período)"
    assert format_metrics([]) == "(nenhuma métrica encontrada para o filtro/período)"


def test_logs_truncate_fields_and_drop_records_past_the_limit():
    long_body = "A" * (MAX_FIELD_CHARS + 1)
    logs = [{"severity": "ERROR", "body": long_body, "trace_id": "t", "exception_type": "E"}]
    logs += [{"severity": "INFO", "body": f"rec-{i:02d}", "trace_id": str(i)} for i in range(MAX_RECORDS)]

    text = format_logs(logs)

    assert "A" * (MAX_FIELD_CHARS + 1) not in text
    assert "A" * MAX_FIELD_CHARS in text
    assert "… (truncado)" in text
    assert text.count("\n") + 1 == MAX_RECORDS
    assert "rec-09" not in text


def test_traces_include_exception_events_and_metrics_truncate():
    traces = [{
        "operation_name": "POST /cart/quote",
        "span_status": "ERROR",
        "events": "exception.type=ZeroDivisionError",
        "http_status_code": 500,
        "duration": 12,
        "trace_id": "tid",
    }]
    text = format_traces(traces)
    assert "POST /cart/quote" in text
    assert "events=" in text
    assert "ZeroDivisionError" in text

    blob = {"value": "M" * (MAX_FIELD_CHARS + 5)}
    metrics = format_metrics([blob])
    assert "M" * (MAX_FIELD_CHARS + 5) not in metrics
    assert "… (truncado)" in metrics
