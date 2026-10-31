"""OpenTelemetry do payment-service: traces, métricas e logs exportados via
OTLP gRPC para o otel-collector compartilhado (endpoint em
OTEL_EXPORTER_OTLP_ENDPOINT).
"""
import logging
import os

from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# /internal/* é o canal do chaos-control: não pode aparecer na telemetria.
EXCLUDED_URLS = "health,internal"


def telemetry_enabled() -> bool:
    return os.getenv("OTEL_SDK_DISABLED", "false").lower() != "true"


def setup_telemetry(service_name: str, service_version: str, app_logger: logging.Logger) -> None:
    if not telemetry_enabled():
        return

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": service_version,
            "deployment.environment.name": os.getenv("DEPLOYMENT_ENVIRONMENT", "demo"),
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    reader = PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=10_000)
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)
    app_logger.addHandler(LoggingHandler(logger_provider=logger_provider, log_code_attributes=True))


def instrument_app(app: FastAPI) -> None:
    if telemetry_enabled():
        FastAPIInstrumentor.instrument_app(app, excluded_urls=EXCLUDED_URLS, exclude_spans=["receive", "send"])
