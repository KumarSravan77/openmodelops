from __future__ import annotations

import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, TraceState, set_span_in_context

from packages.contracts import FactoryEvent


class TelemetryProvider(str, Enum):
    GENERIC_OTLP = "otlp"
    LANGFUSE = "langfuse"
    PHOENIX = "phoenix"
    OPIK = "opik"


SENSITIVE_KEY = re.compile(r"prompt|input|output|document|context|secret|password|authorization|(?:^|[._])token(?:$|[._])", re.IGNORECASE)
ALLOWED_OPERATIONS = frozenset({"agent", "embedding", "factory", "llm", "policy", "rerank", "retrieval", "tool"})


@dataclass(frozen=True)
class TelemetrySettings:
    service_name: str
    enabled: bool = True
    provider: TelemetryProvider = TelemetryProvider.GENERIC_OTLP
    endpoint: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    project_name: str = "openmodelops"
    capture_content: bool = False

    def exporter_headers(self) -> dict[str, str]:
        headers = dict(self.headers)
        if self.provider == TelemetryProvider.LANGFUSE:
            headers.setdefault("x-langfuse-ingestion-version", "4")
        if self.provider in {TelemetryProvider.PHOENIX, TelemetryProvider.OPIK}:
            headers.setdefault("x-project-name", self.project_name)
        return headers


def trace_context_from_event(event: FactoryEvent):
    trace_id = int(event.trace_id, 16)
    span_id = int(event.event_id.replace("-", "")[-16:], 16)
    context = SpanContext(trace_id, span_id, True, TraceFlags(TraceFlags.SAMPLED), trace_state=TraceState())
    return set_span_in_context(NonRecordingSpan(context))


class Telemetry:
    def __init__(self, settings: TelemetrySettings, *, exporter: SpanExporter | None = None) -> None:
        self.settings = settings
        provider = TracerProvider(resource=Resource.create({"service.name": settings.service_name}))
        if settings.enabled:
            selected = exporter
            if selected is None:
                if not settings.endpoint:
                    raise ValueError("an OTLP endpoint is required when telemetry is enabled")
                selected = OTLPSpanExporter(endpoint=settings.endpoint, headers=settings.exporter_headers())
            processor = SimpleSpanProcessor(selected) if exporter is not None else BatchSpanProcessor(selected)
            provider.add_span_processor(processor)
        self._provider = provider
        self.tracer = provider.get_tracer("openmodelops", "1.0")

    def shutdown(self) -> None:
        self._provider.shutdown()

    @contextmanager
    def operation(
        self,
        operation: str,
        *,
        attributes: dict[str, Any] | None = None,
        parent_context=None,
    ) -> Iterator[trace.Span]:
        if operation not in ALLOWED_OPERATIONS:
            raise ValueError(f"unsupported telemetry operation: {operation}")
        safe = self._safe_attributes(attributes or {})
        safe["openinference.span.kind"] = operation.upper()
        with self.tracer.start_as_current_span(f"openmodelops.{operation}", context=parent_context, attributes=safe) as span:
            try:
                yield span
                span.set_attribute("openmodelops.outcome", "success")
            except Exception as exc:
                span.record_exception(exc, attributes={"exception.message": "operation failed"})
                span.set_attribute("openmodelops.outcome", "error")
                raise

    def _safe_attributes(self, attributes: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in attributes.items():
            if SENSITIVE_KEY.search(key) and not key.endswith(".digest") and not self.settings.capture_content:
                continue
            if value is None:
                continue
            if isinstance(value, (str, bool, int, float)) or isinstance(value, (list, tuple)) and all(isinstance(item, (str, bool, int, float)) for item in value):
                safe[key] = value
        return safe


class OpikTelemetry:
    """Native Opik SDK adapter; content capture remains disabled by default."""

    def __init__(self, settings: TelemetrySettings, *, sdk=None) -> None:
        if sdk is None:
            try:
                import opik as sdk
            except ImportError as exc:
                raise RuntimeError("install the 'observability' extra to enable Opik") from exc
        self.settings = settings
        self.sdk = sdk
        self._sanitizer = Telemetry(TelemetrySettings(settings.service_name, enabled=False))

    @contextmanager
    def operation(self, operation: str, *, attributes: dict[str, Any] | None = None, parent_context=None):
        if parent_context is not None:
            raise ValueError("Opik parent context must be propagated through its SDK context")
        if operation not in ALLOWED_OPERATIONS:
            raise ValueError(f"unsupported telemetry operation: {operation}")
        span_type = operation if operation in {"llm", "tool"} else "general"
        metadata = self._sanitizer._safe_attributes(attributes or {})
        with self.sdk.start_as_current_span(
            f"openmodelops.{operation}",
            type=span_type,
            project_name=self.settings.project_name,
            metadata=metadata,
            flush=False,
        ) as span:
            yield span

    def shutdown(self) -> None:
        flush = getattr(self.sdk, "flush_tracker", None)
        if flush:
            flush()


def telemetry_from_environment(service_name: str) -> Telemetry | OpikTelemetry | None:
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "").strip()
    if not endpoint:
        return None
    provider = TelemetryProvider(os.getenv("OPENMODELOPS_TELEMETRY_PROVIDER", "otlp"))
    headers = {}
    raw_headers = os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")
    for item in filter(None, raw_headers.split(",")):
        key, separator, value = item.partition("=")
        if not separator:
            raise ValueError("OTEL_EXPORTER_OTLP_HEADERS must use key=value entries")
        headers[key.strip()] = value.strip()
    settings = TelemetrySettings(
            service_name=service_name,
            provider=provider,
            endpoint=endpoint,
            headers=headers,
            project_name=os.getenv("OPENMODELOPS_TELEMETRY_PROJECT", "openmodelops"),
            capture_content=os.getenv("OPENMODELOPS_CAPTURE_AI_CONTENT", "false").lower() == "true",
        )
    if provider == TelemetryProvider.OPIK:
        return OpikTelemetry(settings)
    return Telemetry(settings)
