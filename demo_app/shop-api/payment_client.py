"""Cliente do payment-service. Em produção o tráfego passa pelo toxiproxy
(PAYMENT_URL), que representa a rede entre os serviços.
"""
import os
import time
from functools import cache

import httpx
from opentelemetry import metrics

PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8666")
PAYMENT_TIMEOUT_S = float(os.getenv("PAYMENT_TIMEOUT_S", "1.0"))

meter = metrics.get_meter("shop")
payment_duration = meter.create_histogram(
    "payment.client.duration",
    unit="ms",
    description="Duração das chamadas do shop-api ao payment-service",
)


@cache
def _client() -> httpx.Client:
    return httpx.Client(base_url=PAYMENT_URL, timeout=PAYMENT_TIMEOUT_S)


def authorize(order_ref: str, amount_cents: int) -> dict:
    started = time.perf_counter()
    outcome = "error"
    try:
        response = _client().post("/authorize", json={"order_ref": order_ref, "amount_cents": amount_cents})
        response.raise_for_status()
        outcome = "success"
        return response.json()
    except httpx.TimeoutException:
        outcome = "timeout"
        raise
    finally:
        payment_duration.record((time.perf_counter() - started) * 1000, {"outcome": outcome})
