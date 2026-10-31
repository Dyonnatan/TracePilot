"""Interface web do TracePilot — painel pro dono da aplicação (não
necessariamente um engenheiro de observabilidade) acompanhar investigações,
disparar uma nova a partir de um relato em linguagem natural, e aprofundar
na evidência bruta por trás de cada diagnóstico.

Roda como um serviço separado do `demo_app` (que é só o alvo investigado) e
do grafo de agentes (chamado em background thread a cada investigação).
"""
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agents import report_store, workspace_store
from agents.orchestrator import run_investigation
from agents.tools.openobserve_client import OpenObserveClient
from agents.tools import resource_snapshot as resource_snapshot_tool
from agents.tools import github_inspector
from webapp import monitoring

BASE_DIR = Path(__file__).resolve().parent
DEMO_APP_URL = os.getenv("DEMO_APP_URL", "http://localhost:8099")
OPENOBSERVE_UI_URL = os.getenv("OPENOBSERVE_URL", "http://localhost:5080")

COOKIE_NAME = "tp_name"
COOKIE_EMAIL = "tp_email"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 dias

app = FastAPI(title="TracePilot")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _timestamp_to_str(ts: int) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


templates.env.filters["timestamp_to_str"] = _timestamp_to_str
templates.env.filters["format_bytes"] = monitoring.format_bytes


def _current_user(request: Request) -> dict | None:
    email = request.cookies.get(COOKIE_EMAIL)
    if not email:
        return None
    return {"name": request.cookies.get(COOKIE_NAME, ""), "email": email}


templates.env.globals["current_user"] = _current_user


def _require_login(request: Request) -> RedirectResponse | None:
    if _current_user(request) is None:
        return RedirectResponse(url="/login", status_code=303)
    return None


def _require_onboarded(request: Request) -> RedirectResponse | None:
    guard = _require_login(request)
    if guard:
        return guard
    if not workspace_store.is_onboarded():
        return RedirectResponse(url="/onboarding", status_code=303)
    return None


def _onboarding_guard(request: Request) -> RedirectResponse | None:
    """Usado no topo de toda rota /onboarding/* — exige login e, se o
    onboarding já foi concluído, manda direto pro dashboard em vez de
    deixar a pessoa revisitar a jornada por acaso.
    """
    guard = _require_login(request)
    if guard:
        return guard
    if workspace_store.is_onboarded():
        return RedirectResponse(url="/dashboard", status_code=303)
    return None


def _demo_app_status() -> dict:
    started = time.perf_counter()
    try:
        resp = httpx.get(f"{DEMO_APP_URL}/health", timeout=3)
        latency_ms = (time.perf_counter() - started) * 1000
        return {"up": resp.status_code == 200, "url": DEMO_APP_URL, "latency_ms": latency_ms}
    except httpx.HTTPError:
        return {"up": False, "url": DEMO_APP_URL, "latency_ms": None}


def _openobserve_status() -> dict:
    try:
        streams = OpenObserveClient().list_streams()
        return {"up": True, "streams": streams, "url": OPENOBSERVE_UI_URL}
    except Exception:
        return {"up": False, "streams": [], "url": OPENOBSERVE_UI_URL}


DEV_METHOD_LABELS = {
    "ai_assisted": "Vibe coding / com ajuda de IA",
    "no_code": "Plataforma no-code / low-code",
    "traditional": "Desenvolvimento tradicional",
    "other": "Outro",
}
ENVIRONMENT_LABELS = {
    "not_deployed": "Ainda não publicado",
    "local_server": "Servidor local",
    "dedicated_server": "Servidor dedicado",
    "vps": "VPS (nuvem)",
    "production": "Já em produção",
}

MONITORED_SERVICE = os.getenv("MONITORED_SERVICE_NAME", "tracepilot-demo-app")


def _recent_error_count() -> int | None:
    """Erros registrados pelo sistema monitorado na janela recente. `None`
    quando não dá pra saber (OpenObserve fora) — diferente de `0`."""
    try:
        start_us = int((time.time() - monitoring.RECENT_ERRORS_WINDOW_MIN * 60) * 1_000_000)
        hits = OpenObserveClient().query_logs(
            severities=["ERROR", "FATAL", "CRITICAL"],
            service=MONITORED_SERVICE,
            start_time=start_us,
            size=100,
        )
        return len(hits)
    except Exception:
        return None


def _collect_state(snapshot: dict | None = None) -> dict:
    """Coleta todos os sinais e devolve o estado pronto pra tela (ver
    `webapp/monitoring.py`)."""
    snapshot = snapshot or resource_snapshot_tool.get_resource_snapshot()
    openobserve = _openobserve_status()
    return monitoring.build_state(
        profile=workspace_store.load(),
        demo_app=_demo_app_status(),
        openobserve=openobserve,
        snapshot=snapshot,
        agent_reporting=resource_snapshot_tool.agent_is_reporting(snapshot),
        recent_errors=_recent_error_count() if openobserve["up"] else None,
    )


@app.get("/onboarding")
def onboarding_root(request: Request):
    guard = _require_login(request)
    if guard:
        return guard
    if workspace_store.is_onboarded():
        return RedirectResponse(url="/dashboard", status_code=303)
    step = workspace_store.current_step() or "welcome"
    return RedirectResponse(url=f"/onboarding/{step}", status_code=303)


@app.get("/onboarding/welcome")
def onboarding_welcome(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("welcome")
    return templates.TemplateResponse(
        request, "onboarding_welcome.html", {"step_index": 0, "user": _current_user(request)}
    )


@app.get("/onboarding/about")
def onboarding_about_form(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("about")
    return templates.TemplateResponse(
        request, "onboarding_about.html", {"step_index": 1, "profile": workspace_store.load()}
    )


@app.post("/onboarding/about")
def onboarding_about_submit(
    request: Request,
    system_name: str = Form(...),
    objective: str = Form(""),
    dev_method: str = Form(""),
    dev_method_tool: str = Form(""),
    environment: str = Form(""),
    environment_notes: str = Form(""),
):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.update(
        system_name=system_name.strip(),
        objective=objective.strip(),
        dev_method=dev_method,
        dev_method_tool=dev_method_tool.strip(),
        environment=environment,
        environment_notes=environment_notes.strip(),
    )
    return RedirectResponse(url="/onboarding/install", status_code=303)


@app.get("/onboarding/install")
def onboarding_install(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("install")
    return templates.TemplateResponse(request, "onboarding_install.html", {"step_index": 2})


@app.get("/onboarding/repo")
def onboarding_repo_form(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("repo")
    return templates.TemplateResponse(
        request, "onboarding_repo.html", {"step_index": 3, "profile": workspace_store.load()}
    )


@app.post("/onboarding/repo")
def onboarding_repo_submit(request: Request, repo_url: str = Form("")):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    repo_url = repo_url.strip()
    repo_info = github_inspector.inspect_repo(repo_url) if repo_url else None
    workspace_store.update(repo_url=repo_url or None, repo_info=repo_info)
    return RedirectResponse(url="/onboarding/connectivity", status_code=303)


@app.get("/onboarding/connectivity")
def onboarding_connectivity(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("connectivity")
    snapshot = resource_snapshot_tool.get_resource_snapshot()
    return templates.TemplateResponse(
        request,
        "onboarding_connectivity.html",
        {
            "step_index": 4,
            "demo_app": _demo_app_status(),
            "openobserve": _openobserve_status(),
            "agent_reporting": resource_snapshot_tool.agent_is_reporting(snapshot),
        },
    )


@app.get("/onboarding/configuring")
def onboarding_configuring(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("configuring")
    snapshot = resource_snapshot_tool.get_resource_snapshot()
    workspace_store.update(host_snapshot=snapshot)
    profile = workspace_store.load()
    return templates.TemplateResponse(
        request,
        "onboarding_configuring.html",
        {
            "step_index": 5,
            "snapshot": snapshot,
            "state": _collect_state(snapshot),
            "profile": profile,
            "repo_info": profile.get("repo_info"),
            "demo_app": _demo_app_status(),
        },
    )


@app.get("/onboarding/summary")
def onboarding_summary(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("summary")
    profile = workspace_store.load()
    state = _collect_state()
    return templates.TemplateResponse(
        request,
        "onboarding_summary.html",
        {
            "step_index": 6,
            "user": _current_user(request),
            "profile": profile,
            "repo_info": profile.get("repo_info"),
            "dev_method_label": DEV_METHOD_LABELS.get(profile.get("dev_method"), "não informado"),
            "environment_label": ENVIRONMENT_LABELS.get(profile.get("environment"), "não informado"),
            "state": state,
        },
    )


@app.post("/onboarding/complete")
def onboarding_complete(request: Request):
    guard = _require_login(request)
    if guard:
        return guard
    workspace_store.mark_onboarding_complete()
    return RedirectResponse(url="/dashboard", status_code=303)


@app.post("/onboarding/reset")
def onboarding_reset(request: Request):
    guard = _require_login(request)
    if guard:
        return guard
    workspace_store.reset_onboarding()
    return RedirectResponse(url="/onboarding", status_code=303)


@app.get("/login")
def login_form(request: Request):
    if _current_user(request) is not None:
        target = "/dashboard" if workspace_store.is_onboarded() else "/onboarding"
        return RedirectResponse(url=target, status_code=303)
    return templates.TemplateResponse(request, "login.html", {})


@app.post("/login")
def login_submit(name: str = Form(...), email: str = Form(...)):
    name, email = name.strip(), email.strip()
    if not name or not email:
        return RedirectResponse(url="/login", status_code=303)
    workspace_store.update(user={"name": name, "email": email})
    target = "/dashboard" if workspace_store.is_onboarded() else "/onboarding"
    response = RedirectResponse(url=target, status_code=303)
    response.set_cookie(COOKIE_NAME, name, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax")
    response.set_cookie(COOKIE_EMAIL, email, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax")
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    response.delete_cookie(COOKIE_EMAIL)
    return response


@app.get("/")
def landing(request: Request):
    return templates.TemplateResponse(
        request,
        "landing.html",
        {"user": _current_user(request), "example": monitoring.example_state()},
    )


def _dashboard_context(request: Request) -> dict:
    profile = workspace_store.load()
    return {
        "user": _current_user(request),
        "profile": profile,
        "state": _collect_state(),
        "investigations": report_store.list_all(),
        "openobserve_url": OPENOBSERVE_UI_URL,
        "monitored_service": MONITORED_SERVICE,
    }


@app.get("/dashboard")
def dashboard(request: Request):
    guard = _require_onboarded(request)
    if guard:
        return guard
    return templates.TemplateResponse(request, "dashboard.html", _dashboard_context(request))


@app.get("/dashboard/live", response_class=HTMLResponse)
def dashboard_live(request: Request):
    """Só o miolo que muda (status geral, indicadores, diagrama, alertas)
    — o JS do dashboard troca esse pedaço a cada poucos segundos."""
    if _current_user(request) is None:
        return HTMLResponse("", status_code=401)
    return templates.TemplateResponse(request, "_dashboard_live.html", _dashboard_context(request))


@app.get("/api/dashboard")
def dashboard_api(request: Request):
    if _current_user(request) is None:
        return {"error": "login necessário"}
    return _collect_state()


@app.post("/investigations")
def create_investigation(
    request: Request,
    error_report: str = Form(...),
    service: str = Form(MONITORED_SERVICE),
):
    guard = _require_login(request)
    if guard:
        return guard
    investigation_id = report_store.new_investigation_id()
    thread = threading.Thread(
        target=run_investigation,
        kwargs={
            "error_report": error_report,
            "service": service,
            "investigation_id": investigation_id,
        },
        daemon=True,
    )
    thread.start()
    return RedirectResponse(url=f"/investigations/{investigation_id}", status_code=303)


@app.get("/investigations/{investigation_id}")
def investigation_detail(request: Request, investigation_id: str):
    guard = _require_login(request)
    if guard:
        return guard
    record = report_store.load(investigation_id)
    return templates.TemplateResponse(
        request,
        "detail.html",
        {"investigation": record, "investigation_id": investigation_id},
    )


@app.get("/api/investigations/{investigation_id}")
def investigation_status(investigation_id: str):
    return report_store.load(investigation_id) or {"status": "not_found"}


@app.get("/api/health")
def health():
    return {"demo_app": _demo_app_status(), "openobserve": _openobserve_status()}
