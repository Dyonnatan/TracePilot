import os

DEFAULT_CHECKPOINT = "convaiinnovations/laya"


class DecisionProvider:
    """Provider para modelos de decisão tipada ("System 1") — hoje usa o
    Laya (Convai Innovations): um encoder (ModernBERT, não-gerativo) que
    responde perguntas tipadas (sim/não, múltipla escolha, nota) com
    probabilidade calibrada, em vez de gerar texto livre. Ver
    docs/decision-models.md para a comparação com Jev/Kev e a justificativa
    de design.

    Por não ser gerativo, não tem como "alucinar" uma resposta fora das
    opções dadas — serve de checagem independente ao lado do veredito do
    LLM de texto no `verifier_agent`, não como substituto (o LLM ainda
    produz as notas explicativas legíveis do relatório).
    """

    def __init__(self, checkpoint: str | None = None):
        self._checkpoint = checkpoint or os.getenv("LAYA_CHECKPOINT", DEFAULT_CHECKPOINT)
        self._agent = None

    def _get_agent(self):
        if self._agent is None:
            import laya

            self._agent = laya.load(self._checkpoint)
        return self._agent

    def yes_no(self, state_text: str, instructions: str, key: str = "decision") -> float:
        """Retorna a probabilidade calibrada (0.0-1.0) de a resposta à
        pergunta `instructions`, sobre o texto `state_text`, ser "sim".
        """
        agent = self._get_agent()
        result = agent.predict(state_text, {key: {"type": "noul", "instructions": instructions}})
        return float(result["answers"][key]["noul"])
