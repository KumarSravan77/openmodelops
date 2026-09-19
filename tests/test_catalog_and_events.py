from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from packages.contracts import FactoryEvent
from platforms.factory.api import app
from platforms.factory.catalog import Catalog, Component


def test_repository_catalog_is_valid_and_connected() -> None:
    catalog = Catalog.load(Path("catalog/components"))
    assert len(catalog.components) == 6
    assert catalog.components["on-call-authority"].dependencies == ("aria-intelligence",)
    assert all(component.evidence for component in catalog.components.values())


def test_factory_exposes_component_catalog() -> None:
    response = TestClient(app).get("/components")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()} >= {"openmodelops-factory", "aria-intelligence"}


def test_catalog_rejects_unknown_dependency() -> None:
    component = Component(
        component_id="sample-service",
        name="Sample",
        domain="shared",
        owner="platform",
        source="https://github.com/example/sample",
        maturity="reference",
        interface_version="v1",
        health_endpoint="/health",
        capabilities=("sample",),
        evidence=("tests/test_sample.py",),
        dependencies=("missing-service",),
    )
    with pytest.raises(ValueError, match="unknown dependencies"):
        Catalog([component])


def test_factory_event_is_stable_and_traceable() -> None:
    occurred_at = datetime(2026, 1, 1, tzinfo=UTC)
    first = FactoryEvent(
        event_type="openmodelops.release.approved",
        source="factory",
        tenant="tenant-a",
        subject="workload-1",
        data={"artifact_digest": "sha256:abc"},
        occurred_at=occurred_at,
    )
    second = FactoryEvent(
        event_type=first.event_type,
        source=first.source,
        tenant=first.tenant,
        subject=first.subject,
        data=first.data,
        occurred_at=occurred_at,
    )
    assert first.idempotency_key == second.idempotency_key
    assert first.envelope()["trace_id"] == first.trace_id


def test_factory_event_rejects_unversioned_event_name() -> None:
    with pytest.raises(ValueError, match="namespaced"):
        FactoryEvent("release", "factory", "tenant-a", "workload-1", {})
