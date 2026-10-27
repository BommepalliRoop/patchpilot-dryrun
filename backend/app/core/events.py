"""In-memory async pub/sub per scan_id for SSE (the only global state allowed by CLAUDE.md).

RISKS N8: each scan keeps a replay buffer (last 200 events); a new subscriber receives the replay first,
so a page opened late or a reconnect never misses events. RISKS S4: messages are redacted on publish.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict, deque
from collections.abc import AsyncIterator
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.security import redact

Stage = Literal["clone", "scan", "symbols", "reachability", "risk", "fix", "pr", "notify", "done"]

REPLAY_SIZE = 200
MAX_TRACKED_SCANS = 100


class ScanEvent(BaseModel):
    """Exactly the SSE `data:` shape in docs/API_CONTRACTS.md."""

    scan_id: str
    stage: Stage
    status: str = "running"  # running | completed | failed | skipped (T03 decides the full set)
    message: str = ""
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    data: dict[str, Any] = Field(default_factory=dict)


class EventBus:
    def __init__(self) -> None:
        self._buffers: OrderedDict[str, deque[ScanEvent]] = OrderedDict()
        self._subscribers: dict[str, set[asyncio.Queue[ScanEvent]]] = {}

    def publish(self, event: ScanEvent) -> None:
        """Non-blocking; safe to call from any coroutine of the running loop."""
        event = event.model_copy(update={"message": redact(event.message)})
        buf = self._buffers.get(event.scan_id)
        if buf is None:
            buf = self._buffers[event.scan_id] = deque(maxlen=REPLAY_SIZE)
            while len(self._buffers) > MAX_TRACKED_SCANS:
                old_id, _ = self._buffers.popitem(last=False)
                self._subscribers.pop(old_id, None)
        buf.append(event)
        for queue in list(self._subscribers.get(event.scan_id, ())):
            queue.put_nowait(event)

    def history(self, scan_id: str) -> list[ScanEvent]:
        return list(self._buffers.get(scan_id, ()))

    async def subscribe(self, scan_id: str) -> AsyncIterator[ScanEvent]:
        """Yield the replay, then live events, until the `done` event has been delivered."""
        queue: asyncio.Queue[ScanEvent] = asyncio.Queue()
        # No await between snapshot and registration, so no event can fall in the gap.
        replay = self.history(scan_id)
        self._subscribers.setdefault(scan_id, set()).add(queue)
        try:
            for event in replay:
                yield event
                if event.stage == "done":
                    return
            while True:
                event = await queue.get()
                yield event
                if event.stage == "done":
                    return
        finally:
            subs = self._subscribers.get(scan_id)
            if subs is not None:
                subs.discard(queue)
                if not subs:
                    self._subscribers.pop(scan_id, None)

    def clear(self, scan_id: str | None = None) -> None:
        if scan_id is None:
            self._buffers.clear()
        else:
            self._buffers.pop(scan_id, None)


bus = EventBus()
