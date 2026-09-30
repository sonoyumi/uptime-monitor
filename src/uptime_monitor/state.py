"""The alerting logic as a pure function: (old state, new result, now) -> (new state, event or None).

Why not alert on every failed check? Networks hiccup. One timeout at 03:12 is noise; three in a
row is an outage. So a monitor goes DOWN only after `fail_threshold` consecutive failures and
comes back UP only after `recover_threshold` consecutive successes. This is "anti-flapping".

    unknown ──success×recover──► up ──failure×fail──► down ──success×recover──► up
       └────────failure×fail─────────────────────────►┘      └─ every remind_every s: Reminder
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from uptime_monitor.models import CheckResult, Monitor

UP, DOWN, UNKNOWN = "up", "down", "unknown"


@dataclass(frozen=True)
class MonitorState:
    status: str = UNKNOWN
    fails: int = 0  # consecutive failures
    successes: int = 0  # consecutive successes
    down_since: float | None = None
    last_alert_at: float | None = None
    last_error: str = ""


@dataclass(frozen=True)
class Event:
    kind: str  # down | up | reminder
    monitor: str
    error: str = ""
    duration: float = 0.0  # seconds down (for up and reminder)


def update(state: MonitorState, result: CheckResult, m: Monitor, now: float) -> tuple[MonitorState, Event | None]:
    if result.ok:
        state = replace(state, successes=state.successes + 1, fails=0)
        if state.status == DOWN and state.successes >= m.recover_threshold:
            duration = now - (state.down_since or now)
            new = MonitorState(status=UP, successes=state.successes)
            return new, Event("up", m.name, duration=duration)
        if state.status == UNKNOWN and state.successes >= m.recover_threshold:
            return replace(state, status=UP), None  # first start: no "recovered" message
        return state, None

    state = replace(state, fails=state.fails + 1, successes=0, last_error=result.error)
    if state.status != DOWN and state.fails >= m.fail_threshold:
        new = replace(state, status=DOWN, down_since=now, last_alert_at=now)
        return new, Event("down", m.name, error=result.error)
    if state.status == DOWN and m.remind_every and now - (state.last_alert_at or now) >= m.remind_every:
        new = replace(state, last_alert_at=now)
        return new, Event("reminder", m.name, error=result.error, duration=now - (state.down_since or now))
    return state, None
