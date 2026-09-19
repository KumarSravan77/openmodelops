from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

MATURITY_LEVELS = {"reference", "integration-ready", "implemented", "verified"}


@dataclass(frozen=True)
class Component:
    component_id: str
    name: str
    domain: str
    owner: str
    source: str
    maturity: str
    interface_version: str
    health_endpoint: str
    capabilities: tuple[str, ...]
    evidence: tuple[str, ...]
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9-]{2,62}", self.component_id):
            raise ValueError(f"invalid component id: {self.component_id}")
        if self.domain not in {"mlops", "llmops", "agentops", "ai-sre", "shared"}:
            raise ValueError(f"invalid domain for {self.component_id}")
        if self.maturity not in MATURITY_LEVELS:
            raise ValueError(f"invalid maturity for {self.component_id}")
        if not self.source.startswith("https://github.com/"):
            raise ValueError(f"source must be a GitHub URL for {self.component_id}")
        if not re.fullmatch(r"v\d+", self.interface_version):
            raise ValueError(f"invalid interface version for {self.component_id}")
        if not self.capabilities or not self.evidence:
            raise ValueError(f"capabilities and evidence are required for {self.component_id}")


class Catalog:
    def __init__(self, components: list[Component]) -> None:
        self.components = {component.component_id: component for component in components}
        if len(self.components) != len(components):
            raise ValueError("duplicate component id")
        for component in components:
            missing = set(component.dependencies) - self.components.keys()
            if missing:
                raise ValueError(f"{component.component_id} has unknown dependencies: {sorted(missing)}")
        self._validate_acyclic()

    @classmethod
    def load(cls, directory: Path) -> Catalog:
        components = []
        for path in sorted(directory.glob("*.yaml")):
            raw = yaml.safe_load(path.read_text())
            components.append(
                Component(
                    component_id=raw["id"],
                    name=raw["name"],
                    domain=raw["domain"],
                    owner=raw["owner"],
                    source=raw["source"],
                    maturity=raw["maturity"],
                    interface_version=raw["interfaceVersion"],
                    health_endpoint=raw["healthEndpoint"],
                    capabilities=tuple(raw["capabilities"]),
                    evidence=tuple(raw["evidence"]),
                    dependencies=tuple(raw.get("dependencies", [])),
                )
            )
        if not components:
            raise ValueError("component catalog is empty")
        return cls(components)

    def _validate_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(component_id: str) -> None:
            if component_id in visiting:
                raise ValueError(f"dependency cycle detected at {component_id}")
            if component_id in visited:
                return
            visiting.add(component_id)
            for dependency in self.components[component_id].dependencies:
                visit(dependency)
            visiting.remove(component_id)
            visited.add(component_id)

        for component_id in self.components:
            visit(component_id)

    def summary(self) -> list[dict[str, object]]:
        return [
            {
                "id": item.component_id,
                "name": item.name,
                "domain": item.domain,
                "maturity": item.maturity,
                "capabilities": list(item.capabilities),
                "dependencies": list(item.dependencies),
            }
            for item in self.components.values()
        ]
