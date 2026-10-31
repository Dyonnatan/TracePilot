from agents.llm import LLMProvider
from agents.tools.openobserve_client import OpenObserveClient


def run(state: dict, llm: LLMProvider, client: OpenObserveClient) -> dict:
    """Investiga logs relevantes ao incidente e devolve evidências ao estado.

    TODO: montar a query de logs a partir do erro relatado em `state`,
    consultar o OpenObserveClient, e usar o LLM para resumir achados
    relevantes (sem alucinar — só reportar o que veio da consulta).
    """
    raise NotImplementedError("TODO: lógica do logs_agent")
