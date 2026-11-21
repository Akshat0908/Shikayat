import asyncio
import json
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from datetime import datetime, timezone


class EventBus:
    """Single-process fan-out. Slow clients lose oldest events; reconnect to refresh."""
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()

    @asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[str]]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        self._subscribers.add(queue)
        try:
            yield queue
        finally:
            self._subscribers.discard(queue)

    async def publish(self, event: str, data: dict[str, object]) -> None:
        payload = f"event: {event}\ndata: {json.dumps(data)}\n\n"
        for queue in tuple(self._subscribers):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(payload)

    async def ping_forever(self) -> None:
        while True:
            await asyncio.sleep(15)
            await self.publish("ping", {"at": datetime.now(timezone.utc).isoformat()})
