"""Presets de demonstração — respostas prontas para a jornada de
onboarding, para a demo ser "next, next" em vez de digitar tudo ao vivo.

Escolhido por `TRACEPILOT_PRESET` (nome de um arquivo em
`webapp/presets/`, sem `.json`). Padrão: `reference-environment`, o
ambiente de referência da branch `feat/reference-environment` (loja Apex
Space). `TRACEPILOT_PRESET=none` desliga: formulários vêm vazios.

O preset só preenche o que o perfil ainda não tem — resposta já salva
pela pessoa sempre vence.
"""
import json
import os
from functools import lru_cache
from pathlib import Path

PRESETS_DIR = Path(__file__).resolve().parent / "presets"
DEFAULT_PRESET = "reference-environment"

FORM_FIELDS = (
    "system_name",
    "objective",
    "dev_method",
    "environment",
    "app_url",
    "service_name",
)


@lru_cache(maxsize=None)
def _load(name: str) -> dict | None:
    path = PRESETS_DIR / f"{name}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def active() -> dict | None:
    name = os.getenv("TRACEPILOT_PRESET", DEFAULT_PRESET).strip()
    if not name or name.lower() == "none":
        return None
    return _load(name)


def repos(preset: dict | None = None) -> list[dict]:
    """Repositórios do preset como lista de {url, local_path}. Aceita o
    formato antigo (repo_url + repo_local_path) para não quebrar presets."""
    preset = active() if preset is None else preset
    preset = preset or {}
    if preset.get("repos"):
        return [r for r in preset["repos"] if r.get("url")]
    if preset.get("repo_url"):
        return [{"url": preset["repo_url"], "local_path": preset.get("repo_local_path")}]
    return []


def local_path_for(url: str) -> str | None:
    url = url.rstrip("/")
    for r in repos():
        if r["url"].rstrip("/") == url:
            return r.get("local_path")
    return None


def form_values(profile: dict) -> dict:
    """Valores para preencher os formulários: o que está no perfil, e o
    preset onde o perfil ainda está vazio."""
    preset = active() or {}
    values = {}
    for field in FORM_FIELDS:
        current = profile.get(field)
        values[field] = current if current not in (None, "") else preset.get(field, "")
    values["repo_urls"] = (
        profile.get("repo_urls")
        or ([profile["repo_url"]] if profile.get("repo_url") else None)
        or [r["url"] for r in repos(preset)]
        or [""]
    )
    return values
