"""Command line.

uptime-monitor run      checks on schedule + web page on HOST:PORT (/, /api/status, /metrics)
uptime-monitor check    every monitor once, a table, exit code 1 if something is down (for cron/CI)
uptime-monitor stats    uptime for 24 h / 7 days / 30 days from the history
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import sys
import time
from collections.abc import Sequence

import httpx

from uptime_monitor import __version__
from uptime_monitor.checks import run_check
from uptime_monitor.config import ConfigError, Settings, load_monitors, load_settings
from uptime_monitor.models import Monitor
from uptime_monitor.notifier import LogNotifier, Notifier, TelegramNotifier
from uptime_monitor.store import Store


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="uptime-monitor", description="Uptime monitoring with alerts")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="run checks on schedule and the web page")
    sub.add_parser("check", help="check every monitor once")
    sub.add_parser("stats", help="uptime from the history")
    return p


def make_notifier(settings: Settings, client: httpx.AsyncClient) -> Notifier:
    if settings.bot_token and settings.chat_id:
        return TelegramNotifier(client, settings.bot_token, settings.chat_id)
    return LogNotifier()


async def check_all(monitors: list[Monitor], client: httpx.AsyncClient, opener=asyncio.open_connection) -> int:
    results = await asyncio.gather(*(run_check(m, client, opener) for m in monitors))
    width = max(len(m.name) for m in monitors)
    failed = 0
    for m, r in zip(monitors, results, strict=True):
        mark = "✅" if r.ok else "❌"
        failed += not r.ok
        extra = f"  {r.error}" if r.error else ""
        cert = r.detail.get("cert_days_left")
        cert = f"  сертификат: {cert:g} дн." if cert is not None and r.ok else ""
        print(f"{mark} {m.name.ljust(width)}  {m.kind:<4} {r.latency_ms:>8.1f} мс{cert}{extra}")
    print(f"\nВсего: {len(monitors)} · работают: {len(monitors) - failed} · недоступны: {failed}")
    return 1 if failed else 0


async def show_stats(settings: Settings, monitors: list[Monitor], now: float | None = None) -> int:
    store = await Store.open(settings.database_path)
    now = now or time.time()
    try:
        width = max(len(m.name) for m in monitors)
        print(f"{'Монитор'.ljust(width)}   24 ч       7 дн       30 дн      p95 (7 дн)")
        for m in monitors:
            cells = []
            for days in (1, 7, 30):
                s = await store.stats(m.name, now - days * 86400)
                cells.append("—".ljust(10) if s.uptime is None else f"{s.uptime:.2f}%".ljust(10))
            p95 = (await store.stats(m.name, now - 7 * 86400)).p95_ms
            print(f"{m.name.ljust(width)}   {' '.join(cells)} {'—' if p95 is None else f'{p95:.0f} мс'}")
    finally:
        await store.close()
    return 0


async def serve(settings: Settings, monitors: list[Monitor]) -> None:
    import uvicorn

    from uptime_monitor.engine import Engine
    from uptime_monitor.web import create_app

    store = await Store.open(settings.database_path)
    async with httpx.AsyncClient(headers={"User-Agent": f"uptime-monitor/{__version__}"}) as client:
        engine = Engine(
            monitors, store, make_notifier(settings, client), client, retention_days=settings.retention_days
        )
        await engine.restore()
        stop = asyncio.Event()
        checks = asyncio.create_task(engine.run(stop))
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(engine, settings.status_title), host=settings.host, port=settings.port, log_level="warning"
            )
        )
        logging.getLogger(__name__).info(
            "Watching %d monitors, page on http://%s:%s", len(monitors), settings.host, settings.port
        )
        try:
            await server.serve()  # returns on Ctrl+C / SIGTERM (uvicorn handles the signals)
        finally:
            stop.set()
            with contextlib.suppress(asyncio.CancelledError):
                await checks
            await store.close()


def run(argv: Sequence[str] | None = None, settings: Settings | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = settings or load_settings()
        monitors = load_monitors(settings.monitors_file)
    except ConfigError as exc:
        print("Ошибки в настройках мониторов:", file=sys.stderr)
        for error in exc.errors:
            print(f"  {error}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"Ошибка настроек: {exc}", file=sys.stderr)
        return 2
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per request is noise here
    if args.command == "check":

        async def once() -> int:
            async with httpx.AsyncClient() as client:
                return await check_all(monitors, client)

        return asyncio.run(once())
    if args.command == "stats":
        return asyncio.run(show_stats(settings, monitors))
    asyncio.run(serve(settings, monitors))
    return 0


def main() -> int:
    return run()
