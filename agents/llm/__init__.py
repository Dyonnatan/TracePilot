from .base import LLMProvider
from .cloud_provider import CloudProvider
from .local_provider import LocalProvider

__all__ = ["LLMProvider", "CloudProvider", "LocalProvider", "get_provider"]


def get_provider() -> LLMProvider:
    """Resolve o LLMProvider configurado via env var LLM_BACKEND (cloud|local)."""
    import os

    backend = os.getenv("LLM_BACKEND", "cloud")
    if backend == "local":
        return LocalProvider()
    return CloudProvider()
