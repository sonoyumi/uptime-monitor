"""Shared helpers: a controllable clock, fake network pieces and a notifier that records alerts."""

import asyncio
import ssl
import time

import httpx
import pytest

from uptime_monitor.store import Store


class Clock:
    def __init__(self, now: float = 1_790_000_000.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> bool:
        self.sent.append(text)
        return True


class FakeWriter:
    def __init__(self, peercert: dict | None = None) -> None:
        self.peercert = peercert
        self.closed = False

    def get_extra_info(self, key: str):
        return self.peercert if key == "peercert" else None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass


def cert_expiring_in(days: float, now: float = time.time()) -> dict:
    return {"notAfter": time.strftime("%b %d %H:%M:%S %Y GMT", time.gmtime(now + days * 86400))}


def opener(behaviour):
    """Fake asyncio.open_connection: behaviour is a writer to return, an exception to raise, or 'hang'."""
    calls = []

    async def open_connection(host, port, **kwargs):
        calls.append((host, port, kwargs))
        if behaviour == "hang":
            await asyncio.sleep(3600)
        if isinstance(behaviour, BaseException):
            raise behaviour
        return None, behaviour

    open_connection.calls = calls
    return open_connection


def web(routes: dict):
    """httpx client whose 'internet' is a dict: url -> Response, exception or callable."""

    def handler(request: httpx.Request) -> httpx.Response:
        route = routes.get(str(request.url))
        if route is None:
            return httpx.Response(404)
        if isinstance(route, Exception):
            raise route
        return route(request) if callable(route) else route

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
async def store():
    s = await Store.open(":memory:")
    yield s
    await s.close()


SSL_ERROR = ssl.SSLCertVerificationError(1, "certificate verify failed")
SSL_ERROR.verify_message = "certificate has expired"
