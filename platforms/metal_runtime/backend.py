from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

Prompt = str | list[dict[str, str]]


@dataclass(frozen=True)
class GenerationResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    queue_wait_seconds: float = 0.0


class InferenceBackend(Protocol):
    async def generate(self, prompt: Prompt, maximum_tokens: int) -> GenerationResult: ...


def estimate_tokens(text: str) -> int:
    return max(1, len(text.encode("utf-8")) // 4)


class DevelopmentBackend:
    async def generate(self, prompt: Prompt, maximum_tokens: int) -> GenerationResult:
        await asyncio.sleep(0)
        text = prompt if isinstance(prompt, str) else "\n".join(item["content"] for item in prompt)
        answer = f"Development backend received {estimate_tokens(text)} estimated prompt tokens."
        return GenerationResult(answer, estimate_tokens(text), min(maximum_tokens, estimate_tokens(answer)))


class MLXBackend:
    """Lazy MLX-LM adapter. Model loading occurs only when this backend is selected."""

    def __init__(self, model_id: str) -> None:
        try:
            from mlx_lm import generate, load
        except ImportError as exc:
            raise RuntimeError("MLX backend requires: pip install mlx-lm") from exc
        self._generate = generate
        self._model, self._tokenizer = load(model_id)

    async def generate(self, prompt: Prompt, maximum_tokens: int) -> GenerationResult:
        def run() -> GenerationResult:
            messages = [{"role": "user", "content": prompt}] if isinstance(prompt, str) else prompt
            formatted_prompt = prompt if isinstance(prompt, str) else "\n".join(item["content"] for item in prompt)
            if self._tokenizer.has_chat_template:
                formatted_prompt = self._tokenizer.apply_chat_template(
                    messages,
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
