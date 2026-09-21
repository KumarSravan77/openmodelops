from __future__ import annotations

import asyncio
from dataclasses import dataclass

from .backend import GenerationResult, InferenceBackend


@dataclass
class WorkItem:
    prompt: str
    maximum_tokens: int
    result: asyncio.Future[GenerationResult]


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

    async def submit(self, prompt: str, maximum_tokens: int, timeout_seconds: float = 300) -> GenerationResult:
        if self.queue.full():
            raise OverflowError("inference queue is full")
        future: asyncio.Future[GenerationResult] = asyncio.get_running_loop().create_future()
        await self.queue.put(WorkItem(prompt, maximum_tokens, future))
        return await asyncio.wait_for(future, timeout_seconds)

    async def _worker(self) -> None:
        while True:
            item = await self.queue.get()
            self.active += 1
            try:
                if not item.result.cancelled():
                    item.result.set_result(await self.backend.generate(item.prompt, item.maximum_tokens))
            except Exception as exc:  # noqa: BLE001 - isolate backend failures at the worker boundary
                if not item.result.cancelled():
                    item.result.set_exception(exc)
            finally:
                self.active -= 1
                self.queue.task_done()
