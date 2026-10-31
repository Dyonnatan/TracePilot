"""API de ingestão direta do TracePilot — o caminho **sem instalador**.

O TracePilot tem dois modos de ingestão (ver docs/ingestion-modes.md):

1. **Coletor instalável** (`local-agent/`) — instalado na máquina
   monitorada, coleta recursos do SO e tail de log sem a aplicação saber
   que existe.
2. **Esta API** — a própria aplicação manda log/span direto, em JSON
   simples. Complementar, não substituta: serve pra infra onde não dá pra
   instalar nada (PaaS, serverless, política de segurança), e pra quem
   quer *otimizar* o envio mandando só o que importa (o erro, com
   stacktrace e trace_id) em vez de despejar todo o log da máquina no
   pipeline.

Roda como serviço separado do `webapp/` de propósito: este é plano de
dados (recebe tráfego da aplicação do cliente, possivelmente exposto
publicamente) e o `webapp/` é plano de controle (painel do operador).
Misturar os dois num processo só daria ao tráfego do cliente a mesma
superfície de ataque do painel.

Rodar:

    uvicorn ingest.main:app --host 0.0.0.0 --port 8810
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import PlainTextResponse

from ingest.otlp import IngestError, build_payloads, integration_warnings
from ingest.schema import IngestRequest

BASE_DIR = Path(__file__).resolve().parent
GUIDE_PATH = BASE_DIR.parent / "docs" / "ai-integration-guide.md"

OTLP_HTTP_ENDPOINT = os.getenv("TRACEPILOT_OTLP_HTTP_ENDPOINT", "http://localhost:4318").rstrip("/")
MAX_EVENTS = int(os.getenv("TRACEPILOT_INGEST_MAX_EVENTS", "500"))


def _allowed_keys() -> set[str]:
    raw = os.getenv("TRACEPILOT_INGEST_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


app = FastAPI(
    title="TracePilot Ingest API",
    description=(
        "Ingestão direta de logs e spans, para aplicações que não podem (ou "
        "não querem) instalar o coletor do TracePilot. Guia de integração "
        "pronto para IA em GET /v1/guide."
    ),
)


def _check_auth(authorization: str | None) -> None:
    """Chave de API por serviço integrado.

    Sem `TRACEPILOT_INGEST_KEYS` configurado, a API aceita qualquer
    requisição — conveniente pra desenvolvimento local, mas é justamente o
    que não pode ir pra produção: este endpoint recebe stacktrace, rota e
    corpo de log, e sem chave qualquer um escreveria evidência falsa numa
    investigação. `GET /v1/health` denuncia esse estado em `auth`.
    """
    keys = _allowed_keys()
    if not keys:
        return
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="informe 'Authorization: Bearer <chave>'")
    if authorization.split(" ", 1)[1].strip() not in keys:
        raise HTTPException(status_code=401, detail="chave de ingestão inválida")


@app.post("/v1/events", status_code=202)
def ingest_events(payload: IngestRequest, authorization: str | None = Header(default=None)):
    """Recebe um lote de eventos de um serviço e repassa em OTLP pro collector.

    Responde 202 com a contagem do que foi aceito e `warnings`: o que falta
    no lote pro TracePilot investigar bem (ver `integration_warnings`). É o
    retorno que fecha o ciclo da integração escrita por IA — manda lote de
    teste, lê os avisos, corrige.
    """
    _check_auth(authorization)

    if not payload.events:
        raise HTTPException(status_code=422, detail="lote sem eventos")
    if len(payload.events) > MAX_EVENTS:
        raise HTTPException(
            status_code=413,
            detail=f"lote com {len(payload.events)} eventos excede o limite de {MAX_EVENTS}",
        )

    try:
        logs_payload, traces_payload = build_payloads(payload)
    except IngestError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    sent = {"logs": 0, "spans": 0}
    try:
        with httpx.Client(timeout=10) as client:
            if logs_payload:
                response = client.post(f"{OTLP_HTTP_ENDPOINT}/v1/logs", json=logs_payload)
                response.raise_for_status()
                sent["logs"] = len(logs_payload["resourceLogs"][0]["scopeLogs"][0]["logRecords"])
            if traces_payload:
                response = client.post(f"{OTLP_HTTP_ENDPOINT}/v1/traces", json=traces_payload)
                response.raise_for_status()
                sent["spans"] = len(traces_payload["resourceSpans"][0]["scopeSpans"][0]["spans"])
    except httpx.HTTPError as exc:
        # 502: o lote estava válido, quem falhou foi o pipeline do
        # TracePilot. O integrador não deve "corrigir" nada — deve repetir.
        raise HTTPException(
            status_code=502,
            detail=f"falha ao repassar pro collector em {OTLP_HTTP_ENDPOINT}: {exc}",
        ) from exc

    return {
        "accepted": sent,
        "service": payload.service,
        "warnings": integration_warnings(payload),
    }


@app.get("/v1/guide", response_class=PlainTextResponse)
def integration_guide():
    """Serve o guia de integração em markdown.

    Existe como endpoint (não só como arquivo no repositório) pra que a IA
    que vai escrever a integração no código do cliente possa buscar o
    contrato direto da instância do TracePilot que ela vai alimentar — sem
    depender de uma cópia colada que envelhece.
    """
    if not GUIDE_PATH.exists():
        raise HTTPException(status_code=404, detail="guia de integração não encontrado")
    return PlainTextResponse(GUIDE_PATH.read_text(encoding="utf-8"), media_type="text/markdown")


@app.get("/v1/health")
def health():
    try:
        with httpx.Client(timeout=3) as client:
            # O receiver OTLP/HTTP não tem rota de health; um POST vazio
            # responder 200/400 já prova que tem alguém escutando ali.
            response = client.post(f"{OTLP_HTTP_ENDPOINT}/v1/logs", json={})
        collector_up = response.status_code < 500
    except httpx.HTTPError:
        collector_up = False
    return {
        "status": "ok",
        "collector": {"endpoint": OTLP_HTTP_ENDPOINT, "up": collector_up},
        "auth": "api_key" if _allowed_keys() else "aberta (defina TRACEPILOT_INGEST_KEYS)",
        "max_events_per_batch": MAX_EVENTS,
    }
