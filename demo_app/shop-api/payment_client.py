"""Cliente do payment-service. Em produção o tráfego passa pelo toxiproxy
(PAYMENT_URL), que representa a rede entre os serviços.
"""
import os
import time
from functools import cache

import httpx
from opentelemetry import metrics

import faults

PAYMENT_URL = os.getenv("PAYMENT_URL", "http://localhost:8666")
PAYMENT_TIMEOUT_S = float(os.getenv("PAYMENT_TIMEOUT_S", "1.0"))

meter = metrics.get_meter("shop")
payment_duration = meter.create_histogram(
    "payment.client.duration",
    unit="ms",
    description="Duração das chamadas do shop-api ao payment-service (uma por tentativa)",
)


@cache
def _client() -> httpx.Client:
    return httpx.Client(base_url=PAYMENT_URL, timeout=PAYMENT_TIMEOUT_S)


def _authorize_once(order_ref: str, amount_cents: int, attempt: int) -> dict:
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
    except httpx.HTTPStatusError:
        outcome = "http_error"
        raise
    finally:
        payment_duration.record((time.perf_counter() - started) * 1000, {"outcome": outcome, "attempt": attempt})


def _is_retryable(exc: httpx.HTTPError) -> bool:
    return not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code >= 500


def authorize(order_ref: str, amount_cents: int) -> dict:
    # Flag payment_retry_no_backoff: retry imediato, sem backoff nem jitter,
    # que multiplica a carga sobre um payment-service já lento.
    config = faults.registry.config(faults.PAYMENT_RETRY_NO_BACKOFF)
    attempts = int(config.get("attempts", 5)) if config is not None else 1
    for attempt in range(1, attempts + 1):
        try:
            return _authorize_once(order_ref, amount_cents, attempt)
        except httpx.HTTPError as exc:
            if attempt == attempts or not _is_retryable(exc):
                raise
    raise AssertionError("unreachable")
