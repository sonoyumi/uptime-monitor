"""History in SQLite: every check result, and incidents (from DOWN to UP).

Uptime is "successful checks / all checks" over a period; latency percentiles are computed
in Python from the stored values (SQLite has no percentile function).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import aiosqlite

from uptime_monitor.models import CheckResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS results (
    id          INTEGER PRIMARY KEY,
    monitor     TEXT    NOT NULL,
    checked_at  REAL    NOT NULL,        -- unix time
    ok          INTEGER NOT NULL,
    latency_ms  REAL    NOT NULL,
    error       TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_results_monitor_time ON results (monitor, checked_at);
CREATE TABLE IF NOT EXISTS incidents (
    id          INTEGER PRIMARY KEY,
    monitor     TEXT    NOT NULL,
    started_at  REAL    NOT NULL,
    ended_at    REAL,                     -- NULL while the incident is still open
    error       TEXT    NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS ix_incidents_monitor ON incidents (monitor, started_at);
"""


@dataclass(frozen=True)
class Stats:
    checks: int
    uptime: float | None  # percent, None when there are no checks yet
    avg_ms: float | None
    p95_ms: float | None


@dataclass(frozen=True)
class Incident:
    monitor: str
    started_at: float
    ended_at: float | None
    error: str

    @property
    def duration(self) -> float | None:
        return None if self.ended_at is None else self.ended_at - self.started_at


def percentile(values: list[float], pct: float) -> float | None:
    """Nearest-rank percentile: p95 of 20 values is the 19th smallest."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * pct // 100))  # ceil without math
    return ordered[int(rank) - 1]


class Store:
    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    @classmethod
    async def open(cls, path: Path | str) -> Store:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(path)
        await conn.execute("PRAGMA journal_mode=WAL")  # the web page reads while the checker writes
        await conn.executescript(SCHEMA)
        await conn.commit()
        return cls(conn)

    async def close(self) -> None:
        await self._conn.close()

    async def add_result(self, monitor: str, result: CheckResult, at: float) -> None:
        await self._conn.execute(
            "INSERT INTO results (monitor, checked_at, ok, latency_ms, error) VALUES (?, ?, ?, ?, ?)",
            (monitor, at, int(result.ok), result.latency_ms, result.error),
        )
        await self._conn.commit()

    async def open_incident(self, monitor: str, at: float, error: str) -> None:
        await self._conn.execute(
            "INSERT INTO incidents (monitor, started_at, error) VALUES (?, ?, ?)", (monitor, at, error)
        )
        await self._conn.commit()

    async def close_incident(self, monitor: str, at: float) -> None:
        await self._conn.execute(
            "UPDATE incidents SET ended_at = ? WHERE monitor = ? AND ended_at IS NULL", (at, monitor)
        )
        await self._conn.commit()

    async def open_incidents(self) -> dict[str, Incident]:
        """Incidents left open by a previous run: the monitor starts as DOWN, so recovery is announced."""
        async with self._conn.execute(
            "SELECT monitor, started_at, ended_at, error FROM incidents WHERE ended_at IS NULL"
        ) as cursor:
            return {row[0]: Incident(*row) async for row in cursor}

    async def stats(self, monitor: str, since: float) -> Stats:
        async with self._conn.execute(
            "SELECT ok, latency_ms FROM results WHERE monitor = ? AND checked_at >= ?", (monitor, since)
        ) as cursor:
            rows = await cursor.fetchall()
        if not rows:
            return Stats(0, None, None, None)
        ok_latencies = [lat for ok, lat in rows if ok]
        uptime = round(100 * sum(ok for ok, _ in rows) / len(rows), 3)
        avg = round(sum(ok_latencies) / len(ok_latencies), 1) if ok_latencies else None
        return Stats(len(rows), uptime, avg, percentile(ok_latencies, 95))

    async def incidents(self, monitor: str | None = None, limit: int = 20) -> list[Incident]:
        sql = "SELECT monitor, started_at, ended_at, error FROM incidents"
        params: tuple = ()
        if monitor:
            sql += " WHERE monitor = ?"
            params = (monitor,)
        sql += " ORDER BY started_at DESC LIMIT ?"
        async with self._conn.execute(sql, (*params, limit)) as cursor:
            return [Incident(*row) async for row in cursor]

    async def cleanup(self, older_than: float) -> int:
        cursor = await self._conn.execute("DELETE FROM results WHERE checked_at < ?", (older_than,))
        await self._conn.commit()
        return cursor.rowcount
