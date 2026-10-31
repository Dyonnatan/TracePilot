"""Contrato da API de ingestão direta do TracePilot.

Este schema é deliberadamente **mais simples que o OTLP**: o caminho de
ingestão direta existe pra quem *não pode* instalar o coletor nem adotar
um SDK de OpenTelemetry (infra gerenciada, PaaS, função serverless,
política de segurança que proíbe agente na máquina). Pedir OTLP cru nesse
cenário empurraria o integrador de volta pro problema que ele não pode
resolver.

O que a aplicação manda aqui é JSON plano; `otlp.py` traduz pro OTLP que o
`otel-collector` (e, por consequência, o OpenObserve e os agentes de IA)
já entende. Os campos obrigatórios/opcionais abaixo não são arbitrários:
são exatamente o que `agents/tools/openobserve_client.py` consulta e o que
os agentes especialistas filtram (ver docs/ai-integration-guide.md).
"""
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExceptionInfo(BaseModel):
    """Exceção associada a um log ou span.

    É a evidência de maior valor pro `diagnosis_agent`: `stacktrace` é o que
    permite apontar arquivo/linha na correção sugerida. Sem ele o
    diagnóstico cai pra "erro em algum ponto deste serviço".
    """

    type: str | None = None
    message: str | None = None
    stacktrace: str | None = None


class HttpInfo(BaseModel):
    method: str | None = None
    route: str | None = None
    status_code: int | None = None


class Event(BaseModel):
    """Um evento — log ou span — da aplicação integrada."""

    kind: Literal["log", "span"]

    # Correlação. `trace_id` é o que liga o log ao span (e o span ao span
    # pai): é o que permite ao TracePilot responder "qual requisição
    # falhou", não só "aconteceu um erro". 32 hex para trace, 16 para span.
    trace_id: str | None = None
    span_id: str | None = None
    parent_span_id: str | None = None

    # ISO-8601 ("2026-10-31T12:00:00Z") ou epoch numérico (s/ms/us/ns —
    # resolvido por magnitude). Ausente = agora, no servidor de ingestão.
    timestamp: str | int | float | None = None

    # --- Só para kind="log" ---
    # `severity` é o filtro primário do logs_agent (ERROR/WARNING/WARN).
    severity: str | None = None
    message: str | None = None

    # --- Só para kind="span" ---
    operation: str | None = None
    start_time: str | int | float | None = None
    end_time: str | int | float | None = None
    duration_ms: float | None = None
    # "ERROR" é o filtro primário do traces_agent quando não há trace_id
    # conhecido — span de requisição que falhou precisa vir marcado.
    status: Literal["OK", "ERROR", "UNSET"] | None = None
    http: HttpInfo | None = None

    # --- Comum aos dois ---
    exception: ExceptionInfo | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class IngestRequest(BaseModel):
    """Lote de eventos de um serviço.

    `service` fica no lote (não no evento) porque vira `service.name` no
    resource OTLP — e é por ele que toda investigação do TracePilot
    filtra. Um lote = um serviço.
    """

    service: str
    host: str | None = None
    environment: str | None = None
    events: list[Event]
