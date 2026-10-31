import os

from .base import LLMProvider


class CloudProvider(LLMProvider):
    """Provider via API cloud (Anthropic por padrão).

    TODO: implementar a chamada real à API (Anthropic/OpenAI), tratamento de
    streaming, retries e logging de prompts/saídas para rastreabilidade
    (LLMOps).
    """

    def __init__(self, model: str | None = None):
        self.model = model or os.getenv("CLOUD_MODEL", "claude-sonnet-5")
        self.api_key = os.getenv("ANTHROPIC_API_KEY")

    def generate(self, prompt: str, **kwargs) -> str:
        raise NotImplementedError("TODO: integrar com a API Anthropic/OpenAI")
