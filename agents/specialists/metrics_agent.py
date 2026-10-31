from agents.llm import LLMProvider
from agents.tools.openobserve_client import OpenObserveClient


def run(state: dict, llm: LLMProvider, client: OpenObserveClient) -> dict:
    """Investiga métricas (latência, taxa de erro, saturação) relacionadas
    ao incidente e devolve evidências ao estado.

    TODO: montar a query de métricas a partir da hipótese atual em `state`,
    consultar o OpenObserveClient, e identificar anomalias/correlações
    temporais com o erro.
    """
    raise NotImplementedError("TODO: lógica do metrics_agent")
