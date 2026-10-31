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
from agents.tools import security_scan
from agents.tools import traffic_guard
from webapp import auth, monitoring, presets

BASE_DIR = Path(__file__).resolve().parent
DEMO_APP_URL = os.getenv("DEMO_APP_URL", "http://localhost:8099")
OPENOBSERVE_UI_URL = os.getenv("OPENOBSERVE_URL", "http://localhost:5080")
MONITORED_SERVICE = os.getenv("MONITORED_SERVICE_NAME", "tracepilot-demo-app")
# TracePilot API (ingest/): endereço interno para o health check e o
# público mostrado na tela de instalação.
INGEST_URL = os.getenv("TRACEPILOT_INGEST_URL", "http://localhost:8810").rstrip("/")
INGEST_PUBLIC_URL = os.getenv("TRACEPILOT_INGEST_PUBLIC_URL", INGEST_URL).rstrip("/")
OTLP_HTTP_PUBLIC_URL = os.getenv("TRACEPILOT_OTLP_PUBLIC_URL", "http://localhost:4318").rstrip("/")

COOKIE_SESSION = "tp_session"
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
    return auth.user_from_token(request.cookies.get(COOKIE_SESSION))


templates.env.globals["current_user"] = _current_user
templates.env.globals["active_preset"] = presets.active


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


def _app_url() -> str:
    """URL do sistema monitorado: a informada no onboarding, senão a do
    preset ativo, senão `DEMO_APP_URL`."""
    profile = workspace_store.load()
    preset = presets.active() or {}
    return (profile.get("app_url") or preset.get("app_url") or DEMO_APP_URL).rstrip("/")


def _monitored_services() -> list[str]:
    """Serviço principal primeiro (é o padrão das investigações), depois
    os relacionados — todos entram na contagem de erros recentes."""
    profile = workspace_store.load()
    preset = presets.active() or {}
    main = profile.get("service_name") or preset.get("service_name") or MONITORED_SERVICE
    related = profile.get("related_services") or preset.get("related_services") or []
    return [main] + [s for s in related if s != main]


def _demo_app_status() -> dict:
    """Sobe = responde 2xx em `/health` (convenção dos nossos serviços) ou,
    se essa rota não existir, na raiz."""
    url = _app_url()
    started = time.perf_counter()
    try:
        resp = httpx.get(f"{url}/health", timeout=3)
        if resp.status_code == 404:
            resp = httpx.get(url or "/", timeout=3)
        latency_ms = (time.perf_counter() - started) * 1000
        return {"up": resp.is_success, "url": url, "latency_ms": latency_ms}
    except httpx.HTTPError:
        return {"up": False, "url": url, "latency_ms": None}


def _openobserve_status() -> dict:
    """Uma falha isolada (timeout, OpenObserve ocupado) não basta para
    declarar o armazenamento fora do ar — tenta de novo antes."""
    for attempt in range(2):
        try:
            streams = OpenObserveClient().list_streams()
            return {"up": True, "streams": streams, "url": OPENOBSERVE_UI_URL}
        except Exception:
            if attempt == 0:
                time.sleep(0.3)
    return {"up": False, "streams": [], "url": OPENOBSERVE_UI_URL}


def _ingest_api_status() -> dict:
    try:
        resp = httpx.get(f"{INGEST_URL}/v1/health", timeout=2)
        return {"up": resp.is_success, "url": INGEST_PUBLIC_URL}
    except httpx.HTTPError:
        return {"up": False, "url": INGEST_PUBLIC_URL}


DEV_METHOD_LABELS = {
    "ai_assisted": "Com IA",
    "no_code": "No-code",
    "traditional": "Programado à mão",
}
ENVIRONMENT_LABELS = {
    "local_server": "Meu computador",
    "vps": "VPS / nuvem",
    "dedicated_server": "Servidor próprio",
    "not_deployed": "Ainda não publicado",
}

def _recent_error_count() -> int | None:
    """Erros registrados pelo sistema monitorado na janela recente. `None`
    quando não dá pra saber (OpenObserve fora) — diferente de `0`."""
    try:
        start_us = int((time.time() - monitoring.RECENT_ERRORS_WINDOW_MIN * 60) * 1_000_000)
        client = OpenObserveClient()
        return sum(
            len(
                client.query_logs(
                    severities=["ERROR", "FATAL", "CRITICAL"],
                    service=service,
                    start_time=start_us,
                    size=100,
                )
            )
            for service in _monitored_services()
        )
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
        sources=_telemetry_sources() if openobserve["up"] else None,
        api_service=_ingest_api_status(),
        threats=_traffic_threats() if openobserve["up"] else None,
        security=workspace_store.load().get("security_scan"),
    )


def _traffic_threats() -> dict | None:
    """Só o serviço de entrada (o que recebe tráfego de fora): os demais
    são chamados por ele, e o user-agent interno viraria falso "robô"."""
    try:
        requests = OpenObserveClient().recent_http_requests(
            _monitored_services()[:1],
            minutes=monitoring.RECENT_ERRORS_WINDOW_MIN,
            exclude_agents=traffic_guard.ALLOWED_AGENTS,
        )
        return traffic_guard.analyze(requests)
    except Exception:
        return None


def _run_security_scan() -> dict:
    profile = workspace_store.load()
    result = security_scan.scan(app_url=_app_url(), repo_path=profile.get("repo_local_path"))
    for f in result["findings"]:
        f["prompt"] = security_scan.fix_prompt(f, profile.get("system_name"))
    workspace_store.update(security_scan=result)
    return result


def _telemetry_sources() -> dict | None:
    try:
        return OpenObserveClient().recent_sources(
            _monitored_services(), minutes=monitoring.RECENT_ERRORS_WINDOW_MIN
        )
    except Exception:
        return None


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
        request,
        "onboarding_welcome.html",
        {
            "step_index": 0,
            "user": _current_user(request),
            "system_name": presets.form_values(workspace_store.load()).get("system_name"),
        },
    )


@app.get("/onboarding/about")
def onboarding_about_form(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("about")
    return templates.TemplateResponse(
        request,
        "onboarding_about.html",
        {"step_index": 1, "form": presets.form_values(workspace_store.load())},
    )


@app.post("/onboarding/about")
def onboarding_about_submit(
    request: Request,
    system_name: str = Form(...),
    objective: str = Form(""),
    dev_method: str = Form(""),
    environment: str = Form(""),
    app_url: str = Form(""),
    service_name: str = Form(""),
):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.update(
        system_name=system_name.strip(),
        objective=objective.strip(),
        dev_method=dev_method,
        environment=environment,
        app_url=app_url.strip().rstrip("/") or None,
        service_name=service_name.strip() or None,
    )
    # Serviços relacionados não têm campo no formulário (detalhe técnico
    # demais pra jornada); vêm do preset quando o serviço principal bate.
    preset = presets.active() or {}
    if preset and service_name.strip() == preset.get("service_name"):
        workspace_store.update(related_services=preset.get("related_services", []))
    return RedirectResponse(url="/onboarding/install", status_code=303)


@app.get("/onboarding/install")
def onboarding_install(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("install")
    preset = presets.active() or {}
    return templates.TemplateResponse(
        request,
        "onboarding_install.html",
        {
            "step_index": 2,
            "preset": preset,
            "otlp_endpoint": preset.get("otlp_endpoint", "SEU-COLETOR:4317"),
            "ingest_url": INGEST_PUBLIC_URL,
            "otlp_http_url": OTLP_HTTP_PUBLIC_URL,
            "service_name": _monitored_services()[0],
        },
    )


@app.get("/onboarding/repo")
def onboarding_repo_form(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("repo")
    return templates.TemplateResponse(
        request,
        "onboarding_repo.html",
        {"step_index": 3, "form": presets.form_values(workspace_store.load())},
    )


@app.post("/onboarding/repo")
def onboarding_repo_submit(request: Request, repo_url: str = Form("")):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    repo_url = repo_url.strip()
    local_path = None
    preset = presets.active() or {}
    if repo_url and preset.get("repo_local_path") and repo_url.rstrip("/") == preset.get("repo_url", "").rstrip("/"):
        local_path = str(BASE_DIR.parent / preset["repo_local_path"])
    repo_info = github_inspector.inspect_repo(repo_url, local_path=local_path) if repo_url else None
    workspace_store.update(repo_url=repo_url or None, repo_info=repo_info, repo_local_path=local_path)
    return RedirectResponse(url="/onboarding/connectivity", status_code=303)


@app.get("/onboarding/connectivity")
def onboarding_connectivity(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("connectivity")
    return templates.TemplateResponse(
        request, "onboarding_connectivity.html", {"step_index": 4, "state": _collect_state()}
    )


@app.get("/onboarding/configuring")
def onboarding_configuring(request: Request):
    guard = _onboarding_guard(request)
    if guard:
        return guard
    workspace_store.set_current_step("configuring")
    snapshot = resource_snapshot_tool.get_resource_snapshot()
    workspace_store.update(host_snapshot=snapshot)
    _run_security_scan()
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
    # ?tour=1 abre o guia do painel na primeira visita.
    return RedirectResponse(url="/dashboard?tour=1", status_code=303)


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
    return templates.TemplateResponse(request, "login.html", _login_context())


def _login_context(email: str | None = None, error: str | None = None) -> dict:
    """Preenche o login no modo demo: e-mail do perfil (ou do preset) e,
    se a conta ainda não tem senha ou é a conta do preset, a senha do
    preset — assim a demo é só clicar em Entrar."""
    profile_user = workspace_store.load().get("user") or {}
    preset_user = (presets.active() or {}).get("user") or {}
    prefill_email = email or profile_user.get("email") or preset_user.get("email", "")
    prefill_password = ""
    if preset_user.get("password") and not error and (
        not auth.has_account() or prefill_email == preset_user.get("email")
    ):
        prefill_password = preset_user["password"]
    return {
        "prefill_email": prefill_email,
        "prefill_password": prefill_password,
        "first_access": not auth.has_account(),
        "error": error,
    }


@app.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    user = auth.authenticate(email, password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            _login_context(email=email.strip(), error="E-mail ou senha incorretos."),
            status_code=401,
        )
    target = "/dashboard" if workspace_store.is_onboarded() else "/onboarding"
    response = RedirectResponse(url=target, status_code=303)
    response.set_cookie(
        COOKIE_SESSION, auth.session_token(user["email"]),
        max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax",
    )
    return response


@app.post("/logout")
def logout():
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(COOKIE_SESSION)
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
        "monitored_service": _monitored_services()[0],
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


@app.post("/security/scan")
def security_rescan(request: Request):
    guard = _require_login(request)
    if guard:
        return guard
    _run_security_scan()
    return RedirectResponse(url="/dashboard#vulnerabilidades", status_code=303)


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
