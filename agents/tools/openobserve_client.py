"""Wrapper fino sobre a API HTTP do OpenObserve.

Os métodos abaixo foram escritos e validados contra uma instância local real
(ver `docker-compose.yml`), gerando tráfego de sucesso/falha no `demo_app` e
inspecionando o schema de fato ingerido — não são um "melhor palpite" sobre a
API do OpenObserve. `query_logs` e `query_traces` usam os nomes de campo
confirmados; `query_metrics` foi validado contra as métricas reais do
`local-agent` (um stream por métrica — ver o método).

Decisão de design: só métodos de leitura/consulta são expostos — os agentes
nunca devem ter acesso de escrita/admin ao OpenObserve.
"""
import os
import time

import httpx


class OpenObserveClient:
    def __init__(self, base_url: str | None = None, org: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("OPENOBSERVE_URL", "http://localhost:5080")).rstrip("/")
        self.org = org or os.getenv("OPENOBSERVE_ORG", "default")
        self.token = token or os.getenv("OPENOBSERVE_TOKEN")

    def _auth_headers_and_auth(self) -> tuple[dict, tuple[str, str] | None]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            return headers, None
        user = os.getenv("OPENOBSERVE_USER")
        password = os.getenv("OPENOBSERVE_PASSWORD")
        if user and password:
            return headers, (user, password)
        raise RuntimeError(
            "Nenhuma credencial do OpenObserve configurada: defina "
            "OPENOBSERVE_TOKEN, ou OPENOBSERVE_USER + OPENOBSERVE_PASSWORD no .env."
        )

    def list_streams(self) -> list[dict]:
        """Lista os streams existentes (nome, tipo, nº de documentos) — usado
        pelo painel de monitoramento da interface web, não pelos agentes.
        """
        headers, auth = self._auth_headers_and_auth()
        url = f"{self.base_url}/api/{self.org}/streams"
        response = httpx.get(url, headers=headers, auth=auth, timeout=15)
        response.raise_for_status()
        streams = response.json().get("list", [])
        return [
            {
                "name": s.get("name"),
                "type": s.get("stream_type"),
                "doc_count": (s.get("stats") or {}).get("doc_num", 0),
            }
            for s in streams
        ]

    def _search(
        self,
        stream_type: str,
        sql: str,
        start_time: int,
        end_time: int,
        size: int = 50,
    ) -> list[dict]:
        """Executa uma busca SQL no OpenObserve.

        `stream_type` é "logs", "traces" ou "metrics" — o OpenObserve
        precisa do parâmetro `type` na URL para resolver em qual stream
        buscar, já que `default` é compartilhado entre os três tipos.
        """
        headers, auth = self._auth_headers_and_auth()
        url = f"{self.base_url}/api/{self.org}/_search"
        payload = {
            "query": {
                "sql": sql,
                "start_time": start_time,
                "end_time": end_time,
                "from": 0,
                "size": size,
            }
        }
        response = httpx.post(
            url,
            params={"type": stream_type},
            json=payload,
            headers=headers,
            auth=auth,
            timeout=30,
        )
        response.raise_for_status()
        return response.json().get("hits", [])

    def query_logs(
        self,
        query_text: str | None = None,
        severities: list[str] | None = None,
        start_time: str | int | None = None,
        end_time: str | int | None = None,
        service: str | None = None,
        trace_id: str | None = None,
        stream: str = "default",
        size: int = 50,
    ) -> list[dict]:
        """Busca logs. Campos confirmados: `body` (mensagem), `severity`,
        `trace_id`, `span_id`, `service_name`, `exception_type`,
        `exception_message`, `exception_stacktrace`.

        `query_text`, quando informado, busca em `body` OU `exception_type`
        OU `exception_message` — não só na mensagem crua — porque um relato
        de erro em linguagem natural (ex. "checkout falhando") raramente
        aparece literal no corpo do log; já um termo técnico específico
        (ex. "ZeroDivisionError") tende a bater em `exception_type`.
        `severities` (ex. `["ERROR", "WARNING"]`) é o filtro mais confiável
        para achar logs relevantes a um incidente sem depender de uma
        palavra-chave exata — por isso é o que `logs_agent.py` usa por
        padrão, em vez de `query_text`.
        """
        conditions = []
        if query_text:
            escaped = _escape(query_text)
            conditions.append(
                f"(body ILIKE '%{escaped}%' OR exception_type ILIKE '%{escaped}%' "
                f"OR exception_message ILIKE '%{escaped}%')"
            )
        if severities:
            in_list = ", ".join(f"'{_escape(s)}'" for s in severities)
            conditions.append(f"severity IN ({in_list})")
        if service:
            conditions.append(f"service_name = '{_escape(service)}'")
        if trace_id:
            conditions.append(f"trace_id = '{_escape(trace_id)}'")
        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f'SELECT * FROM "{stream}" WHERE {where} ORDER BY _timestamp DESC'
        start_us, end_us = _resolve_window(start_time, end_time)
        return self._search("logs", sql, start_us, end_us, size)

    def query_traces(
        self,
        trace_id: str | None = None,
        service: str | None = None,
        only_errors: bool = False,
        start_time: str | int | None = None,
        end_time: str | int | None = None,
        stream: str = "default",
        size: int = 50,
    ) -> list[dict]:
        """Busca spans. Campos confirmados: `trace_id`, `span_id`,
        `service_name`, `operation_name`, `span_status` ("ERROR"/"UNSET"),
        `events` (string JSON com `exception.type/message/stacktrace`
        quando o span registrou uma exceção), `http_status_code`,
        `http_route`, `duration`.
        """
        conditions = []
        if trace_id:
            conditions.append(f"trace_id = '{_escape(trace_id)}'")
        if service:
            conditions.append(f"service_name = '{_escape(service)}'")
        if only_errors:
            conditions.append("span_status = 'ERROR'")
        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f'SELECT * FROM "{stream}" WHERE {where} ORDER BY _timestamp DESC'
        start_us, end_us = _resolve_window(start_time, end_time)
        return self._search("traces", sql, start_us, end_us, size)

    def query_metrics(
        self,
        metric_name: str,
        start_time: str | int | None = None,
        end_time: str | int | None = None,
        service: str | None = None,
        stream: str | None = None,
        size: int = 50,
    ) -> list[dict]:
        """Busca pontos de uma métrica. Validado contra dado real do
        `local-agent`: o OpenObserve grava **cada métrica num stream
        próprio**, com o nome trocando "." por "_" (ex.:
        `system.cpu.usage_percent` → stream `system_cpu_usage_percent`), e
        cada hit traz `value`, `service_name`, `host_name` e os atributos
        do ponto (ex.: `mount_point`). Stream inexistente (métrica nunca
        recebida) levanta erro HTTP — o chamador decide o que fazer.
        """
        stream = stream or metric_name.replace(".", "_")
        conditions = []
        if service:
            conditions.append(f"service_name = '{_escape(service)}'")
        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f'SELECT * FROM "{stream}" WHERE {where} ORDER BY _timestamp DESC'
        start_us, end_us = _resolve_window(start_time, end_time)
        return self._search("metrics", sql, start_us, end_us, size)

    def recent_http_requests(
        self,
        services: list[str],
        minutes: int = 15,
        size: int = 2000,
        exclude_agents: list[str] | None = None,
    ) -> list[dict]:
        """Requisições HTTP recebidas pelos `services` (spans de servidor,
        `span_kind = '2'`) na janela recente, só com os campos usados na
        detecção de tráfego suspeito. Validado contra spans reais da
        instrumentação FastAPI do OpenTelemetry: `http_target` vem SEM a
        query string; a URL completa (com `?q=...`) está em `http_url`.
        `exclude_agents` tira tráfego sintético conhecido já na consulta,
        para ele não ocupar o limite de `size`."""
        in_list = ", ".join(f"'{_escape(s)}'" for s in services)
        conditions = [f"service_name IN ({in_list})", "span_kind = '2'"]
        for agent in exclude_agents or []:
            conditions.append(
                f"(http_user_agent IS NULL OR http_user_agent NOT LIKE '%{_escape(agent)}%')"
            )
        start_us, end_us = _resolve_window(None, None, default_minutes=minutes)
        sql = (
            "SELECT _timestamp, http_method, http_target, http_url, http_status_code, "
            "http_user_agent, net_peer_ip, service_name "
            f'FROM "default" WHERE {" AND ".join(conditions)} ORDER BY _timestamp DESC'
        )
        return self._search("traces", sql, start_us, end_us, size)

    def recent_sources(self, services: list[str], minutes: int = 15) -> dict:
        """De onde está chegando telemetria dos `services` na janela
        recente: quantos logs/spans chegaram e se algum veio pela API de
        ingestão direta (atributo `tracepilot.ingest_mode` →
        `tracepilot_ingest_mode` no OpenObserve)."""
        in_list = ", ".join(f"'{_escape(s)}'" for s in services)
        start_us, end_us = _resolve_window(None, None, default_minutes=minutes)
        result = {"logs": 0, "traces": 0, "direct_api": False}
        for kind in ("logs", "traces"):
            try:
                hits = self._search(
                    kind,
                    f'SELECT * FROM "default" WHERE service_name IN ({in_list}) ORDER BY _timestamp DESC',
                    start_us, end_us, 200,
                )
            except Exception:
                continue
            result[kind] = len(hits)
            if any(h.get("tracepilot_ingest_mode") == "direct_api" for h in hits):
                result["direct_api"] = True
        return result


def _escape(value: str) -> str:
    return value.replace("'", "''")


def _resolve_window(start_time: str | int | None, end_time: str | int | None, default_minutes: int = 60) -> tuple[int, int]:
    """Converte a janela de tempo para microssegundos Unix (formato exigido
    pela API de busca do OpenObserve). Aceita int (já em microssegundos) ou
    None (usa os últimos `default_minutes`).
    """
    now_us = int(time.time() * 1_000_000)
    end_us = int(end_time) if end_time is not None else now_us
    start_us = int(start_time) if start_time is not None else end_us - default_minutes * 60 * 1_000_000
    return start_us, end_us
