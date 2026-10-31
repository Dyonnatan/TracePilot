"""Tradução do JSON simples da API de ingestão para OTLP/HTTP (JSON).

Por que traduzir em vez de inventar um formato próprio de armazenamento:
o pipeline do TracePilot (otel-collector → OpenObserve → agentes) já
existe e já foi validado contra dado real. Quem manda dado pela API de
ingestão direta tem que acabar nos *mesmos* streams, com os *mesmos*
nomes de campo que `agents/tools/openobserve_client.py` consulta — senão
o caminho sem instalador viraria um segundo pipeline pela metade.

Detalhe de formato: no OTLP/JSON, `traceId`/`spanId` vão como string
hexadecimal (exceção à regra de bytes-em-base64 do mapeamento JSON do
protobuf) — é assim que o receiver do collector espera.
"""
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

from ingest.schema import Event, IngestRequest

# OTLP severityNumber (spec de logs). O OpenObserve guarda o texto em
# `severity`, que é o que o logs_agent filtra, mas o número é o que dá
# semântica de ordenação pra quem consultar via PromQL/SQL depois.
SEVERITY_NUMBERS = {
    "TRACE": 1,
    "DEBUG": 5,
    "INFO": 9,
    "WARN": 13,
    "WARNING": 13,
    "ERROR": 17,
    "FATAL": 21,
    "CRITICAL": 21,
}

SPAN_STATUS_CODES = {"UNSET": 0, "OK": 1, "ERROR": 2}

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_HEX16 = re.compile(r"^[0-9a-f]{16}$")


class IngestError(ValueError):
    """Evento que não dá pra traduzir — vira 422 com a mensagem."""


def to_unix_nano(value: str | int | float | None) -> int:
    """Normaliza timestamp para nanossegundos Unix.

    Aceita ISO-8601 ou epoch numérico em qualquer unidade usual. A unidade
    é inferida por magnitude porque, na prática, cada linguagem/biblioteca
    entrega uma diferente (`time.time()` em segundos, `Date.now()` em ms,
    `time.time_ns()` em ns) — exigir uma só unidade seria a fonte de erro
    mais provável numa integração escrita por IA.
    """
    if value is None:
        return time.time_ns()
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise IngestError(
                f"timestamp '{value}' não é ISO-8601 nem epoch numérico"
            ) from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1_000_000_000)
    magnitude = abs(float(value))
    if magnitude < 1e11:          # segundos
        return int(float(value) * 1_000_000_000)
    if magnitude < 1e14:          # milissegundos
        return int(float(value) * 1_000_000)
    if magnitude < 1e17:          # microssegundos
        return int(float(value) * 1_000)
    return int(value)             # nanossegundos


def _normalize_id(value: str | None, *, bits: int, field: str) -> str | None:
    if value is None:
        return None
    candidate = value.strip().lower().replace("-", "")
    pattern = _HEX32 if bits == 128 else _HEX16
    if not pattern.match(candidate):
        raise IngestError(
            f"{field} inválido ('{value}'): esperado hexadecimal de "
            f"{bits // 4} caracteres"
        )
    return candidate


def _attr(key: str, value: Any) -> dict:
    """Um KeyValue do OTLP. Tipos fora do conjunto suportado viram string —
    perder a tipagem é melhor que recusar o lote inteiro por um atributo
    exótico que o integrador mandou sem querer.
    """
    if isinstance(value, bool):
        any_value = {"boolValue": value}
    elif isinstance(value, int):
        any_value = {"intValue": str(value)}
    elif isinstance(value, float):
        any_value = {"doubleValue": value}
    elif isinstance(value, str):
        any_value = {"stringValue": value}
    else:
        any_value = {"stringValue": json.dumps(value, ensure_ascii=False, default=str)}
    return {"key": key, "value": any_value}


def _exception_attrs(event: Event) -> list[dict]:
    """Atributos de exceção com os nomes da convenção semântica do OTel —
    é o que o OpenObserve achata em `exception_type`/`exception_message`/
    `exception_stacktrace`, os campos que o `logs_agent` lê.
    """
    if event.exception is None:
        return []
    attrs = []
    if event.exception.type:
        attrs.append(_attr("exception.type", event.exception.type))
    if event.exception.message:
        attrs.append(_attr("exception.message", event.exception.message))
    if event.exception.stacktrace:
        attrs.append(_attr("exception.stacktrace", event.exception.stacktrace))
    return attrs


def _resource(request: IngestRequest) -> dict:
    attrs = [_attr("service.name", request.service)]
    if request.host:
        attrs.append(_attr("host.name", request.host))
    if request.environment:
        attrs.append(_attr("deployment.environment", request.environment))
    # Marca a origem: dá pra distinguir, numa investigação, o que veio do
    # coletor instalado do que veio da integração direta da aplicação.
    attrs.append(_attr("tracepilot.ingest_mode", "direct_api"))
    return {"attributes": attrs}


def _log_record(event: Event) -> dict:
    if not event.message and not (event.exception and event.exception.message):
        raise IngestError("evento kind='log' precisa de 'message' (ou exception.message)")
    body = event.message or f"{event.exception.type}: {event.exception.message}"
    severity = (event.severity or "INFO").upper()
    nano = to_unix_nano(event.timestamp)
    record: dict[str, Any] = {
        "timeUnixNano": str(nano),
        "observedTimeUnixNano": str(nano),
        "severityText": severity,
        "severityNumber": SEVERITY_NUMBERS.get(severity, 0),
        "body": {"stringValue": body},
        "attributes": [_attr(k, v) for k, v in event.attributes.items()] + _exception_attrs(event),
    }
    trace_id = _normalize_id(event.trace_id, bits=128, field="trace_id")
    span_id = _normalize_id(event.span_id, bits=64, field="span_id")
    if trace_id:
        record["traceId"] = trace_id
    if span_id:
        record["spanId"] = span_id
    return record


def _span(event: Event) -> dict:
    if not event.operation:
        raise IngestError("evento kind='span' precisa de 'operation'")
    trace_id = _normalize_id(event.trace_id, bits=128, field="trace_id")
    span_id = _normalize_id(event.span_id, bits=64, field="span_id")
    if not trace_id or not span_id:
        raise IngestError(
            "evento kind='span' precisa de 'trace_id' (32 hex) e 'span_id' (16 hex)"
        )

    start = to_unix_nano(event.start_time if event.start_time is not None else event.timestamp)
    if event.end_time is not None:
        end = to_unix_nano(event.end_time)
    elif event.duration_ms is not None:
        end = start + int(event.duration_ms * 1_000_000)
    else:
        end = start

    attributes = [_attr(k, v) for k, v in event.attributes.items()]
    if event.http:
        if event.http.method:
            attributes.append(_attr("http.request.method", event.http.method))
        if event.http.route:
            attributes.append(_attr("http.route", event.http.route))
        if event.http.status_code is not None:
            attributes.append(_attr("http.status_code", event.http.status_code))

    status = (event.status or "UNSET").upper()
    span: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": event.operation,
        "kind": 2,  # SERVER — o caso dominante de quem integra via API direta
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(end),
        "attributes": attributes,
        "status": {"code": SPAN_STATUS_CODES.get(status, 0)},
    }
    parent = _normalize_id(event.parent_span_id, bits=64, field="parent_span_id")
    if parent:
        span["parentSpanId"] = parent
    if event.exception and (event.exception.type or event.exception.message):
        if event.exception.message:
            span["status"]["message"] = event.exception.message
        # Exceção em span vai como span event "exception" (convenção do
        # OTel) — é de lá que o traces_agent lê, via o campo `events`.
        span["events"] = [
            {
                "timeUnixNano": str(end),
                "name": "exception",
                "attributes": _exception_attrs(event),
            }
        ]
    return span


def build_payloads(request: IngestRequest) -> tuple[dict | None, dict | None]:
    """Devolve `(payload_de_logs, payload_de_traces)` em OTLP/JSON — `None`
    quando o lote não tem eventos daquele tipo (não manda requisição vazia
    pro collector).
    """
    resource = _resource(request)
    log_records = [_log_record(e) for e in request.events if e.kind == "log"]
    spans = [_span(e) for e in request.events if e.kind == "span"]

    logs_payload = (
        {
            "resourceLogs": [
                {
                    "resource": resource,
                    "scopeLogs": [
                        {"scope": {"name": "tracepilot.ingest"}, "logRecords": log_records}
                    ],
                }
            ]
        }
        if log_records
        else None
    )
    traces_payload = (
        {
            "resourceSpans": [
                {
                    "resource": resource,
                    "scopeSpans": [{"scope": {"name": "tracepilot.ingest"}, "spans": spans}],
                }
            ]
        }
        if spans
        else None
    )
    return logs_payload, traces_payload


def integration_warnings(request: IngestRequest) -> list[str]:
    """Avisos sobre o que falta pro TracePilot investigar *bem* esse lote.

    Não bloqueia a ingestão: o lote é aceito e só vem acompanhado dos
    avisos. A razão é o público desta API — uma IA implementando a
    integração no código do cliente (ver docs/ai-integration-guide.md):
    ela manda um lote de teste, lê os avisos e corrige a integração sem
    ninguém precisar abrir o OpenObserve pra conferir se o campo certo
    chegou.
    """
    warnings: list[str] = []
    logs = [e for e in request.events if e.kind == "log"]
    spans = [e for e in request.events if e.kind == "span"]

    if logs and not any(e.trace_id for e in logs):
        warnings.append(
            "nenhum log com trace_id: o TracePilot não vai conseguir ligar "
            "esses logs à requisição que falhou (correlação log↔trace)"
        )
    if logs and not any((e.severity or "").upper() in ("ERROR", "WARNING", "WARN") for e in logs):
        warnings.append(
            "nenhum log com severity ERROR/WARNING: o logs_agent filtra por "
            "severidade — logs de erro sem essa marcação não entram na investigação"
        )
    if spans and not any((e.status or "").upper() == "ERROR" for e in spans):
        warnings.append(
            "nenhum span com status='ERROR': quando a investigação não tem "
            "trace_id conhecido, o traces_agent busca justamente os spans com erro"
        )
    if not spans and logs:
        warnings.append(
            "lote só com logs: sem spans o TracePilot perde latência, rota HTTP "
            "e a cadeia de chamadas — o diagnóstico fica mais fraco"
        )
    if not any(e.exception and e.exception.stacktrace for e in request.events):
        warnings.append(
            "nenhum evento com exception.stacktrace: é o campo que permite "
            "apontar arquivo/linha no prompt de correção"
        )
    return warnings
