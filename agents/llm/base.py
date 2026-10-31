from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Interface comum para providers de LLM (cloud ou local), para que o
    resto do código (orquestrador, agentes) não acople a uma API específica.
    """

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        """Gera uma resposta de texto a partir de um prompt."""
        raise NotImplementedError
