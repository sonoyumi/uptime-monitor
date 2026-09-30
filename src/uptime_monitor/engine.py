"""The engine: one asyncio task per monitor, each on its own interval.

For every check: run it -> store the result -> update the state machine -> on an event,
open/close an incident and send an alert. The engine also keeps the live picture
(last result, counters) that the status page and /metrics show.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from uptime_monitor.checks import Opener, run_check
from uptime_monitor.models import CheckResult, Monitor
from uptime_monitor.notifier import Notifier
from uptime_monitor.state import DOWN, Event, MonitorState, update
from uptime_monitor.store import Store
from uptime_monitor.texts import alert_text

logger = logging.getLogger(__name__)
CLEANUP_EVERY = 6 * 3600


@dataclass
class Live:
    monitor: Monitor
    state: MonitorState
    last: CheckResult | None = None
    last_at: float | None = None
    ok_total: int = 0
    fail_total: int = 0


class Engine:
    def __init__(
        self,
        monitors: list[Monitor],
        store: Store,
        notifier: Notifier,
        client: httpx.AsyncClient,
        *,
        opener: Opener = asyncio.open_connection,
        clock: Callable[[], float] = time.time,
        retention_days: int = 90,
    ) -> None:
        self.live = {m.name: Live(m, MonitorState()) for m in monitors}
        self.store = store
        self.notifier = notifier
        self.client = client
        self.opener = opener
        self.clock = clock
        self.retention_days = retention_days

    async def restore(self) -> None:
        """After a restart, monitors that were down stay down, so their recovery is announced."""
        for name, incident in (await self.store.open_incidents()).items():
            if name in self.live:
                self.live[name].state = MonitorState(
                    status=DOWN, down_since=incident.started_at, last_alert_at=self.clock(), last_error=incident.error
                )

    async def check_once(self, name: str) -> Event | None:
        live = self.live[name]
        result = await run_check(live.monitor, self.client, self.opener)
        now = self.clock()
        live.last, live.last_at = result, now
        if result.ok:
            live.ok_total += 1
        else:
            live.fail_total += 1
        await self.store.add_result(name, result, now)
        live.state, event = update(live.state, result, live.monitor, now)
        if event is not None:
            if event.kind == "down":
                await self.store.open_incident(name, now, event.error)
            elif event.kind == "up":
                await self.store.close_incident(name, now)
            await self.notifier.send(alert_text(event))
            logger.info("%s: %s %s", name, event.kind, event.error)
        return event

    async def _loop(self, name: str, stop: asyncio.Event) -> None:
        interval = self.live[name].monitor.interval
        # Spread the first checks so twenty monitors do not fire in the same second.
        if await _sleep(random.uniform(0, min(interval, 5)), stop):
            return
        while not stop.is_set():
            try:
                await self.check_once(name)
            except Exception:  # storage or notifier problems must not kill the loop
                logger.exception("Check loop of %s failed", name)
            if await _sleep(interval, stop):
                return

    async def _cleanup_loop(self, stop: asyncio.Event) -> None:
        while not await _sleep(CLEANUP_EVERY, stop):
            deleted = await self.store.cleanup(self.clock() - self.retention_days * 86400)
            logger.info("Removed %d old results", deleted)

    async def run(self, stop: asyncio.Event) -> None:
        await asyncio.gather(*(self._loop(name, stop) for name in self.live), self._cleanup_loop(stop))

    def snapshot(self) -> list[dict]:
        rows = []
        for name, live in self.live.items():
            status = live.state.status
            rows.append(
                {
                    "monitor": name,
                    "kind": live.monitor.kind,
                    "status": status,
                    "up": 1 if status == "up" else 0 if status == DOWN else -1,
                    "latency_ms": live.last.latency_ms if live.last else None,
                    "last_error": live.state.last_error if status == DOWN else (live.last.error if live.last else ""),
                    "last_checked": live.last_at,
                    "down_since": live.state.down_since,
                    "ok_total": live.ok_total,
                    "fail_total": live.fail_total,
                    "cert_days_left": (live.last.detail.get("cert_days_left") if live.last else None),
                }
            )
        return rows


async def _sleep(seconds: float, stop: asyncio.Event) -> bool:
    """Sleeps unless stop is set; returns True if we should stop."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
        return True
    except TimeoutError:
        return False
