from .base import LLMProvider
from .cloud_provider import CloudProvider
from .local_provider import LocalProvider

__all__ = ["LLMProvider", "CloudProvider", "LocalProvider", "get_provider"]


def get_provider() -> LLMProvider:
    """Resolve o LLMProvider configurado via env var LLM_BACKEND (cloud|local)."""
    import os

    backend = os.getenv("LLM_BACKEND", "").strip().lower()
    if backend == "local":
        return LocalProvider()
    if backend == "cloud":
        return CloudProvider()
    # Não configurado: nuvem se houver chave, senão o modelo local (Ollama).
    # Antes o padrão era sempre nuvem, e sem OPENROUTER_API_KEY toda
    # investigação morria no primeiro agente.
    return CloudProvider() if os.getenv("OPENROUTER_API_KEY") else LocalProvider()
