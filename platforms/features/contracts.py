from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class FeatureContractError(ValueError):
    pass


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    dtype: str
    owner: str
    description: str
    minimum: float | None = None
    maximum: float | None = None
    ttl_seconds: int | None = None

    def validate(self, value: Any) -> None:
        checks = {
            "float": lambda item: isinstance(item, (float, int)) and not isinstance(item, bool),
            "int": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "string": lambda item: isinstance(item, str),
            "bool": lambda item: isinstance(item, bool),
        }
        if self.dtype not in checks or not checks[self.dtype](value):
            raise FeatureContractError(f"{self.name} must be {self.dtype}")
        if self.minimum is not None and value < self.minimum:
            raise FeatureContractError(f"{self.name} below minimum")
        if self.maximum is not None and value > self.maximum:
            raise FeatureContractError(f"{self.name} above maximum")


@dataclass(frozen=True)
class FeatureRecord:
    entity_id: str
    event_timestamp: datetime
    values: dict[str, Any]

    def __post_init__(self) -> None:
        if self.event_timestamp.tzinfo is None:
            raise FeatureContractError("event_timestamp must be timezone aware")
        if self.event_timestamp > datetime.now(UTC):
            raise FeatureContractError("event_timestamp cannot be in the future")


class FeatureService:
    def __init__(self, definitions: list[FeatureDefinition]) -> None:
        self.definitions = {item.name: item for item in definitions}

    def validate(self, record: FeatureRecord) -> None:
        unknown = record.values.keys() - self.definitions.keys()
        missing = self.definitions.keys() - record.values.keys()
        if unknown or missing:
            raise FeatureContractError(f"feature mismatch unknown={sorted(unknown)} missing={sorted(missing)}")
        for name, value in record.values.items():
            self.definitions[name].validate(value)
