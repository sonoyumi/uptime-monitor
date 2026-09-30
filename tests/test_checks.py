import httpx
import pytest
from conftest import SSL_ERROR, FakeWriter, cert_expiring_in, opener, web

from uptime_monitor.checks import check_http, check_tcp, check_tls, run_check
from uptime_monitor.models import Monitor

URL = "https://shop.example/"


def http(**kw) -> Monitor:
    return Monitor(name="Shop", kind="http", url=URL, **kw)


@pytest.mark.parametrize(
    ("route", "monitor", "ok", "error"),
    [
        (httpx.Response(200, text="Book now"), http(keyword="Book now"), True, ""),
        (httpx.Response(503), http(), False, "HTTP 503"),
        (httpx.Response(301), http(expect_status=(200, 301)), True, ""),
        (httpx.Response(200, text="Maintenance"), http(keyword="Book now"), False, "keyword «Book now» not found"),
        (httpx.ReadTimeout("slow"), http(timeout=2), False, "timeout after 2 s"),
        (httpx.ConnectError("refused"), http(), False, "connection error: ConnectError"),
    ],
)
async def test_http(route, monitor, ok, error):
    async with web({URL: route}) as client:
        result = await check_http(client, monitor)
    assert result.ok is ok and result.error == error
    assert result.latency_ms >= 0


async def test_http_too_slow(monkeypatch):
    # Replace only our own stopwatch: patching time.perf_counter itself would also affect httpx.
    monkeypatch.setattr("uptime_monitor.checks._ms", lambda started: 2500.0)
    async with web({URL: httpx.Response(200)}) as client:
        result = await check_http(client, http(max_latency_ms=1000))
    assert not result.ok and result.error == "slow: 2500 ms > 1000 ms"


async def test_tcp():
    writer = FakeWriter()
    ok = await check_tcp(Monitor("Db", "tcp", host="db", port=5432), opener(writer))
    assert ok.ok and writer.closed
    refused = await check_tcp(
        Monitor("Db", "tcp", host="db", port=5432), opener(ConnectionRefusedError(111, "Connection refused"))
    )
    assert not refused.ok and "Connection refused" in refused.error
    hang = await check_tcp(Monitor("Db", "tcp", host="db", port=5432, timeout=0.05), opener("hang"))
    assert hang.error == "timeout after 0.05 s"


async def test_tls_reads_expiry_and_verifies():
    m = Monitor("Cert", "tls", host="shop.example", port=443, cert_days=14)
    fake = opener(FakeWriter(cert_expiring_in(60, now=1_790_000_000)))
    good = await check_tls(m, fake, now=1_790_000_000)
    assert good.ok and good.detail["cert_days_left"] == 60
    assert fake.calls[0][2]["server_hostname"] == "shop.example"  # host name is checked, not only the chain

    soon = await check_tls(m, opener(FakeWriter(cert_expiring_in(5, now=1_790_000_000))), now=1_790_000_000)
    assert not soon.ok and soon.error == "certificate expires in 5 days"

    invalid = await check_tls(m, opener(SSL_ERROR))
    assert not invalid.ok and invalid.error == "certificate is not valid: certificate has expired"

    empty = await check_tls(m, opener(FakeWriter({})))
    assert empty.error == "server sent no readable certificate"


async def test_a_crashing_check_becomes_a_failure(monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("bug")

    monkeypatch.setattr("uptime_monitor.checks.check_tcp", boom)
    result = await run_check(Monitor("Db", "tcp", host="db", port=1), client=None)
    assert not result.ok and result.error == "check crashed: RuntimeError: bug"
