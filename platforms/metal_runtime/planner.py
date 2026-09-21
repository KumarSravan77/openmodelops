from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    model_id: str
    parameter_billions: float
    weight_bits: int = 4
    kv_bytes_per_token_fp16: int = 65536
    kv_bits: int = 8
    vision_reserve_gb: float = 1.5

    @property
    def estimated_weights_gb(self) -> float:
        raw = self.parameter_billions * self.weight_bits / 8
        return round(raw * 1.12, 3)

    @property
    def kv_bytes_per_token(self) -> int:
        return max(1, int(self.kv_bytes_per_token_fp16 * self.kv_bits / 16))


@dataclass(frozen=True)
class AdmissionRequest:
    prompt_tokens: int
    maximum_generation_tokens: int
    active_slots: int = 0
    multimodal: bool = False


@dataclass(frozen=True)
class AdmissionDecision:
    admitted: bool
    requested_context: int
    granted_context: int
    estimated_memory_gb: float
    available_memory_gb: float
    reason: str


class MemoryPlanner:
    def __init__(
        self,
        total_memory_gb: float,
        model: ModelProfile,
        system_reserve_gb: float = 6,
        runtime_reserve_gb: float = 2,
        maximum_slots: int = 2,
    ) -> None:
        self.total_memory_gb = total_memory_gb
        self.model = model
        self.system_reserve_gb = system_reserve_gb
        self.runtime_reserve_gb = runtime_reserve_gb
        self.maximum_slots = maximum_slots

    @property
    def cache_budget_gb(self) -> float:
        return max(0, self.total_memory_gb - self.system_reserve_gb - self.runtime_reserve_gb - self.model.estimated_weights_gb)

    def decide(self, request: AdmissionRequest) -> AdmissionDecision:
        requested = request.prompt_tokens + request.maximum_generation_tokens
        slots = request.active_slots + 1
        available = self.cache_budget_gb - (self.model.vision_reserve_gb if request.multimodal else 0)
        if slots > self.maximum_slots:
            return AdmissionDecision(False, requested, 0, 0, available, "concurrency_limit")
        bytes_per_slot = max(0, available) * (1024**3) / slots
        maximum_context = int(bytes_per_slot / self.model.kv_bytes_per_token)
        granted = min(requested, maximum_context)
        estimated = self.model.estimated_weights_gb + self.system_reserve_gb + self.runtime_reserve_gb
        estimated += (granted * self.model.kv_bytes_per_token * slots) / (1024**3)
        if request.multimodal:
            estimated += self.model.vision_reserve_gb
        if maximum_context < request.prompt_tokens:
            return AdmissionDecision(False, requested, maximum_context, round(estimated, 3), available, "insufficient_memory")
        reason = "admitted" if granted == requested else "generation_clamped"
        return AdmissionDecision(True, requested, granted, round(estimated, 3), round(available, 3), reason)
