from __future__ import annotations

import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


_INITIALIZED = False


def init_telemetry(app: Optional[object] = None) -> trace.Tracer:
    global _INITIALIZED
    if _INITIALIZED:
        return trace.get_tracer(os.getenv("OTEL_SERVICE_NAME", "per-customer-ai-cost-radar"))

    service_name = os.getenv("OTEL_SERVICE_NAME", "per-customer-ai-cost-radar")
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    if app is not None:
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)

    _INITIALIZED = True
    return trace.get_tracer(service_name)
