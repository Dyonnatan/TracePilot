"""Inspeção leve de um repositório via API do GitHub — usada no passo
opcional do onboarding em que a pessoa cola o link do repositório do
sistema monitorado. Não clona nada: só duas chamadas de leitura na API
pública (metadados + breakdown de linguagens), o suficiente pra enriquecer
o diagrama de arquitetura com "o que essa aplicação parece ser feita de",
sem o custo/risco de baixar e analisar código de verdade.

Decisão de design: só funciona para `github.com` (a esmagadora maioria
dos repositórios hoje) — qualquer outra URL ou falha na API degrada para
"informado, mas não analisado automaticamente", nunca trava o onboarding.
"""
import os
import re
import time

import httpx

GITHUB_API = "https://api.github.com"

_GITHUB_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/([^/\s]+)/([^/\s]+?)(?:\.git)?/?$"
)


def _parse_github_url(repo_url: str) -> tuple[str, str] | None:
    if not repo_url:
        return None
    match = _GITHUB_URL_RE.match(repo_url.strip())
    if not match:
        return None
    return match.group(1), match.group(2)


def inspect_repo(repo_url: str) -> dict:
    parsed = _parse_github_url(repo_url)
    if parsed is None:
        return {"analyzed": False, "reason": "not_github", "repo_url": repo_url}

    owner, name = parsed
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        repo_resp = httpx.get(f"{GITHUB_API}/repos/{owner}/{name}", headers=headers, timeout=5)
        if repo_resp.status_code == 404:
            # A API pública devolve 404 tanto para repo inexistente quanto
            # para repo privado sem token — não dá pra distinguir.
            return {"analyzed": False, "reason": "not_found", "repo_url": repo_url}
        repo_resp.raise_for_status()
        repo_data = repo_resp.json()

        lang_resp = httpx.get(f"{GITHUB_API}/repos/{owner}/{name}/languages", headers=headers, timeout=5)
        lang_resp.raise_for_status()
        languages = lang_resp.json()
    except Exception:
        return {"analyzed": False, "reason": "api_error", "repo_url": repo_url}

    primary_language = max(languages, key=languages.get) if languages else repo_data.get("language")

    return {
        "analyzed": True,
        "repo_url": repo_url,
        "owner": owner,
        "name": name,
        "description": repo_data.get("description"),
        "stars": repo_data.get("stargazers_count"),
        "default_branch": repo_data.get("default_branch"),
        "pushed_at": repo_data.get("pushed_at"),
        "languages": languages,
        "primary_language": primary_language,
        "checked_at": time.time(),
    }
