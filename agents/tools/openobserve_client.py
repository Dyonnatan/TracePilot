import os


class OpenObserveClient:
    """Wrapper fino sobre a API HTTP do OpenObserve, usado pelos agentes
    especialistas para consultar logs, métricas e traces.

    TODO: implementar os métodos de consulta reais (ex.: `query_logs`,
    `query_traces`, `query_metrics`) usando a API SQL/stream do OpenObserve,
    limitando os agentes a operações de leitura (somente consulta).
    """

    def __init__(self, base_url: str | None = None, org: str | None = None, token: str | None = None):
        self.base_url = base_url or os.getenv("OPENOBSERVE_URL", "http://localhost:5080")
        self.org = org or os.getenv("OPENOBSERVE_ORG", "default")
        self.token = token or os.getenv("OPENOBSERVE_TOKEN")

    def query_logs(self, query: str, start_time: str, end_time: str):
        raise NotImplementedError("TODO: consultar stream de logs no OpenObserve")

    def query_traces(self, trace_id: str | None = None, service: str | None = None):
        raise NotImplementedError("TODO: consultar traces no OpenObserve")

    def query_metrics(self, metric_name: str, start_time: str, end_time: str):
        raise NotImplementedError("TODO: consultar métricas no OpenObserve")
