"""OpenTelemetry wiring — opt-in via the `[otel]` extra.

If the OTel packages aren't installed, `instrument_app` is a no-op. Keeps
the base image small; production deployments install with the extra.
"""

from __future__ import annotations

import os
from typing import Any

import structlog

_log = structlog.get_logger(__name__)


def instrument_app(app: Any) -> None:
    """Instrument a FastAPI app + httpx with OTel exporters, if configured.

    Reads the standard OTLP env vars:
      - OTEL_EXPORTER_OTLP_ENDPOINT
      - OTEL_SERVICE_NAME (defaults to db2st-mcp)
      - OTEL_RESOURCE_ATTRIBUTES
    """
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        _log.info("otel.disabled", reason="OTEL_EXPORTER_OTLP_ENDPOINT unset")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        _log.warning("otel.unavailable", hint="reinstall with the [otel] extra")
        return

    service_name = os.getenv("OTEL_SERVICE_NAME", "db2st-mcp")
    resource = Resource.create({SERVICE_NAME: service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    _log.info("otel.enabled", service_name=service_name)
