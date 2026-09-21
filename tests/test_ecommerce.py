from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from platforms.ecommerce.api import app
from platforms.ecommerce.catalog import ProductCatalog
from platforms.ecommerce.retrieval import HybridProductRetriever
from platforms.ecommerce.tools import ProductToolRegistry
from platforms.ecommerce.workflow import ProductAssistant

CATALOG = Path("examples/ecommerce-assistant/data/products.json")


def assistant() -> ProductAssistant:
    return ProductAssistant(HybridProductRetriever(ProductCatalog.load(CATALOG)))


def test_catalog_is_valid_and_unique() -> None:
    catalog = ProductCatalog.load(CATALOG)
    assert len(catalog.products) == 12
    assert len(catalog.by_id) == 12


def test_hybrid_retrieval_and_price_constraint_return_grounded_product() -> None:
    result = assistant().ask("Recommend noise-cancelling headphones under CAD 300")
    assert result.status == "grounded"
    assert result.citations[0]["product_id"] == "prod-001"
    assert "[prod-001]" in result.answer
    assert "prod-003" not in {item["product_id"] for item in result.citations}


def test_unknown_product_question_refuses_without_web_fallback() -> None:
    result = assistant().ask("Which laptop has an RTX 5090?")
    assert result.status == "insufficient_evidence"
    assert not result.citations


def test_tools_are_deny_by_default_and_validate_comparison() -> None:
    catalog = ProductCatalog.load(CATALOG)
    registry = ProductToolRegistry(catalog, HybridProductRetriever(catalog))
    result = registry.call("product_compare", {"product_ids": ["prod-001", "prod-003"]})
    assert len(result["products"]) == 2
    try:
        registry.call("live_web_search", {"query": "competitor price"})
    except PermissionError:
        pass
    else:
        raise AssertionError("unregistered tools must be denied")


def test_golden_retrieval_cases() -> None:
    workflow = assistant()
    for line in Path("examples/ecommerce-assistant/evaluation/golden.jsonl").read_text().splitlines():
        case = json.loads(line)
        result = workflow.ask(case["question"])
        actual = {item["product_id"] for item in result.citations}
        assert result.status == case["expected_status"], case["question"]
        assert set(case["expected_product_ids"]).issubset(actual), case["question"]


def test_api_and_mcp_style_contract() -> None:
    with TestClient(app) as client:
        ready = client.get("/health/ready")
        answer = client.post("/v1/chat", json={"question": "Find a quiet wireless office keyboard"})
        tools = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        denied = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "web_search"}},
        )
    assert ready.json()["catalog_products"] == 12
    assert answer.json()["status"] == "grounded"
    assert len(tools.json()["result"]["tools"]) == 2
    assert denied.json()["error"]["code"] == -32602
