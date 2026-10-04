from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

Prompt = str | list[dict[str, str]]
TokenCallback = Callable[[str, int], None]


@dataclass(frozen=True)
class GenerationResult:
    text: str
    prompt_tokens: int
    completion_tokens: int
    queue_wait_seconds: float = 0.0
    first_token_seconds: float | None = None
    time_per_output_token_seconds: float | None = None


class InferenceBackend(Protocol):
    async def generate(
        self,
        prompt: Prompt,
        maximum_tokens: int,
        on_token: TokenCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> GenerationResult: ...


def estimate_tokens(text: str) -> int:
    return max(1, len(text.encode("utf-8")) // 4)


class DevelopmentBackend:
    async def generate(
        self,
        prompt: Prompt,
        maximum_tokens: int,
        on_token: TokenCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> GenerationResult:
        await asyncio.sleep(0)
        if cancel_event is not None and cancel_event.is_set():
            raise RuntimeError("generation cancelled")
        text = prompt if isinstance(prompt, str) else "\n".join(item["content"] for item in prompt)
        answer = f"Development backend received {estimate_tokens(text)} estimated prompt tokens."
        if on_token is not None:
            on_token(answer, 1)
        return GenerationResult(answer, estimate_tokens(text), min(maximum_tokens, estimate_tokens(answer)))


class MLXBackend:
    """Lazy MLX-LM adapter. Model loading occurs only when this backend is selected."""

    def __init__(self, model_id: str) -> None:
        try:
            from mlx_lm import load, stream_generate
        except ImportError as exc:
            raise RuntimeError("MLX backend requires: pip install mlx-lm") from exc
        self._stream_generate = stream_generate
        self._model, self._tokenizer = load(model_id)

    async def generate(
        self,
        prompt: Prompt,
        maximum_tokens: int,
        on_token: TokenCallback | None = None,
        cancel_event: threading.Event | None = None,
    ) -> GenerationResult:
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
            started = time.perf_counter()
            first_token_at: float | None = None
            last_token_at: float | None = None
            token_count = 0
            output_segments: list[str] = []
            prompt_tokens = len(self._tokenizer.encode(formatted_prompt))
            for event in self._stream_generate(
                self._model, self._tokenizer, prompt=formatted_prompt, max_tokens=maximum_tokens
            ):
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("generation cancelled")
                output_segments.append(event.text)
                # The final MLX event may only flush decoded text; it is not a new token.
                if event.finish_reason != "stop" and event.generation_tokens > token_count:
                    token_count = event.generation_tokens
                    last_token_at = time.perf_counter()
                    if first_token_at is None:
                        first_token_at = last_token_at
                    if on_token is not None:
                        on_token(event.text, token_count)
                elif on_token is not None and event.text:
                    on_token(event.text, token_count)
                prompt_tokens = event.prompt_tokens
            output = "".join(output_segments)
            return GenerationResult(
                output,
                prompt_tokens,
                token_count,
                first_token_seconds=first_token_at - started if first_token_at is not None else None,
                time_per_output_token_seconds=(last_token_at - first_token_at) / (token_count - 1)
                if first_token_at is not None and last_token_at is not None and token_count > 1
                else None,
            )

        return await asyncio.to_thread(run)
