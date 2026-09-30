"""The three kinds of checks. Each returns a CheckResult and never raises:
a check that crashes would be indistinguishable from a service that is down.

Network access is passed in (an httpx client, a connection opener), so tests replace it.
"""

from __future__ import annotations

import asyncio
import ssl
import time
from collections.abc import Awaitable, Callable

import httpx

from uptime_monitor.models import CheckResult, Monitor

Opener = Callable[..., Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


async def check_http(client: httpx.AsyncClient, m: Monitor) -> CheckResult:
    started = time.perf_counter()
    try:
        response = await client.request(m.method, m.url, timeout=m.timeout, follow_redirects=True)
    except httpx.TimeoutException:
        return CheckResult(False, _ms(started), f"timeout after {m.timeout:g} s")
    except httpx.HTTPError as exc:
        return CheckResult(False, _ms(started), f"connection error: {type(exc).__name__}")
    latency = _ms(started)
    detail = {"status": response.status_code}
    if response.status_code not in m.expect_status:
        return CheckResult(False, latency, f"HTTP {response.status_code}", detail)
    if m.keyword and m.keyword not in response.text:
        return CheckResult(False, latency, f"keyword «{m.keyword}» not found", detail)
    if m.max_latency_ms and latency > m.max_latency_ms:
        return CheckResult(False, latency, f"slow: {latency:.0f} ms > {m.max_latency_ms} ms", detail)
    return CheckResult(True, latency, "", detail)


async def _close(writer: asyncio.StreamWriter) -> None:
    writer.close()
    try:
        await writer.wait_closed()
    except (OSError, ssl.SSLError):
        pass


async def check_tcp(m: Monitor, opener: Opener = asyncio.open_connection) -> CheckResult:
    started = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(opener(m.host, m.port), m.timeout)
    except TimeoutError:
        return CheckResult(False, _ms(started), f"timeout after {m.timeout:g} s")
    except OSError as exc:
        return CheckResult(False, _ms(started), f"connection refused or unreachable ({exc.strerror or exc})")
    await _close(writer)
    return CheckResult(True, _ms(started))


async def check_tls(m: Monitor, opener: Opener = asyncio.open_connection, now: float | None = None) -> CheckResult:
    """Opens a verified TLS connection and reads the certificate's expiry date."""
    started = time.perf_counter()
    context = ssl.create_default_context()  # verifies the chain and the host name
    try:
        _, writer = await asyncio.wait_for(opener(m.host, m.port, ssl=context, server_hostname=m.host), m.timeout)
    except TimeoutError:
        return CheckResult(False, _ms(started), f"timeout after {m.timeout:g} s")
    except ssl.SSLCertVerificationError as exc:
        return CheckResult(False, _ms(started), f"certificate is not valid: {exc.verify_message}")
    except (OSError, ssl.SSLError) as exc:
        return CheckResult(False, _ms(started), f"TLS connection failed ({exc})")
    cert = writer.get_extra_info("peercert") or {}
    await _close(writer)
    latency = _ms(started)
    try:
        expires = ssl.cert_time_to_seconds(cert["notAfter"])
    except (KeyError, ValueError):
        return CheckResult(False, latency, "server sent no readable certificate")
    days_left = round((expires - (now if now is not None else time.time())) / 86400, 1)
    detail = {"cert_days_left": days_left}
    if days_left < m.cert_days:
        return CheckResult(False, latency, f"certificate expires in {days_left:g} days", detail)
    return CheckResult(True, latency, "", detail)


async def run_check(m: Monitor, client: httpx.AsyncClient, opener: Opener = asyncio.open_connection) -> CheckResult:
    try:
        if m.kind == "http":
            return await check_http(client, m)
        if m.kind == "tcp":
            return await check_tcp(m, opener)
        return await check_tls(m, opener)
    except Exception as exc:  # last line of defence: a bug in a check must not stop the monitor
        return CheckResult(False, 0.0, f"check crashed: {type(exc).__name__}: {exc}")
