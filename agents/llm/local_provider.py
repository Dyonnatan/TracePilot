import os

from .base import LLMProvider


class LocalProvider(LLMProvider):
    """Provider via modelo open-weight local, servido pelo Ollama.

    TODO: implementar a chamada real ao Ollama (cliente `ollama` Python),
    com timeout e fallback para o CloudProvider se o modelo local não
    estiver disponível.
    """

    def __init__(self, model: str | None = None):
        self.host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.1")

    def generate(self, prompt: str, **kwargs) -> str:
        raise NotImplementedError("TODO: integrar com o Ollama local")
