"""OpenTelemetry tracing and metrics — optional, env-gated.

Set OTEL_ENABLED=true to activate. No-op by default.
"""

from __future__ import annotations

import os

from {name}.core.config import settings


def init_telemetry() -> None:
    """Initialize OpenTelemetry if OTEL_ENABLED=true.

    Configures tracing (OTLP exporter) and metrics for the service.
    Falls back gracefully if opentelemetry is not installed.
    """
    if not os.getenv("OTEL_ENABLED", "false").lower() == "true":
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({
            "service.name": f"skyrict-{settings.SERVICE_NAME}" if hasattr(settings, "SERVICE_NAME") else "{name}",
            "service.version": "0.1.0",
            "deployment.environment": settings.ENVIRONMENT.value,
        })

        provider = TracerProvider(resource=resource)
        processor = BatchSpanProcessor(OTLPSpanExporter())
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

    except ImportError:
        import logging
        logging.warning(
            "opentelemetry not installed — telemetry disabled. "
            "Install: pip install opentelemetry-sdk opentelemetry-exporter-otlp"
        )
