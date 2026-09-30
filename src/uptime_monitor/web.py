"""Web part: the status page, JSON for other tools and /metrics for Prometheus.

No `from __future__ import annotations`: FastAPI reads annotations at runtime.
"""

from datetime import datetime
from html import escape

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse

from uptime_monitor import __version__, metrics
from uptime_monitor.engine import Engine
from uptime_monitor.texts import duration

PERIODS = {"24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400}
BADGE = {"up": ("🟢", "работает"), "down": ("🔴", "недоступен"), "unknown": ("⚪", "проверяется")}


def create_app(engine: Engine, title: str = "Статус сервисов") -> FastAPI:
    app = FastAPI(title="Uptime monitor", version=__version__, docs_url=None, redoc_url=None)

    async def status_rows() -> list[dict]:
        now = engine.clock()
        rows = engine.snapshot()
        for row in rows:
            for key, seconds in PERIODS.items():
                row[f"uptime_{key}"] = (await engine.store.stats(row["monitor"], now - seconds)).uptime
        return rows

    @app.get("/metrics", response_class=PlainTextResponse)
    async def prometheus():
        return PlainTextResponse(metrics.render(engine.snapshot()), media_type="text/plain; version=0.0.4")

    @app.get("/api/status")
    async def api_status():
        rows = await status_rows()
        return {"overall": "down" if any(r["status"] == "down" for r in rows) else "up", "monitors": rows}

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": __version__}

    @app.get("/", response_class=HTMLResponse)
    async def page():
        rows = await status_rows()
        incidents = await engine.store.incidents(limit=10)
        return HTMLResponse(render_page(title, rows, incidents, engine.clock()))

    return app


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.2f}%"


def render_page(title: str, rows: list[dict], incidents, now: float) -> str:
    down = [r for r in rows if r["status"] == "down"]
    banner = (
        f'<p class="banner bad">Проблемы: {len(down)} из {len(rows)}</p>'
        if down
        else '<p class="banner good">Все сервисы работают</p>'
    )
    cards = []
    for r in rows:
        icon, word = BADGE[r["status"]]
        extra = ""
        if r["status"] == "down" and r["down_since"]:
            extra = f" · {duration(now - r['down_since'])} · {escape(r['last_error'] or '')}"
        elif r.get("cert_days_left") is not None:
            extra = f" · сертификат: {r['cert_days_left']:g} дн."
        latency = f"{r['latency_ms']:.0f} мс" if r["latency_ms"] is not None else "—"
        cards.append(
            f"<tr><td>{icon} <b>{escape(r['monitor'])}</b><br><small>{word}{extra}</small></td>"
            f"<td>{latency}</td><td>{_pct(r['uptime_24h'])}</td><td>{_pct(r['uptime_7d'])}</td>"
            f"<td>{_pct(r['uptime_30d'])}</td></tr>"
        )
    history = (
        "".join(
            f"<li>{escape(i.monitor)}: {datetime.fromtimestamp(i.started_at):%d.%m %H:%M}, "
            f"{'идёт сейчас' if i.ended_at is None else duration(i.duration)} — {escape(i.error)}</li>"
            for i in incidents
        )
        or "<li>Инцидентов не было</li>"
    )
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60"><title>{escape(title)}</title>
<style>
:root {{ --bg:#f5f7f6; --card:#fff; --ink:#1c2420; --muted:#5f6b65; --good:#2d7a4b; --bad:#b3261e; --line:#dde3df; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#121715; --card:#1a211e; --ink:#e3ebe6; --muted:#98a69f;
  --good:#6cc28e; --bad:#f2837a; --line:#2c3833; }} }}
body {{ margin:0; padding:24px 16px; background:var(--bg); color:var(--ink); font:15px/1.5 system-ui, sans-serif; }}
main {{ max-width:860px; margin:0 auto; display:flex; flex-direction:column; gap:16px; }}
h1 {{ margin:0; font-size:22px; }} .banner {{ margin:0; padding:12px 14px; border-radius:10px; font-weight:600; }}
.good {{ background:color-mix(in srgb, var(--good) 15%, transparent); color:var(--good); }}
.bad {{ background:color-mix(in srgb, var(--bad) 15%, transparent); color:var(--bad); }}
.wrap {{ overflow-x:auto; background:var(--card); border:1px solid var(--line); border-radius:10px; }}
table {{ width:100%; border-collapse:collapse; }}
th, td {{ padding:10px 12px; text-align:left; border-top:1px solid var(--line); }}
thead th {{ border-top:0; color:var(--muted); font-size:12px; text-transform:uppercase;
  letter-spacing:.05em; }}
td:not(:first-child) {{ font-variant-numeric:tabular-nums; white-space:nowrap; }}
small, footer {{ color:var(--muted); }}
</style></head>
<body><main>
<h1>{escape(title)}</h1>
{banner}
<div class="wrap"><table><thead><tr><th>Сервис</th><th>Отклик</th><th>24 ч</th><th>7 дн</th><th>30 дн</th></tr></thead>
<tbody>{"".join(cards)}</tbody></table></div>
<h2>Последние инциденты</h2><ul>{history}</ul>
<footer>Обновлено {datetime.fromtimestamp(now):%d.%m.%Y %H:%M:%S} · страница обновляется каждую минуту</footer>
</main></body></html>"""
