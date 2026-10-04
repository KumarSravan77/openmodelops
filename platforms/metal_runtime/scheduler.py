from __future__ import annotations

import asyncio
import threading
import time
from dataclasses import dataclass, replace

from .backend import GenerationResult, InferenceBackend, Prompt


@dataclass
class WorkItem:
    prompt: Prompt
    maximum_tokens: int
    result: asyncio.Future[GenerationResult]
    enqueued_at: float
    token_events: asyncio.Queue[tuple[str, int] | None] | None = None
    cancel_event: threading.Event | None = None


@dataclass
class StreamHandle:
    token_events: asyncio.Queue[tuple[str, int] | None]
    result: asyncio.Future[GenerationResult]
    cancel_event: threading.Event


class BoundedScheduler:
    def __init__(self, backend: InferenceBackend, slots: int = 2, queue_limit: int = 20) -> None:
        if slots < 1 or queue_limit < 1:
            raise ValueError("slots and queue_limit must be positive")
        self.backend = backend
        self.slots = slots
        self.queue: asyncio.Queue[WorkItem] = asyncio.Queue(maxsize=queue_limit)
        self._workers: list[asyncio.Task[None]] = []
        self.active = 0

    async def start(self) -> None:
        if not self._workers:
            self._workers = [asyncio.create_task(self._worker()) for _ in range(self.slots)]

    async def stop(self) -> None:
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

    async def submit(self, prompt: Prompt, maximum_tokens: int, timeout_seconds: float = 300) -> GenerationResult:
        if self.queue.full():
            raise OverflowError("inference queue is full")
        future: asyncio.Future[GenerationResult] = asyncio.get_running_loop().create_future()
        await self.queue.put(WorkItem(prompt, maximum_tokens, future, time.perf_counter()))
        return await asyncio.wait_for(future, timeout_seconds)

    async def submit_stream(self, prompt: Prompt, maximum_tokens: int) -> StreamHandle:
        if self.queue.full():
            raise OverflowError("inference queue is full")
        loop = asyncio.get_running_loop()
        handle = StreamHandle(asyncio.Queue(), loop.create_future(), threading.Event())
        await self.queue.put(WorkItem(
            prompt, maximum_tokens, handle.result, time.perf_counter(), handle.token_events, handle.cancel_event
        ))
        return handle

    async def _worker(self) -> None:
        while True:
            item = await self.queue.get()
            self.active += 1
            try:
                if not item.result.cancelled():
                    waited = time.perf_counter() - item.enqueued_at
                    if item.token_events is None:
                        result = await self.backend.generate(item.prompt, item.maximum_tokens)
                    else:
                        loop = asyncio.get_running_loop()

                        def emit(
                            text: str, index: int,
                            target: asyncio.Queue[tuple[str, int] | None] = item.token_events,
                            event_loop: asyncio.AbstractEventLoop = loop,
                        ) -> None:
                            event_loop.call_soon_threadsafe(target.put_nowait, (text, index))

                        result = await self.backend.generate(
                            item.prompt, item.maximum_tokens, on_token=emit, cancel_event=item.cancel_event
                        )
                    if not item.result.cancelled():
                        item.result.set_result(replace(result, queue_wait_seconds=waited))
            except Exception as exc:  # noqa: BLE001 - isolate backend failures at the worker boundary
                if not item.result.cancelled():
                    item.result.set_exception(exc)
            finally:
                if item.token_events is not None:
                    asyncio.get_running_loop().call_soon(item.token_events.put_nowait, None)
                self.active -= 1
                self.queue.task_done()
