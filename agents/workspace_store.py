"""Persistência do perfil do workspace — quem está usando o TracePilot, o
que o sistema monitorado é, e o progresso da jornada de configuração
inicial (onboarding).

Decisão de design: um único arquivo JSON (não um por registro, como em
`report_store.py`) porque isto é um *singleton* — este MVP de hackathon é
de um workspace só, sem conceito de múltiplos times/contas. Se isso virar
multi-tenant, o próximo passo natural é trocar por uma linha por
workspace num banco (SQLite), não escalar este arquivo único.

Consequência prática de ser global: uma vez que *qualquer* navegador
termine o onboarding, todo login seguinte (com qualquer nome/e-mail) cai
direto no dashboard — não há onboarding por pessoa. Pra ver a jornada de
novo (ex.: demonstrar para alguém), use `reset_onboarding()` (exposto
também como botão na interface) ou apague `workspace/profile.json`.
"""
import json
import time
from pathlib import Path

WORKSPACE_FILE = Path(__file__).resolve().parent.parent / "workspace" / "profile.json"


def _default_profile() -> dict:
    now = time.time()
    return {
        "user": {"name": None, "email": None},
        "system_name": None,
        "objective": None,
        "dev_method": None,
        "dev_method_tool": None,
        "environment": None,
        "environment_notes": None,
        # Onde o sistema monitorado responde e com que nome ele aparece na
        # telemetria (OTel `service.name`) — usados no health check, na
        # contagem de erros e como serviço padrão das investigações.
        "app_url": None,
        "service_name": None,
        "related_services": [],
        "repo_url": None,
        "repo_local_path": None,
        "repo_info": None,
        "host_snapshot": None,
        "onboarding": {
            "completed": False,
            "completed_at": None,
            "current_step": None,
        },
        "created_at": now,
        "updated_at": now,
    }


def load() -> dict:
    """Lê o perfil. Nunca levanta exceção — arquivo ausente ou corrompido
    volta como perfil default, porque todo chamador (templates incluídos)
    espera o formato completo, não `None`.
    """
    if not WORKSPACE_FILE.exists():
        return _default_profile()
    try:
        data = json.loads(WORKSPACE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return _default_profile()
    merged = _default_profile()
    merged.update(data)
    return merged


def save(profile: dict) -> dict:
    WORKSPACE_FILE.parent.mkdir(parents=True, exist_ok=True)
    profile["updated_at"] = time.time()
    WORKSPACE_FILE.write_text(
        json.dumps(profile, default=str, ensure_ascii=False, indent=2)
    )
    return profile


def update(**fields) -> dict:
    """Atualiza campos do perfil. Campos cujo valor novo e atual são
    ambos dict (ex.: `user=`, `onboarding=`) são mesclados nível 1 em vez
    de substituídos — assim `update(onboarding={"current_step": "repo"})`
    não apaga `completed`, e `update(user={"name": "..."})` não apaga
    `email` já salvo.
    """
    profile = load()
    for key, value in fields.items():
        current = profile.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            current.update(value)
        else:
            profile[key] = value
    return save(profile)


def is_onboarded() -> bool:
    return bool(load()["onboarding"]["completed"])


def mark_onboarding_complete() -> dict:
    return update(onboarding={"completed": True, "completed_at": time.time()})


def reset_onboarding() -> dict:
    """Mantém o resto do perfil (respostas do questionário, repo, etc.) —
    só volta a jornada pro início, pra poder demonstrar de novo."""
    return update(onboarding={"completed": False, "completed_at": None, "current_step": None})


def current_step() -> str | None:
    return load()["onboarding"]["current_step"]


def set_current_step(slug: str) -> dict:
    return update(onboarding={"current_step": slug})
