"""shop-api: loja do ambiente de referência (frontend, carrinho e checkout).

Depende do Postgres (catálogo, cupons, pedidos) e do payment-service
(autorização de pagamento, acessado via toxiproxy).
"""
import contextvars
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from telemetry import current_trace_id, instrument_app, setup_telemetry

SHOP_VERSION = os.getenv("SHOP_VERSION", "1.0.0")
CHANGELOG = {
    "1.0.0": "versão base da loja",
    "1.1.0": "checkout passa a exibir a economia obtida com o cupom",
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("shop")
setup_telemetry("shop-api", SHOP_VERSION, logger)

import httpx  # noqa: E402
import psycopg  # noqa: E402
from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from opentelemetry import metrics, trace  # noqa: E402
from opentelemetry.trace import Status, StatusCode  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402

import db  # noqa: E402
import payment_client  # noqa: E402
import pricing  # noqa: E402

STATIC_DIR = Path(__file__).parent / "static"

tracer = trace.get_tracer("shop")
meter = metrics.get_meter("shop")
checkout_requests = meter.create_counter(
    "shop.checkout.requests", description="Tentativas de checkout por resultado (atributo outcome)"
)
checkout_duration = meter.create_histogram(
    "shop.checkout.duration", unit="ms", description="Duração do checkout por resultado"
)

session_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_id", default=None)


class SessionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        session_id = session_id_var.get()
        if session_id and not hasattr(record, "session.id"):
            setattr(record, "session.id", session_id)
        return True


logger.addFilter(SessionFilter())


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info(
        "change.event deploy shop-api %s: %s",
        SHOP_VERSION,
        CHANGELOG.get(SHOP_VERSION, "sem changelog"),
        extra={
            "event_type": "change.event",
            "change.type": "deploy",
            "change.service": "shop-api",
            "change.version": SHOP_VERSION,
        },
    )
    yield


app = FastAPI(title="TracePilot Reference Shop", version=SHOP_VERSION, lifespan=lifespan)


@app.middleware("http")
async def session_context(request: Request, call_next):
    session_id = request.headers.get("x-session-id")
    token = session_id_var.set(session_id)
    if session_id:
        trace.get_current_span().set_attribute("session.id", session_id)
    try:
        response = await call_next(request)
    finally:
        session_id_var.reset(token)
    if trace_id := current_trace_id():
        response.headers["X-Trace-Id"] = trace_id
    return response


def _error_response(status_code: int, detail: str, exc: Exception, record_exception: bool = True) -> JSONResponse:
    if record_exception:
        span = trace.get_current_span()
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, f"{type(exc).__name__}: {exc}"))
    trace_id = current_trace_id()
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "trace_id": trace_id},
        headers={"X-Trace-Id": trace_id} if trace_id else None,
    )


def _log_extra(request: Request, event_type: str) -> dict:
    return {"event_type": event_type, "session.id": request.headers.get("x-session-id") or "", "http.route": request.url.path}


class InvalidCoupon(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=422, detail="cupom inválido")


@app.exception_handler(InvalidCoupon)
async def invalid_coupon_handler(_request: Request, exc: InvalidCoupon):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "field": "coupon"})


@app.exception_handler(httpx.TimeoutException)
async def payment_timeout_handler(request: Request, exc: httpx.TimeoutException):
    logger.error(
        "payment.timeout chamada ao payment-service excedeu %.0f ms",
        payment_client.PAYMENT_TIMEOUT_S * 1000,
        extra=_log_extra(request, "payment.timeout"),
    )
    return _error_response(504, "pagamento indisponível", exc)


@app.exception_handler(httpx.TransportError)
async def payment_unavailable_handler(request: Request, exc: httpx.TransportError):
    logger.error("payment.unavailable %s: %s", type(exc).__name__, exc, extra=_log_extra(request, "payment.unavailable"))
    return _error_response(502, "pagamento indisponível", exc)


@app.exception_handler(psycopg.OperationalError)
async def db_unavailable_handler(request: Request, exc: psycopg.OperationalError):
    logger.error("db.unavailable %s: %s", type(exc).__name__, exc, extra=_log_extra(request, "db.unavailable"))
    return _error_response(503, "serviço temporariamente indisponível", exc)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("unhandled.error %s: %s", type(exc).__name__, exc, extra=_log_extra(request, "unhandled.error"))
    # A instrumentação FastAPI já registra exceções não tratadas no span.
    return _error_response(500, "erro interno", exc, record_exception=False)


class CartItem(BaseModel):
    product_id: int = Field(gt=0)
    quantity: int = Field(gt=0, le=20)


class CartRequest(BaseModel):
    items: list[CartItem] = Field(min_length=1, max_length=10)
    coupon: str | None = Field(default=None, max_length=32)
    payment_method: Literal["pix", "card", "boleto"] = "card"

    @field_validator("items")
    @classmethod
    def unique_products(cls, items: list[CartItem]) -> list[CartItem]:
        if len({item.product_id for item in items}) != len(items):
            raise ValueError("produto repetido no carrinho")
        return items


class RumEvent(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    type: str = Field(min_length=1, max_length=40)
    page: str | None = Field(default=None, max_length=200)
    detail: Annotated[dict[str, str | int | float | bool], Field(max_length=10)] = {}


class SupportReport(BaseModel):
    session_id: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=2000)
    trace_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")
    page: str | None = Field(default=None, max_length=200)


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "version": SHOP_VERSION}


@app.get("/products")
def products():
    return db.list_products()


@app.get("/products/{product_id}")
def product(product_id: int):
    found = db.get_product(product_id)
    if found is None:
        raise HTTPException(status_code=404, detail="produto não encontrado")
    return found


@app.post("/cart/quote")
def cart_quote(payload: CartRequest):
    lines, coupon_code, quote = _price_cart(payload)
    return _cart_response(payload, lines, coupon_code, quote)


@app.post("/checkout")
def checkout(payload: CartRequest):
    started = time.perf_counter()
    outcome = "error"
    try:
        result = _checkout(payload)
        outcome = "success"
        return result
    except HTTPException as exc:
        outcome = "rejected" if exc.status_code < 500 else "error"
        raise
    except httpx.TimeoutException:
        outcome = "payment_timeout"
        raise
    except httpx.TransportError:
        outcome = "payment_unavailable"
        raise
    except psycopg.OperationalError:
        outcome = "db_unavailable"
        raise
    finally:
        attributes = {"outcome": outcome, "service.version": SHOP_VERSION}
        checkout_requests.add(1, attributes)
        checkout_duration.record((time.perf_counter() - started) * 1000, attributes)


def _price_cart(payload: CartRequest) -> tuple[list[dict], str | None, dict]:
    """Valida produtos e cupom e calcula o preço. Usado pelo carrinho e pelo checkout."""
    products_by_id = db.get_products([item.product_id for item in payload.items])
    lines = []
    for item in payload.items:
        found = products_by_id.get(item.product_id)
        if found is None:
            raise HTTPException(status_code=404, detail="produto não encontrado")
        if found["stock"] == 0:
            raise HTTPException(status_code=409, detail="produto esgotado")
        if item.quantity > found["stock"]:
            raise HTTPException(status_code=409, detail="estoque insuficiente")
        lines.append(
            {
                "product_id": found["id"],
                "name": found["name"],
                "image": found["image"],
                "quantity": item.quantity,
                "unit_price_cents": found["price_cents"],
            }
        )

    coupon_code = payload.coupon.strip().upper() if payload.coupon and payload.coupon.strip() else None
    discount_pct = 0
    if coupon_code:
        coupon = db.get_coupon(coupon_code)
        if coupon is None:
            raise InvalidCoupon()
        discount_pct = coupon["discount_pct"]

    with tracer.start_as_current_span("pricing.quote") as span:
        span.set_attributes(
            {
                "coupon.code": coupon_code or "",
                "coupon.discount_pct": discount_pct,
                "payment.method": payload.payment_method,
                "cart.items": len(lines),
            }
        )
        quote = pricing.quote(
            [(line["unit_price_cents"], line["quantity"]) for line in lines],
            discount_pct,
            payload.payment_method,
            SHOP_VERSION,
        )
    return lines, coupon_code, quote


def _cart_response(payload: CartRequest, lines: list[dict], coupon_code: str | None, quote: dict) -> dict:
    return {
        "items": [{**line, "line_total_cents": line["unit_price_cents"] * line["quantity"]} for line in lines],
        "coupon": coupon_code,
        "payment_method": payload.payment_method,
        "free_shipping_threshold_cents": pricing.FREE_SHIPPING_THRESHOLD_CENTS,
        **quote,
    }


def _checkout(payload: CartRequest) -> dict:
    lines, coupon_code, quote = _price_cart(payload)

    authorization_id = None
    if quote["total_cents"] > 0:
        authorization = payment_client.authorize(f"ORD-{uuid.uuid4().hex[:12]}", quote["total_cents"])
        authorization_id = authorization["authorization_id"]

    order_id = db.create_order(
        lines, coupon_code, payload.payment_method, quote, session_id_var.get(), authorization_id
    )
    logger.info(
        "checkout.success pedido %s total %s centavos",
        order_id,
        quote["total_cents"],
        extra={"event_type": "checkout.success", "order.id": order_id, "payment.method": payload.payment_method},
    )
    return {"order_id": order_id, **_cart_response(payload, lines, coupon_code, quote)}


@app.post("/rum/events", status_code=202)
def rum_event(event: RumEvent):
    logger.info(
        "rum.%s %s",
        event.type,
        event.page or "",
        extra={
            "event_type": "rum.event",
            "session.id": event.session_id,
            "rum.type": event.type,
            "rum.page": event.page or "",
            **{f"rum.{key}": value for key, value in event.detail.items()},
        },
    )
    return {"accepted": True}


@app.post("/support/report", status_code=201)
def support_report(report: SupportReport):
    ticket = f"TP-{uuid.uuid4().hex[:8].upper()}"
    logger.warning(
        "user.report %s: %s",
        ticket,
        report.message,
        extra={
            "event_type": "user.report",
            "session.id": report.session_id,
            "report.ticket": ticket,
            "report.trace_id": report.trace_id or "",
            "report.page": report.page or "",
        },
    )
    return {"ticket": ticket}


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
instrument_app(app)
