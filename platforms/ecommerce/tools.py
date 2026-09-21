from __future__ import annotations

from .catalog import ProductCatalog
from .retrieval import HybridProductRetriever


class ProductToolRegistry:
    """Deny-by-default MCP-style tool registry."""

    def __init__(self, catalog: ProductCatalog, retriever: HybridProductRetriever) -> None:
        self.catalog = catalog
        self.retriever = retriever

    def definitions(self) -> list[dict]:
        return [
            {
                "name": "product_search",
                "description": "Search the approved synthetic product catalog.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 10}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "name": "product_compare",
                "description": "Compare two approved product IDs.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"product_ids": {"type": "array", "minItems": 2, "maxItems": 2, "items": {"type": "string"}}},
                    "required": ["product_ids"],
                    "additionalProperties": False,
                },
            },
        ]

    def call(self, name: str, arguments: dict) -> dict:
        if name == "product_search":
            if set(arguments) - {"query", "limit"} or not isinstance(arguments.get("query"), str):
                raise ValueError("invalid product_search arguments")
            hits = self.retriever.search(arguments["query"], int(arguments.get("limit", 5)))
            return {"products": [hit.product.model_dump() | {"retrieval_score": hit.score} for hit in hits]}
        if name == "product_compare":
            if set(arguments) != {"product_ids"} or not isinstance(arguments["product_ids"], list):
                raise ValueError("invalid product_compare arguments")
            identifiers = arguments["product_ids"]
            if len(identifiers) != 2 or identifiers[0] == identifiers[1]:
                raise ValueError("exactly two distinct product IDs are required")
            try:
                products = [self.catalog.by_id[str(identifier)] for identifier in identifiers]
            except KeyError as exc:
                raise ValueError("unknown product ID") from exc
            return {"products": [product.model_dump() for product in products]}
        raise PermissionError("tool is not registered")
