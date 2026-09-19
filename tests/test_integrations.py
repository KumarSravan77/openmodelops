from typing import Any

from platforms.integrations.clients import AgentGatewayClient, AriaClient, ModelServingClient, OnCallClient
from platforms.integrations.dispatcher import OutboxDispatcher
from platforms.integrations.evaluation import EvaluationReport, EvaluationReportAdapter
from platforms.integrations.http import JsonResponse
from platforms.integrations.outbox import IntegrationOutbox


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def request(self, method: str, url: str, **kwargs: Any) -> JsonResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return JsonResponse(200, {"status": "ok", "incident_id": "inc-1"})


def test_clients_match_existing_service_contracts() -> None:
    transport = FakeTransport()
    assert AriaClient("http://aria", transport).ready()
    OnCallClient("http://on-call", transport).incident("inc-1", "token")
    assert ModelServingClient("http://model-admin", transport).ready()
    AgentGatewayClient("http://agent-gateway", transport).request_tool_call(
        {"idempotency_key": "request-1", "tool": "diagnose"},
        "factory-controller",
        {"tools:read"},
    )
    assert [call["url"] for call in transport.calls] == [
        "http://aria/health",
        "http://on-call/api/v1/incidents/inc-1",
        "http://model-admin/readyz",
        "http://agent-gateway/v1/tool-calls",
    ]
    assert transport.calls[-1]["headers"]["X-Principal"] == "factory-controller"


def test_evaluation_report_becomes_quality_evidence() -> None:
    adapter = EvaluationReportAdapter(0.95)
    report = EvaluationReport.parse({"pass_rate": 0.98, "passed": 49, "total": 50, "comparison": {"regression": False}})
    assert adapter.passed(report)
    evidence = adapter.evidence("workload-1", "s3://reports/eval.json", "sha256:abc", "eval-engine")
    assert evidence.gate == "quality"


def test_outbox_is_durable_idempotent_and_dead_letters(tmp_path) -> None:
    outbox = IntegrationOutbox(f"sqlite:///{tmp_path / 'outbox.db'}")
    first = outbox.enqueue("aria", "event-key", {"event": "investigate"})
    assert outbox.enqueue("aria", "event-key", {"event": "duplicate"}) == first
    pending = outbox.pending()
    assert len(pending) == 1
    outbox.failed(first, "temporary failure", 1)
    assert outbox.pending() == []
    for attempt in range(2, 6):
        outbox.failed(first, "still unavailable", attempt)
    assert outbox.pending() == []


def test_outbox_marks_delivery(tmp_path) -> None:
    outbox = IntegrationOutbox(f"sqlite:///{tmp_path / 'outbox.db'}")
    message_id = outbox.enqueue("on-call", "event-2", {"incident": "inc-1"})
    outbox.delivered(message_id)
    assert outbox.pending() == []


def test_dispatcher_delivers_and_dead_letters_unknown_destination(tmp_path) -> None:
    outbox = IntegrationOutbox(f"sqlite:///{tmp_path / 'outbox.db'}")
    delivered: list[tuple[dict[str, Any], str]] = []
    outbox.enqueue("aria", "event-1", {"incident": "inc-1"})
    outbox.enqueue("unknown", "event-2", {"incident": "inc-2"})
    result = OutboxDispatcher(outbox, {"aria": lambda payload, key: delivered.append((payload, key))}).run_once()
    assert result.delivered == 1
    assert result.dead_lettered == 1
    assert delivered == [({"incident": "inc-1"}, "event-1")]
