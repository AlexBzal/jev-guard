"""Bus de eventos en memoria para el flujo en vivo (Server-Sent Events).

Las decisiones se toman en hilos del servidor; cada suscriptor SSE vive en el event
loop de asyncio. `publish` cruza esa frontera con `call_soon_threadsafe`.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any

Subscription = tuple[asyncio.AbstractEventLoop, asyncio.Queue]


class EventBus:
    def __init__(self, max_queue: int = 500):
        self._subs: set[Subscription] = set()
        self._lock = threading.Lock()
        self._max = max_queue

    def subscribe(self, loop: asyncio.AbstractEventLoop) -> Subscription:
        sub = (loop, asyncio.Queue(maxsize=self._max))
        with self._lock:
            self._subs.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        with self._lock:
            self._subs.discard(sub)

    @property
    def subscribers(self) -> int:
        return len(self._subs)

    def publish(self, event: dict[str, Any]) -> None:
        with self._lock:
            subs = list(self._subs)
        for loop, queue in subs:
            try:
                loop.call_soon_threadsafe(self._put, queue, event)
            except RuntimeError:  # el loop ya cerró
                self.unsubscribe((loop, queue))

    @staticmethod
    def _put(queue: asyncio.Queue, event: dict[str, Any]) -> None:
        if queue.full():  # un cliente lento pierde los eventos más viejos, no frena al resto
            queue.get_nowait()
        queue.put_nowait(event)
