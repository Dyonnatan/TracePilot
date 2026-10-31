from agents.llm import get_provider
from agents.llm.cloud_provider import CloudProvider
from agents.llm.local_provider import LocalProvider


def test_local_backend(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "local")
    assert isinstance(get_provider(), LocalProvider)


def test_cloud_backend_and_default(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "cloud")
    assert isinstance(get_provider(), CloudProvider)

    monkeypatch.setenv("LLM_BACKEND", "outro")
    assert isinstance(get_provider(), CloudProvider)

    monkeypatch.delenv("LLM_BACKEND", raising=False)
    assert isinstance(get_provider(), CloudProvider)
