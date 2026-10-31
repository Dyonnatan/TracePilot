from agents.llm import LLMProvider


def run(state: dict, llm: LLMProvider) -> dict:
    """Confronta a(s) hipótese(s) do diagnosis_agent com as evidências
    disponíveis, rejeitando conclusões sem suporte suficiente e, se
    necessário, pedindo nova investigação a um especialista.

    TODO: implementar os critérios de verificação (evidência mínima por
    hipótese, contradições entre fontes) e a decisão de aceitar o
    diagnóstico ou devolver ao orquestrador para mais investigação.
    """
    raise NotImplementedError("TODO: lógica do verifier_agent")
