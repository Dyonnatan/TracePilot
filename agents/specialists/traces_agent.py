from agents.llm import LLMProvider
from agents.tools.openobserve_client import OpenObserveClient


def run(state: dict, llm: LLMProvider, client: OpenObserveClient) -> dict:
    """Investiga traces distribuídos relacionados ao incidente (spans,
    latência por serviço, erros propagados) e devolve evidências ao estado.

    TODO: montar a query de traces a partir do trace_id/serviço em `state`,
    consultar o OpenObserveClient, e identificar o span onde o erro se
    originou.
    """
    raise NotImplementedError("TODO: lógica do traces_agent")
