from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .retrieval import HybridProductRetriever, ProductHit


@dataclass(frozen=True)
class ProductAnswer:
    answer: str
    citations: tuple[dict, ...]
    attempts: int
    status: str


class ProductAssistant:
    """Bounded corrective product workflow with grounded deterministic generation."""

    def __init__(
        self,
        retriever: HybridProductRetriever,
        minimum_score: float = 0.12,
        maximum_attempts: int = 2,
        generator: Callable[[str, list[ProductHit]], str] | None = None,
    ) -> None:
        self.retriever = retriever
        self.minimum_score = minimum_score
        self.maximum_attempts = maximum_attempts
        self.generator = generator or self._answer

    def ask(self, question: str, maximum_results: int = 5) -> ProductAnswer:
        query = question
        for attempt in range(1, self.maximum_attempts + 1):
            hits = self._apply_constraints(question, self.retriever.search(query, maximum_results))
            relevant = [hit for hit in hits if hit.score >= self.minimum_score and hit.lexical_score > 0]
            if relevant:
                return ProductAnswer(
                    self.generator(question, relevant),
                    tuple(
                        {
                            "product_id": hit.product.product_id,
                            "source": hit.product.source,
                            "score": hit.score,
                        }
                        for hit in relevant
                    ),
                    attempt,
                    "grounded",
                )
            query = self._rewrite(question)
        return ProductAnswer(
            "I do not have sufficient evidence in the approved product catalog to answer that question.",
            (),
            self.maximum_attempts,
            "insufficient_evidence",
        )

    @staticmethod
    def _rewrite(question: str) -> str:
        ignored = {"recommend", "please", "show", "find", "best", "product", "products", "for", "me"}
        return " ".join(token for token in re.findall(r"[a-z0-9]+", question.casefold()) if token not in ignored)

    @staticmethod
    def _apply_constraints(question: str, hits: list[ProductHit]) -> list[ProductHit]:
        match = re.search(r"(?:under|below|less than)\s*(?:cad|\$)?\s*([0-9]+(?:\.[0-9]+)?)", question.casefold())
        if not match:
            return hits
        maximum = float(match.group(1))
        return [hit for hit in hits if hit.product.price_cad < maximum]

    @staticmethod
    def _answer(question: str, hits: list[ProductHit]) -> str:
        recommendations = []
        for hit in hits[:3]:
            product = hit.product
            recommendations.append(
                f"{product.name} [{product.product_id}] — CAD {product.price_cad:.2f}, "
                f"rating {product.rating:.1f}/5. Evidence: {product.description}"
            )
        return "Based only on the approved catalog:\n" + "\n".join(f"- {item}" for item in recommendations)
