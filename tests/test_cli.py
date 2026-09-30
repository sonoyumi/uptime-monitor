import httpx
from conftest import FakeWriter, cert_expiring_in, opener, web

from uptime_monitor import cli
from uptime_monitor.config import Settings
from uptime_monitor.models import CheckResult, Monitor
from uptime_monitor.store import Store


async def test_check_all_table_and_exit_code(capsys):
    monitors = [
        Monitor("Site", "http", url="https://a.it/"),
        Monitor("Broken", "http", url="https://b.it/"),
        Monitor("Cert", "tls", host="a.it", port=443),
    ]
    routes = {"https://a.it/": httpx.Response(200), "https://b.it/": httpx.Response(502)}
    async with web(routes) as client:
        code = await cli.check_all(monitors, client, opener(FakeWriter(cert_expiring_in(90))))
    out = capsys.readouterr().out
    assert code == 1
    assert "✅ Site" in out and "❌ Broken" in out and "HTTP 502" in out and "сертификат: 90 дн." in out
    assert "Всего: 3 · работают: 2 · недоступны: 1" in out


async def test_stats_command(tmp_path, capsys):
    db = tmp_path / "u.db"
    store = await Store.open(db)
    now = 1_790_000_000.0
    for i in range(4):
        await store.add_result("Site", CheckResult(i != 0, 100.0), now - 100 * i)
    await store.close()
    settings = Settings(monitors_file=tmp_path / "m.toml", database_path=db)
    assert await cli.show_stats(settings, [Monitor("Site", "http", url="https://a.it")], now=now) == 0
    assert "75.00%" in capsys.readouterr().out


def test_bad_config_exit_code_2(tmp_path, capsys):
    (tmp_path / "m.toml").write_text('[[monitor]]\nname = "X"\ntype = "ping"')
    settings = Settings(monitors_file=tmp_path / "m.toml", database_path=tmp_path / "u.db")
    assert cli.run(["check"], settings=settings) == 2
    assert "monitor «X»: type must be one of" in capsys.readouterr().err
