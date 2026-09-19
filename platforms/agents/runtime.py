from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Protocol

from packages.contracts import ModelEndpoint

from .policy import GuardrailResult, GuardrailUnavailable, LocalGuardrail, ToolRegistry


class ModelClient(Protocol):
    def generate(self, endpoint: ModelEndpoint, system_prompt: str, user_input: str) -> str: ...


class EchoModel:
    def generate(self, endpoint: ModelEndpoint, system_prompt: str, user_input: str) -> str:
        return f"[{endpoint.name}@{endpoint.revision}] {user_input}"


@dataclass(frozen=True)
class AgentRelease:
    name: str
    revision: str
    prompt: str
    model: ModelEndpoint
    allowed_tools: frozenset[str] = frozenset()
    protected: bool = True


@dataclass
class Trace:
    trace_id: str
    agent: str
    revision: str
    model_revision: str
    status: str
    latency_ms: float
    prompt_digest: str
    input_digest: str
    reasons: tuple[str, ...] = ()


@dataclass
class AgentRuntime:
    model_client: ModelClient
    guardrail: LocalGuardrail | None
    tools: ToolRegistry
    traces: list[Trace] = field(default_factory=list)

    @staticmethod
    def _digest(text: str) -> str:
        return "sha256:" + hashlib.sha256(text.encode()).hexdigest()

    def _check(self, release: AgentRelease, text: str) -> GuardrailResult:
        if self.guardrail is None:
            if release.protected:
                raise GuardrailUnavailable("protected agent requires an available guardrail")
            return GuardrailResult(True, text)
        return self.guardrail.check(text)

    def invoke(self, release: AgentRelease, user_input: str) -> dict:
        trace_id = str(uuid.uuid4())
        started = time.monotonic()
        status = "error"
        reasons: tuple[str, ...] = ()
        try:
            inbound = self._check(release, user_input)
            if not inbound.allowed:
                status, reasons = "blocked_input", inbound.reasons
                return {"trace_id": trace_id, "status": status, "response": inbound.safe_text}
            response = self.model_client.generate(release.model, release.prompt, inbound.safe_text)
            outbound = self._check(release, response)
            if not outbound.allowed:
                status, reasons = "blocked_output", outbound.reasons
                return {"trace_id": trace_id, "status": status, "response": outbound.safe_text}
            status = "success"
            return {"trace_id": trace_id, "status": status, "response": outbound.safe_text}
        finally:
            self.traces.append(
                Trace(
                    trace_id=trace_id,
                    agent=release.name,
                    revision=release.revision,
                    model_revision=release.model.revision,
                    status=status,
                    latency_ms=(time.monotonic() - started) * 1000,
                    prompt_digest=self._digest(release.prompt),
                    input_digest=self._digest(user_input),
                    reasons=reasons,
                )
            )
