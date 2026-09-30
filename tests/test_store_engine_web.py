import asyncio

import httpx
import pytest
from conftest import RecordingNotifier, web

from uptime_monitor.engine import Engine
from uptime_monitor.metrics import label, render
from uptime_monitor.models import CheckResult, Monitor
from uptime_monitor.store import percentile
from uptime_monitor.texts import duration
from uptime_monitor.web import create_app

URL = "https://shop.example/"


def test_percentile_and_duration():
    assert percentile([], 95) is None
    assert percentile(list(range(1, 21)), 95) == 19 and percentile([5.0], 95) == 5.0
    assert duration(45) == "меньше минуты" and duration(3725) == "1 ч 2 мин" and duration(90000) == "1 д 1 ч"


async def test_stats_incidents_and_cleanup(store, clock):
    for i in range(10):
        await store.add_result("A", CheckResult(i != 3, 100 + i), clock.now - 3600 + i)
    await store.add_result("A", CheckResult(True, 999), clock.now - 10 * 86400)  # outside 24 h
    day = await store.stats("A", clock.now - 86400)
    assert day.checks == 10 and day.uptime == 90.0 and day.avg_ms == pytest.approx(104.6, 0.01) and day.p95_ms == 109
    assert (await store.stats("B", 0)).uptime is None

    await store.open_incident("A", clock.now - 120, "HTTP 503")
    assert list(await store.open_incidents()) == ["A"]
    await store.close_incident("A", clock.now)
    [incident] = await store.incidents("A")
    assert incident.duration == 120 and await store.open_incidents() == {}
    assert await store.cleanup(clock.now - 86400) == 1


def engine_for(routes, clock, store, notifier, **monitor):
    m = Monitor("Shop", "http", url=URL, fail_threshold=2, recover_threshold=1, remind_every=0, **monitor)
    return Engine([m], store, notifier, web(routes), clock=clock)


async def test_engine_opens_and_closes_incidents(store, clock):
    notifier = RecordingNotifier()
    state = {"code": 503}
    routes = {URL: lambda request: httpx.Response(state["code"])}
    engine = engine_for(routes, clock, store, notifier)
    for _ in range(3):
        await engine.check_once("Shop")
        clock.advance(60)
    assert notifier.sent == ["🔴 <b>Shop</b> недоступен\nHTTP 503"]
    assert list(await store.open_incidents()) == ["Shop"]
    state["code"] = 200
    event = await engine.check_once("Shop")
    assert event.kind == "up" and notifier.sent[-1] == "🟢 <b>Shop</b> снова работает\nНе работал: 2 мин"
    assert await store.open_incidents() == {}
    row = engine.snapshot()[0]
    assert (row["status"], row["up"], row["ok_total"], row["fail_total"]) == ("up", 1, 1, 3)


async def test_recovery_is_announced_after_restart(store, clock):
    await store.open_incident("Shop", clock.now - 600, "HTTP 503")  # left open by the previous run
    notifier = RecordingNotifier()
    engine = engine_for({URL: httpx.Response(200)}, clock, store, notifier)
    await engine.restore()
    assert engine.snapshot()[0]["status"] == "down"
    await engine.check_once("Shop")
    assert notifier.sent == ["🟢 <b>Shop</b> снова работает\nНе работал: 10 мин"]


async def test_run_loop_checks_until_stopped(store, clock):
    engine = engine_for({URL: httpx.Response(200)}, clock, store, RecordingNotifier(), interval=0)
    stop = asyncio.Event()
    task = asyncio.create_task(engine.run(stop))
    await asyncio.sleep(0.3)
    stop.set()
    await asyncio.wait_for(task, 2)
    assert engine.snapshot()[0]["ok_total"] >= 2


def test_metrics_format_and_escaping():
    text = render(
        [
            {
                "monitor": 'A "quoted"\\name',
                "kind": "tls",
                "up": 0,
                "latency_ms": 12.5,
                "ok_total": 3,
                "fail_total": 1,
                "cert_days_left": 40.5,
            },
        ]
    )
    assert "# TYPE uptime_monitor_up gauge" in text
    assert 'uptime_monitor_up{monitor="A \\"quoted\\"\\\\name",type="tls"} 0' in text
    assert 'uptime_monitor_checks_total{monitor="A \\"quoted\\"\\\\name",type="tls",result="fail"} 1' in text
    assert "uptime_monitor_cert_days_left" in text and label("a\nb") == "a\\nb"


async def test_web_endpoints_and_escaping(store, clock):
    m = Monitor("<script>alert(1)</script>", "http", url=URL, fail_threshold=1, remind_every=0)
    engine = Engine([m], store, RecordingNotifier(), web({URL: httpx.Response(500)}), clock=clock)
    await engine.check_once(m.name)
    app = create_app(engine, "Status Alpina")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as client:
        status = (await client.get("/api/status")).json()
        assert status["overall"] == "down" and status["monitors"][0]["uptime_24h"] == 0.0
        page = (await client.get("/")).text
        assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page and "Проблемы: 1 из 1" in page
        metrics = await client.get("/metrics")
        assert metrics.headers["content-type"].startswith("text/plain") and "uptime_monitor_up" in metrics.text
        assert (await client.get("/health")).json()["status"] == "ok"
