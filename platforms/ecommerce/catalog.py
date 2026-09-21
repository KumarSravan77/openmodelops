from __future__ import annotations

import json
from pathlib import Path

from .domain import Product


class ProductCatalog:
    def __init__(self, products: list[Product]) -> None:
        if not products:
            raise ValueError("product catalog cannot be empty")
        identifiers = [product.product_id for product in products]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("product IDs must be unique")
        self.products = tuple(products)
        self.by_id = {product.product_id: product for product in products}

    @classmethod
    def load(cls, path: Path) -> ProductCatalog:
        payload = json.loads(path.read_text())
        return cls([Product.model_validate(item) for item in payload])
