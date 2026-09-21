from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(pattern=r"^prod-[0-9]{3}$")
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=10, max_length=2000)
    price_cad: float = Field(gt=0, le=100_000)
    rating: float = Field(ge=0, le=5)
    review_count: int = Field(ge=0)
    features: list[str] = Field(min_length=1, max_length=30)
    source: str = Field(default="synthetic-catalog-v1")

    @property
    def searchable_text(self) -> str:
        return " ".join([self.name, self.category, self.description, *self.features])


class ChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    maximum_results: int = Field(default=5, ge=1, le=10)


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict
