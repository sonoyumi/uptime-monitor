"""Prometheus text format, written by hand (it is simple, and this way there is nothing to hide).

# HELP uptime_monitor_up 1 = up, 0 = down, -1 = not known yet
# TYPE uptime_monitor_up gauge
uptime_monitor_up{monitor="Website"} 1
"""

from __future__ import annotations

from collections.abc import Iterable


def label(value: str) -> str:
    """Label values escape backslash, double quote and newline (Prometheus exposition format)."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render(rows: Iterable[dict]) -> str:
    """rows: dicts with monitor, kind, up (1/0/-1), latency_ms, ok_total, fail_total, cert_days_left (optional)."""
    rows = list(rows)
    out: list[str] = []

    def metric(name: str, kind: str, help_text: str, samples: list[tuple[str, float]]) -> None:
        out.append(f"# HELP {name} {help_text}")
        out.append(f"# TYPE {name} {kind}")
        out.extend(f"{name}{{{labels}}} {value:g}" for labels, value in samples)

    def lbl(row: dict, **extra: str) -> str:
        pairs = {"monitor": row["monitor"], "type": row["kind"], **extra}
        return ",".join(f'{k}="{label(str(v))}"' for k, v in pairs.items())

    metric("uptime_monitor_up", "gauge", "1 = up, 0 = down, -1 = not known yet", [(lbl(r), r["up"]) for r in rows])
    metric(
        "uptime_monitor_latency_ms",
        "gauge",
        "Latency of the last check in milliseconds",
        [(lbl(r), r["latency_ms"]) for r in rows if r.get("latency_ms") is not None],
    )
    metric(
        "uptime_monitor_checks_total",
        "counter",
        "Checks since start, by result",
        [s for r in rows for s in ((lbl(r, result="ok"), r["ok_total"]), (lbl(r, result="fail"), r["fail_total"]))],
    )
    certs = [(lbl(r), r["cert_days_left"]) for r in rows if r.get("cert_days_left") is not None]
    if certs:
        metric("uptime_monitor_cert_days_left", "gauge", "Days until the TLS certificate expires", certs)
    return "\n".join(out) + "\n"
