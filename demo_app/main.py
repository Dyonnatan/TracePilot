"""App de teste instrumentada com OpenTelemetry, usada para gerar os
cenários de falha controlada que o TracePilot vai investigar.

Falha controlada: POST /checkout com quantity <= 0 dispara um
ZeroDivisionError proposital (simula um bug real de cálculo de preço
unitário), reproduzível e determinístico.
"""
import logging
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "tracepilot-demo-app")
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
RESOURCE = Resource.create({"service.name": SERVICE_NAME})

provider = TracerProvider(resource=RESOURCE)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)

# Logs: exportados via OTLP para o mesmo Collector, para o logs_agent ter
# dado real (correlacionado por trace_id/span_id, já que emitidos dentro de
# um span ativo).
logger_provider = LoggerProvider(resource=RESOURCE)
logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True))
)
set_logger_provider(logger_provider)
logging.getLogger().addHandler(LoggingHandler(logger_provider=logger_provider))
log = logging.getLogger("tracepilot.demo_app")

app = FastAPI(title="TracePilot Demo App")
FastAPIInstrumentor.instrument_app(app)

# "Banco de dados" em memória, só para o demo.
ORDERS = {
    "1": {"item": "teclado mecânico", "unit_price": 350.0},
    "2": {"item": "mouse", "unit_price": 120.0},
}


class CheckoutRequest(BaseModel):
    order_id: str
    quantity: int
    budget: float


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/orders/{order_id}")
def get_order(order_id: str):
    order = ORDERS.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="pedido não encontrado")
    return order


@app.post("/checkout")
def checkout(payload: CheckoutRequest):
    log.info("checkout iniciado order_id=%s quantity=%s", payload.order_id, payload.quantity)

    order = ORDERS.get(payload.order_id)
    if order is None:
        log.warning("checkout falhou: pedido não encontrado order_id=%s", payload.order_id)
        raise HTTPException(status_code=404, detail="pedido não encontrado")

    try:
        with tracer.start_as_current_span("calcular_preco_unitario_efetivo"):
            # Falha controlada e reproduzível: dividir o orçamento pela
            # quantidade quebra com quantity = 0 (bug proposital, para o
            # TracePilot investigar a partir do traceback + traces).
            preco_unitario_efetivo = payload.budget / payload.quantity
    except ZeroDivisionError:
        log.error(
            "checkout falhou ao calcular preço unitário order_id=%s quantity=%s",
            payload.order_id,
            payload.quantity,
            exc_info=True,
        )
        raise

    total = preco_unitario_efetivo * payload.quantity
    log.info("checkout concluído order_id=%s total=%s", payload.order_id, total)
    return {"order_id": payload.order_id, "total": total}
