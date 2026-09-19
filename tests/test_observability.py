from contextlib import contextmanager

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from packages.contracts import FactoryEvent
from packages.observability import (
    OpikTelemetry,
    Telemetry,
    TelemetryProvider,
    TelemetrySettings,
    trace_context_from_event,
)


def test_sensitive_content_is_excluded_and_openinference_kind_is_set():
    exporter = InMemorySpanExporter()
    telemetry = Telemetry(TelemetrySettings("test", endpoint="http://unused"), exporter=exporter)
    with telemetry.operation(
        "llm",
        attributes={"model.name": "qwen", "prompt": "private", "document.content": "secret", "llm.tokens": 12},
    ):
        pass

    span = exporter.get_finished_spans()[0]
    assert span.attributes["model.name"] == "qwen"
    assert span.attributes["llm.tokens"] == 12
    assert span.attributes["openinference.span.kind"] == "LLM"
    assert "prompt" not in span.attributes
    assert "document.content" not in span.attributes


def test_provider_headers_and_explicit_content_capture():
    langfuse = TelemetrySettings(
        "test", provider=TelemetryProvider.LANGFUSE, headers={"Authorization": "Basic opaque"}
    )
    assert langfuse.exporter_headers()["x-langfuse-ingestion-version"] == "4"
    phoenix = TelemetrySettings("test", provider=TelemetryProvider.PHOENIX, project_name="factory")
    assert phoenix.exporter_headers()["x-project-name"] == "factory"

    exporter = InMemorySpanExporter()
    telemetry = Telemetry(TelemetrySettings("test", endpoint="unused", capture_content=True), exporter=exporter)
    with telemetry.operation("retrieval", attributes={"document.content": "approved sample"}):
        pass
    assert exporter.get_finished_spans()[0].attributes["document.content"] == "approved sample"


def test_factory_event_context_preserves_trace_id_and_errors_are_sanitized():
    exporter = InMemorySpanExporter()
    telemetry = Telemetry(TelemetrySettings("test", endpoint="unused"), exporter=exporter)
    event = FactoryEvent("factory.release", "factory", "tenant-a", "workload-a", {})
    try:
        with telemetry.operation("factory", parent_context=trace_context_from_event(event)):
            raise RuntimeError("customer secret")
    except RuntimeError:
        pass
    span = exporter.get_finished_spans()[0]
    assert f"{span.context.trace_id:032x}" == event.trace_id
    assert span.attributes["openmodelops.outcome"] == "error"
    assert "customer secret" not in str(span.events)


def test_disabled_telemetry_requires_no_endpoint_and_emits_no_spans():
    telemetry = Telemetry(TelemetrySettings("test", enabled=False))
    with telemetry.operation("tool", attributes={"tool.name": "search"}):
        pass
    telemetry.shutdown()


def test_native_opik_adapter_sanitizes_metadata_and_maps_span_type():
    class SDK:
        def __init__(self):
            self.calls = []

        @contextmanager
        def start_as_current_span(self, name, **kwargs):
            self.calls.append((name, kwargs))
            yield object()

    sdk = SDK()
    telemetry = OpikTelemetry(TelemetrySettings("test", provider=TelemetryProvider.OPIK), sdk=sdk)
    with telemetry.operation("llm", attributes={"model.name": "qwen", "prompt": "private"}):
        pass
    name, kwargs = sdk.calls[0]
    assert name == "openmodelops.llm"
    assert kwargs["type"] == "llm"
    assert kwargs["metadata"] == {"model.name": "qwen"}
