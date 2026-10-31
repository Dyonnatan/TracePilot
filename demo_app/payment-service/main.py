"""payment-service: autorização de pagamento com cálculo de score de fraude
(CPU-bound), chamado pelo shop-api via toxiproxy.
"""
import hashlib
import logging
import os
import random
import uuid
from contextlib import asynccontextmanager

from telemetry import instrument_app, setup_telemetry

SERVICE_VERSION = os.getenv("PAYMENT_VERSION", "1.0.0")
FRAUD_SCORE_ITERATIONS = int(os.getenv("FRAUD_SCORE_ITERATIONS", "200000"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("payment")
setup_telemetry("payment-service", SERVICE_VERSION, logger)

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from opentelemetry import trace  # noqa: E402
from opentelemetry.trace import Status, StatusCode  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from cpu_burn import CpuBurner  # noqa: E402

tracer = trace.get_tracer("payment")
burner = CpuBurner()

ACQUIRER_FAILURE = "acquirer_failure"
KNOWN_FAULTS = frozenset({ACQUIRER_FAILURE})
faults: dict[str, dict] = {}
fault_rng = random.Random()


class AcquirerUnavailable(Exception):
    pass


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    burner.stop()


app = FastAPI(title="TracePilot Payment Service", version=SERVICE_VERSION, lifespan=lifespan)


class AuthorizeRequest(BaseModel):
    order_ref: str = Field(min_length=1, max_length=64)
    amount_cents: int = Field(gt=0)


class CpuBurnRequest(BaseModel):
    enabled: bool
    workers: int = Field(default=2, ge=1, le=8)


class FaultRequest(BaseModel):
    enabled: bool
    config: dict[str, float | int | str] = {}


def fraud_score(order_ref: str, iterations: int) -> float:
    digest = hashlib.pbkdf2_hmac("sha256", order_ref.encode(), b"tracepilot", iterations)
    return round(digest[0] / 255, 3)


@app.get("/health")
def health():
    return {"status": "ok", "version": SERVICE_VERSION}


def charge_acquirer(order_ref: str, amount_cents: int) -> None:
    """Captura na adquirente (simulada). Com acquirer_failure ligada, parte
    das capturas falha como uma adquirente instável.
    """
    with tracer.start_as_current_span("acquirer.charge") as span:
        span.set_attributes({"acquirer.name": "acquirer-br", "order.ref": order_ref, "payment.amount_cents": amount_cents})
        fault = faults.get(ACQUIRER_FAILURE)
        if fault is not None and fault_rng.random() < float(fault.get("rate", 0.3)):
            exc = AcquirerUnavailable("adquirente acquirer-br respondeu 503 Service Unavailable")
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise exc


@app.post("/authorize")
def authorize(payload: AuthorizeRequest):
    with tracer.start_as_current_span("fraud.score") as span:
        score = fraud_score(payload.order_ref, FRAUD_SCORE_ITERATIONS)
        span.set_attribute("fraud.score", score)

    try:
        charge_acquirer(payload.order_ref, payload.amount_cents)
    except AcquirerUnavailable as exc:
        logger.error(
            "acquirer.unavailable %s: %s",
            payload.order_ref,
            exc,
            extra={"event_type": "acquirer.unavailable", "order.ref": payload.order_ref, "acquirer.name": "acquirer-br"},
        )
        status = int(faults.get(ACQUIRER_FAILURE, {}).get("status", 503))
        return JSONResponse(status_code=status, content={"detail": "adquirente indisponível"})

    authorization_id = f"AUTH-{uuid.uuid4().hex[:10].upper()}"
    logger.info(
        "payment.authorized %s %s centavos",
        payload.order_ref,
        payload.amount_cents,
        extra={"event_type": "payment.authorized", "order.ref": payload.order_ref, "fraud.score": score},
    )
    return {"authorized": True, "authorization_id": authorization_id, "fraud_score": score}


@app.get("/internal/cpu-burn")
def cpu_burn_status():
    return {"enabled": burner.workers > 0, "workers": burner.workers}


@app.post("/internal/cpu-burn")
def cpu_burn(payload: CpuBurnRequest):
    if payload.enabled:
        burner.start(payload.workers)
    else:
        burner.stop()
    return {"enabled": burner.workers > 0, "workers": burner.workers}


def _describe_fault(name: str) -> dict:
    return {"name": name, "enabled": name in faults, "config": faults.get(name, {})}


@app.get("/internal/faults")
def list_faults():
    return [_describe_fault(name) for name in sorted(KNOWN_FAULTS)]


@app.post("/internal/faults/{name}")
def set_fault(name: str, payload: FaultRequest):
    if name not in KNOWN_FAULTS:
        raise HTTPException(status_code=404, detail=f"flag desconhecida: {name}")
    if payload.enabled:
        faults[name] = dict(payload.config)
    else:
        faults.pop(name, None)
    return _describe_fault(name)


instrument_app(app)
