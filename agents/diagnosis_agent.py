from agents.llm import LLMProvider


def run(state: dict, llm: LLMProvider) -> dict:
    """Consolida as evidências coletadas pelos agentes especialistas
    (logs/métricas/traces) em uma ou mais hipóteses de causa-raiz,
    com nível de confiança e evidências associadas.

    TODO: implementar o raciocínio de consolidação de hipóteses e decidir
    se evidências adicionais precisam ser solicitadas a um especialista
    antes de seguir para o verifier_agent.
    """
    raise NotImplementedError("TODO: lógica do diagnosis_agent")
