"""Settings: `.env` for secrets and paths, `monitors.toml` for what to watch.

monitors.toml:

    [defaults]            # optional, applies to every monitor
    interval = 60
    fail_threshold = 3

    [[monitor]]
    name = "Website"
    type = "http"
    url = "https://example.com"
    keyword = "Book now"

Every mistake in the file is reported with the monitor name, all at once.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from dotenv import load_dotenv

from uptime_monitor.models import KINDS, Monitor

_ALLOWED = {f.name for f in fields(Monitor)} - {"kind"} | {"type"}
_INT_FIELDS = {"interval", "fail_threshold", "recover_threshold", "remind_every", "max_latency_ms", "port", "cert_days"}


class ConfigError(ValueError):
    def __init__(self, errors: list[str]) -> None:
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass(frozen=True)
class Settings:
    monitors_file: Path
    database_path: Path
    bot_token: str = field(default="", repr=False)
    chat_id: str = ""
    host: str = "127.0.0.1"
    port: int = 8090
    retention_days: int = 90
    status_title: str = "Статус сервисов"


def _monitor(raw: dict, defaults: dict, errors: list[str], index: int) -> Monitor | None:
    data = {**defaults, **raw}
    name = str(data.get("name", "")).strip()
    where = f"monitor «{name}»" if name else f"monitor #{index}"
    problems = []
    unknown = set(data) - _ALLOWED
    if unknown:
        problems.append(f"unknown keys: {', '.join(sorted(unknown))}")
    kind = data.pop("type", "")
    if kind not in KINDS:
        problems.append(f"type must be one of {', '.join(KINDS)}")
    if not name:
        problems.append("name is required")
    for key in _INT_FIELDS & data.keys():
        if not isinstance(data[key], int) or isinstance(data[key], bool) or data[key] < 0:
            problems.append(f"{key} must be a whole number ≥ 0")
    if isinstance(data.get("interval"), int) and data["interval"] < 10:
        problems.append("interval must be at least 10 seconds")
    for key in ("fail_threshold", "recover_threshold"):
        if isinstance(data.get(key), int) and data[key] < 1:
            problems.append(f"{key} must be at least 1")
    if kind == "http" and not str(data.get("url", "")).startswith(("http://", "https://")):
        problems.append("url must start with http:// or https://")
    if kind in ("tcp", "tls") and (not data.get("host") or not isinstance(data.get("port"), int) or not data["port"]):
        problems.append("host and port are required")
    if "expect_status" in data:
        codes = data["expect_status"]
        codes = [codes] if isinstance(codes, int) else codes
        if not isinstance(codes, list) or not all(isinstance(c, int) and 100 <= c <= 599 for c in codes):
            problems.append("expect_status must be a status code or a list of codes")
        else:
            data["expect_status"] = tuple(codes)
    if problems:
        errors.append(f"{where}: " + "; ".join(problems))
        return None
    data["method"] = str(data.get("method", "GET")).upper()
    return Monitor(kind=kind, **{k: v for k, v in data.items() if k != "name"}, name=name)


def load_monitors(path: Path) -> list[Monitor]:
    try:
        doc = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigError([f"file not found: {path}"]) from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError([f"{path.name}: TOML syntax error: {exc}"]) from None
    defaults = doc.get("defaults", {})
    raw_monitors = doc.get("monitor", [])
    errors: list[str] = []
    if not isinstance(defaults, dict) or not isinstance(raw_monitors, list):
        raise ConfigError(["use [defaults] and [[monitor]] sections"])
    if not raw_monitors:
        errors.append("no [[monitor]] sections: nothing to watch")
    monitors = [m for i, raw in enumerate(raw_monitors, 1) if (m := _monitor(raw, defaults, errors, i))]
    names = [m.name for m in monitors]
    errors.extend(f"duplicate monitor name «{n}»" for n in sorted({n for n in names if names.count(n) > 1}))
    if errors:
        raise ConfigError(errors)
    return monitors


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from None


def load_settings(env_file: Path | None = Path(".env")) -> Settings:
    if env_file is not None:
        load_dotenv(env_file)
    return Settings(
        monitors_file=Path(os.getenv("MONITORS_FILE", "").strip() or "monitors.toml"),
        database_path=Path(os.getenv("DATABASE_PATH", "").strip() or "data/uptime.db"),
        bot_token=os.getenv("BOT_TOKEN", "").strip(),
        chat_id=os.getenv("CHAT_ID", "").strip(),
        host=os.getenv("HOST", "").strip() or "127.0.0.1",
        port=_int("PORT", 8090),
        retention_days=_int("RETENTION_DAYS", 90),
        status_title=os.getenv("STATUS_TITLE", "").strip() or "Статус сервисов",
    )
