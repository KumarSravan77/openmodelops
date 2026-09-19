from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar


class PolicyDenied(RuntimeError):
    pass


class GuardrailUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class GuardrailResult:
    allowed: bool
    safe_text: str
    reasons: tuple[str, ...] = ()


class LocalGuardrail:
    """Deterministic baseline guardrail. Production providers implement this interface."""

    _patterns: ClassVar[list[tuple[re.Pattern[str], str]]] = [
        (re.compile(r"\b(?:password|secret|api[_ -]?key)\s*[:=]\s*\S+", re.IGNORECASE), "credential"),
        (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "government_identifier"),
    ]

    def check(self, text: str) -> GuardrailResult:
        reasons = tuple(label for pattern, label in self._patterns if pattern.search(text))
        if reasons:
            return GuardrailResult(False, "Request blocked by safety policy.", reasons)
        return GuardrailResult(True, text)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    handler: Callable[..., Any]
    required_arguments: frozenset[str] = frozenset()
    allowed_roles: frozenset[str] = frozenset({"operator"})
    side_effecting: bool = False


@dataclass
class ToolRegistry:
    tools: dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self.tools:
            raise ValueError(f"duplicate tool: {spec.name}")
        self.tools[spec.name] = spec

    def invoke(self, name: str, arguments: Mapping[str, Any], role: str, approved: bool = False) -> Any:
        spec = self.tools.get(name)
        if spec is None:
            raise PolicyDenied("tool is not allow-listed")
        if role not in spec.allowed_roles:
            raise PolicyDenied("caller role is not permitted for this tool")
        missing = spec.required_arguments - arguments.keys()
        if missing:
            raise PolicyDenied(f"missing required arguments: {sorted(missing)}")
        if spec.side_effecting and not approved:
            raise PolicyDenied("side-effecting tool requires explicit approval")
        return spec.handler(**dict(arguments))
