from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GenerationResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


class InferenceBackend(Protocol):
    async def generate(self, prompt: str, maximum_tokens: int) -> GenerationResult: ...


def estimate_tokens(text: str) -> int:
    return max(1, len(text.encode("utf-8")) // 4)


class DevelopmentBackend:
    async def generate(self, prompt: str, maximum_tokens: int) -> GenerationResult:
        await asyncio.sleep(0)
        answer = f"Development backend received {estimate_tokens(prompt)} estimated prompt tokens."
        return GenerationResult(answer, estimate_tokens(prompt), min(maximum_tokens, estimate_tokens(answer)))


class MLXBackend:
    """Lazy MLX-LM adapter. Model loading occurs only when this backend is selected."""

    def __init__(self, model_id: str) -> None:
        try:
            from mlx_lm import generate, load
        except ImportError as exc:
            raise RuntimeError("MLX backend requires: pip install mlx-lm") from exc
        self._generate = generate
        self._model, self._tokenizer = load(model_id)

    async def generate(self, prompt: str, maximum_tokens: int) -> GenerationResult:
        def run() -> GenerationResult:
            formatted_prompt = prompt
            if self._tokenizer.has_chat_template:
                formatted_prompt = self._tokenizer.apply_chat_template(
                    [{"role": "user", "content": prompt}],
                    tokenize=False,
                    add_generation_prompt=True,
                    enable_thinking=False,
                )
            output = self._generate(
                self._model,
                self._tokenizer,
                prompt=formatted_prompt,
                max_tokens=maximum_tokens,
                verbose=False,
            )
            return GenerationResult(
                str(output),
                len(self._tokenizer.encode(formatted_prompt)),
                len(self._tokenizer.encode(str(output))),
            )

        return await asyncio.to_thread(run)
