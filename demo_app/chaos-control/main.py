"""chaos-control: painel do apresentador para ligar/desligar as falhas do
ambiente de referência. Propositalmente sem OpenTelemetry: a injeção de
falha não pode aparecer na telemetria que os agentes investigam.
"""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from drivers import (
    CompositeDriver,
    CpuBurnDriver,
    DeployDriver,
    Driver,
    FaultFlagDriver,
    ManualActionRequired,
    PgIndexDriver,
    PgLockDriver,
    ToxiproxyDriver,
)
from runner import ScenarioRunner, UnknownScenario
from scenarios import load_scenarios

SCENARIOS_DIR = Path(os.getenv("SCENARIOS_DIR", Path(__file__).parent.parent / "scenarios"))
TOXIPROXY_URL = os.getenv("TOXIPROXY_URL", "http://localhost:8474")
PAYMENT_INTERNAL_URL = os.getenv("PAYMENT_INTERNAL_URL", "http://localhost:8001")
SHOP_INTERNAL_URL = os.getenv("SHOP_INTERNAL_URL", "http://localhost:8081")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://shop:shop@localhost:5432/shop")
STATIC_DIR = Path(__file__).parent / "static"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def build_drivers() -> dict[str, Driver]:
    drivers: dict[str, Driver] = {
        "toxiproxy": ToxiproxyDriver(httpx.Client(base_url=TOXIPROXY_URL, timeout=5)),
        "pg_lock": PgLockDriver(DATABASE_URL),
        "cpu_burn": CpuBurnDriver(httpx.Client(base_url=PAYMENT_INTERNAL_URL, timeout=10)),
        "deploy": DeployDriver(),
        "fault_flag": FaultFlagDriver(
            {
                "shop": httpx.Client(base_url=SHOP_INTERNAL_URL, timeout=5),
                "payment": httpx.Client(base_url=PAYMENT_INTERNAL_URL, timeout=5),
            }
        ),
        "pg_index": PgIndexDriver(DATABASE_URL),
    }
    drivers["composite"] = CompositeDriver(drivers)
    return drivers


def build_runner() -> ScenarioRunner:
    return ScenarioRunner(load_scenarios(SCENARIOS_DIR), build_drivers())


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "runner"):
        app.state.runner = build_runner()
    app.state.runner.reset_all()
    yield
    app.state.runner.reset_all()


app = FastAPI(title="TracePilot Chaos Control", lifespan=lifespan)


class EnableRequest(BaseModel):
    ttl_seconds: int | None = Field(default=None, ge=5, le=3600)


def _run(action, name: str, *args):
    try:
        return action(name, *args)
    except UnknownScenario:
        raise HTTPException(status_code=404, detail=f"cenário desconhecido: {name}")
    except ManualActionRequired as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (httpx.HTTPError, psycopg.Error) as exc:
        raise HTTPException(status_code=502, detail=f"falha ao aplicar cenário: {type(exc).__name__}: {exc}")


@app.get("/")
def admin_page():
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/scenarios")
def list_scenarios():
    return app.state.runner.status()


@app.post("/api/scenarios/{name}/enable")
def enable_scenario(name: str, payload: EnableRequest | None = None):
    return _run(app.state.runner.enable, name, payload.ttl_seconds if payload else None)


@app.post("/api/scenarios/{name}/disable")
def disable_scenario(name: str):
    return _run(app.state.runner.disable, name)
