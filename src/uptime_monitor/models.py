"""Plain data: what to check (Monitor) and what a check returned (CheckResult)."""

from __future__ import annotations

from dataclasses import dataclass, field

KINDS = ("http", "tcp", "tls")


@dataclass(frozen=True)
class Monitor:
    name: str
    kind: str  # http | tcp | tls
    interval: int = 60  # seconds between checks
    timeout: float = 10.0
    fail_threshold: int = 3  # consecutive failures before we say DOWN (anti-flapping)
    recover_threshold: int = 2  # consecutive successes before we say UP again
    remind_every: int = 1800  # while down, repeat the alert every N seconds; 0 = never
    # http
    url: str = ""
    method: str = "GET"
    expect_status: tuple[int, ...] = (200,)
    keyword: str = ""  # the page must contain this text
    max_latency_ms: int = 0  # 0 = no limit
    # tcp / tls
    host: str = ""
    port: int = 0
    cert_days: int = 14  # tls: fail when the certificate expires sooner than this


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    latency_ms: float
    error: str = ""
    detail: dict = field(default_factory=dict)  # e.g. {"status": 200} or {"cert_days_left": 41.5}
