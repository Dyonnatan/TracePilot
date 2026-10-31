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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from agents import report_store
from agents.orchestrator import run_investigation
from agents.tools.openobserve_client import OpenObserveClient

BASE_DIR = Path(__file__).resolve().parent
DEMO_APP_URL = os.getenv("DEMO_APP_URL", "http://localhost:8088")
OPENOBSERVE_UI_URL = os.getenv("OPENOBSERVE_URL", "http://localhost:5080")

app = FastAPI(title="TracePilot")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _timestamp_to_str(ts: int) -> str:
    import datetime

    return datetime.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


templates.env.filters["timestamp_to_str"] = _timestamp_to_str


def _demo_app_status() -> dict:
    try:
        resp = httpx.get(f"{DEMO_APP_URL}/health", timeout=3)
        return {"up": resp.status_code == 200, "url": DEMO_APP_URL}
    except httpx.HTTPError:
        return {"up": False, "url": DEMO_APP_URL}


def _openobserve_status() -> dict:
    try:
        streams = OpenObserveClient().list_streams()
        return {"up": True, "streams": streams, "url": OPENOBSERVE_UI_URL}
    except Exception:
        return {"up": False, "streams": [], "url": OPENOBSERVE_UI_URL}


@app.get("/")
def dashboard(request: Request):
    investigations = report_store.list_all()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "investigations": investigations,
            "demo_app": _demo_app_status(),
            "openobserve": _openobserve_status(),
        },
    )


@app.post("/investigations")
def create_investigation(
    error_report: str = Form(...),
    service: str = Form(""),
):
    investigation_id = report_store.new_investigation_id()
    thread = threading.Thread(
        target=run_investigation,
        kwargs={
            "error_report": error_report,
            "service": service.strip() or None,
            "investigation_id": investigation_id,
        },
        daemon=True,
    )
    thread.start()
    return RedirectResponse(url=f"/investigations/{investigation_id}", status_code=303)


@app.get("/investigations/{investigation_id}")
def investigation_detail(request: Request, investigation_id: str):
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
