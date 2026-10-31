"""payment-service: autorização de pagamento com cálculo de score de fraude
(CPU-bound), chamado pelo shop-api via toxiproxy.
"""
import hashlib
import logging
import os
import uuid
from contextlib import asynccontextmanager

from telemetry import instrument_app, setup_telemetry

SERVICE_VERSION = os.getenv("PAYMENT_VERSION", "1.0.0")
FRAUD_SCORE_ITERATIONS = int(os.getenv("FRAUD_SCORE_ITERATIONS", "200000"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("payment")
setup_telemetry("payment-service", SERVICE_VERSION, logger)

from fastapi import FastAPI  # noqa: E402
from opentelemetry import trace  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from cpu_burn import CpuBurner  # noqa: E402

tracer = trace.get_tracer("payment")
burner = CpuBurner()


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


def fraud_score(order_ref: str, iterations: int) -> float:
    digest = hashlib.pbkdf2_hmac("sha256", order_ref.encode(), b"tracepilot", iterations)
    return round(digest[0] / 255, 3)


@app.get("/health")
def health():
    return {"status": "ok", "version": SERVICE_VERSION}


@app.post("/authorize")
def authorize(payload: AuthorizeRequest):
    with tracer.start_as_current_span("fraud.score") as span:
        score = fraud_score(payload.order_ref, FRAUD_SCORE_ITERATIONS)
        span.set_attribute("fraud.score", score)

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


instrument_app(app)
