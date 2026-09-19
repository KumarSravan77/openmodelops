from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OpenWeightModel:
    model_id: str
    family: str
    license_name: str
    use_case: str
    minimum_memory_gb: int


# License metadata must be verified again before every redistribution or production release.
CATALOG = {
    "qwen-small": OpenWeightModel("qwen2.5:3b", "Qwen", "Apache-2.0", "local development", 6),
    "mistral-small": OpenWeightModel("mistral:7b", "Mistral", "Apache-2.0", "general assistant", 10),
    "gemma-small": OpenWeightModel("gemma3:4b", "Gemma", "Gemma Terms", "local multimodal experiments", 8),
}


def get_model(alias: str) -> OpenWeightModel:
    try:
        return CATALOG[alias]
    except KeyError as exc:
        raise ValueError(f"unknown model alias: {alias}") from exc
