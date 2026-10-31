"""Wrapper fino sobre a API HTTP do OpenObserve.

Os métodos abaixo foram escritos e validados contra uma instância local real
(ver `docker-compose.yml`), gerando tráfego de sucesso/falha no `demo_app` e
inspecionando o schema de fato ingerido — não são um "melhor palpite" sobre a
API do OpenObserve. `query_logs` e `query_traces` usam os nomes de campo
confirmados; `query_metrics` segue a mesma mecânica de busca, mas **ainda não
foi validado contra dado real** porque o `demo_app` hoje não exporta métricas
(ver TODO no fim do arquivo).

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
        """
        conditions = []
        if query_text:
            escaped = query_text.replace("'", "''")
            conditions.append(f"body ILIKE '%{escaped}%'")
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
        stream: str = "default",
        size: int = 50,
    ) -> list[dict]:
        """Busca métricas.

        TODO: `demo_app` ainda não exporta métricas (só traces/logs), então
        este método não foi validado contra dado real — o nome do campo de
        métrica (`metric_name` abaixo) é uma suposição baseada na convenção
        do OpenObserve para OTLP, e deve ser conferido contra uma instância
        real assim que houver uma fonte de métricas (ex.: o
        `reference-environment`, ver docs/reference-environment.md).
        """
        conditions = [f"metric_name = '{_escape(metric_name)}'"]
        if service:
            conditions.append(f"service_name = '{_escape(service)}'")
        where = " AND ".join(conditions)
        sql = f'SELECT * FROM "{stream}" WHERE {where} ORDER BY _timestamp DESC'
        start_us, end_us = _resolve_window(start_time, end_time)
        return self._search("metrics", sql, start_us, end_us, size)


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
