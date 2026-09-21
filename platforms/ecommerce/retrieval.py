from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from .catalog import ProductCatalog
from .domain import Product

TOKEN = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset({"a", "an", "and", "are", "for", "has", "i", "is", "it", "me", "of", "or", "the", "to", "what", "which", "with"})


def tokens(value: str) -> set[str]:
    return set(TOKEN.findall(value.casefold()))


def embedding(value: str, dimensions: int = 64) -> tuple[float, ...]:
    vector = [0.0] * dimensions
    for token in tokens(value):
        digest = hashlib.sha256(token.encode()).digest()
        index = int.from_bytes(digest[:2], "big") % dimensions
        vector[index] += -1.0 if digest[2] & 1 else 1.0
    magnitude = math.sqrt(sum(item * item for item in vector)) or 1
    return tuple(item / magnitude for item in vector)


def cosine(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    return sum(left * right for left, right in zip(first, second, strict=True))


@dataclass(frozen=True)
class ProductHit:
    product: Product
    score: float
    lexical_score: float
    semantic_score: float


class HybridProductRetriever:
    """Deterministic local hybrid retrieval with bounded MMR diversification."""

    def __init__(self, catalog: ProductCatalog) -> None:
        self.catalog = catalog
        self._vectors = {item.product_id: embedding(item.searchable_text) for item in catalog.products}

    def search(self, query: str, limit: int = 5) -> list[ProductHit]:
        query_tokens = tokens(query) - STOPWORDS
        query_vector = embedding(query)
        candidates = []
        for product in self.catalog.products:
            product_tokens = tokens(product.searchable_text)
            lexical = len(query_tokens & product_tokens) / max(1, len(query_tokens))
            semantic = max(0.0, cosine(query_vector, self._vectors[product.product_id]))
            score = 0.6 * lexical + 0.4 * semantic
            if score > 0:
                candidates.append(ProductHit(product, round(score, 6), round(lexical, 6), round(semantic, 6)))
        candidates.sort(key=lambda item: (item.score, item.product.rating, item.product.review_count), reverse=True)
        selected: list[ProductHit] = []
        while candidates and len(selected) < limit:
            choice = max(
                candidates,
                key=lambda item: item.score
                - 0.2
                * max(
                    (cosine(self._vectors[item.product.product_id], self._vectors[other.product.product_id]) for other in selected),
                    default=0,
                ),
            )
            selected.append(choice)
            candidates.remove(choice)
        return selected
