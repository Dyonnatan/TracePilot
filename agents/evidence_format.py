"""Formatação de evidências brutas (OpenObserve) em texto compacto para
prompt — compartilhado pelos três agentes especialistas. Mantém o LLM
grounded no dado real, sem repassar o JSON bruto inteiro (caro em tokens,
ruim para modelos pequenos).
"""

MAX_RECORDS = 10
MAX_FIELD_CHARS = 400


def _truncate(value, limit: int = MAX_FIELD_CHARS) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "… (truncado)"


def format_logs(logs: list[dict]) -> str:
    if not logs:
        return "(nenhum log encontrado para o filtro/período)"
    lines = []
    for rec in logs[:MAX_RECORDS]:
        lines.append(
            f"- [{rec.get('severity', '?')}] {_truncate(rec.get('body', ''))}"
            f" (trace_id={rec.get('trace_id', '?')}, exception={rec.get('exception_type', '-')})"
        )
    return "\n".join(lines)


def format_traces(traces: list[dict]) -> str:
    if not traces:
        return "(nenhum span encontrado para o filtro/período)"
    lines = []
    for rec in traces[:MAX_RECORDS]:
        exc = ""
        if rec.get("span_status") == "ERROR" and rec.get("events") and "exception" in str(rec.get("events")):
            exc = f" events={_truncate(rec.get('events'))}"
        lines.append(
            f"- {rec.get('operation_name', '?')} status={rec.get('span_status', '?')}"
            f" http_status={rec.get('http_status_code', '-')} duration_ns={rec.get('duration', '-')}"
            f" trace_id={rec.get('trace_id', '?')}{exc}"
        )
    return "\n".join(lines)


def format_metrics(metrics: list[dict]) -> str:
    if not metrics:
        return "(nenhuma métrica encontrada para o filtro/período)"
    lines = []
    for rec in metrics[:MAX_RECORDS]:
        lines.append(f"- {_truncate(rec)}")
    return "\n".join(lines)
