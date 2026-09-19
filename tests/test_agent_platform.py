import pytest

from packages.contracts import ModelEndpoint
from platforms.agents.feedback import Feedback, FeedbackStore
from platforms.agents.policy import GuardrailUnavailable, LocalGuardrail, PolicyDenied, ToolRegistry, ToolSpec
from platforms.agents.runtime import AgentRelease, AgentRuntime, EchoModel


def release(protected: bool = True) -> AgentRelease:
    return AgentRelease(
        "support-agent",
        "prompt-v1",
        "Be accurate.",
        ModelEndpoint("local", "model-v1", "http://localhost:8080"),
        protected=protected,
    )


def test_protected_agent_fails_closed_without_guardrail():
    runtime = AgentRuntime(EchoModel(), None, ToolRegistry())
    with pytest.raises(GuardrailUnavailable):
        runtime.invoke(release(), "hello")
    assert runtime.traces[-1].status == "error"


def test_guardrail_blocks_credentials_and_telemetry_keeps_only_digest():
    runtime = AgentRuntime(EchoModel(), LocalGuardrail(), ToolRegistry())
    result = runtime.invoke(release(), "password=super-secret")
    assert result["status"] == "blocked_input"
    assert "super-secret" not in repr(runtime.traces[-1])
    assert runtime.traces[-1].input_digest.startswith("sha256:")


def test_tool_registry_is_deny_by_default_and_requires_approval():
    tools = ToolRegistry()
    tools.register(
        ToolSpec(
            "restart",
            lambda service: f"restarted {service}",
            frozenset({"service"}),
            frozenset({"operator"}),
            side_effecting=True,
        )
    )
    with pytest.raises(PolicyDenied, match="not allow-listed"):
        tools.invoke("shell", {}, "operator")
    with pytest.raises(PolicyDenied, match="approval"):
        tools.invoke("restart", {"service": "api"}, "operator")
    assert tools.invoke("restart", {"service": "api"}, "operator", approved=True) == "restarted api"


def test_feedback_is_curated_not_applied_directly():
    store = FeedbackStore()
    store.add(Feedback("trace-1", -1, "correctness", "wrong source"))
    store.add(Feedback("trace-2", 1, "correctness"))
    assert [item.trace_id for item in store.evaluation_candidates()] == ["trace-1"]
