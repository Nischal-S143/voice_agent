from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


class InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._completed: set[str] = set()
        self._in_flight: dict[str, asyncio.Task[T]] = {}
        self._lock = asyncio.Lock()

    async def run_once(
        self, key: str, operation: Callable[[], Awaitable[T]]
    ) -> tuple[T | None, bool]:
        async with self._lock:
            if key in self._completed:
                return None, True
            task = self._in_flight.get(key)
            is_owner = task is None
            if task is None:
                task = asyncio.create_task(operation())
                self._in_flight[key] = task

        try:
            result = await task
        except Exception:
            async with self._lock:
                if self._in_flight.get(key) is task:
                    self._in_flight.pop(key, None)
            raise

        async with self._lock:
            self._completed.add(key)
            if self._in_flight.get(key) is task:
                self._in_flight.pop(key, None)
        return result, not is_owner
