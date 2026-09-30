"""Alert texts (Telegram HTML) and human-friendly durations."""

from __future__ import annotations

from html import escape

from uptime_monitor.state import Event


def duration(seconds: float) -> str:
    """3725 -> '1 ч 2 мин'; 45 -> 'меньше минуты'."""
    minutes = int(seconds // 60)
    if minutes < 1:
        return "меньше минуты"
    days, rest = divmod(minutes, 1440)
    hours, mins = divmod(rest, 60)
    parts = [f"{days} д" if days else "", f"{hours} ч" if hours else "", f"{mins} мин" if mins else ""]
    return " ".join(p for p in parts if p)


def alert_text(event: Event) -> str:
    name = escape(event.monitor)
    if event.kind == "down":
        return f"🔴 <b>{name}</b> недоступен\n{escape(event.error)}"
    if event.kind == "up":
        return f"🟢 <b>{name}</b> снова работает\nНе работал: {duration(event.duration)}"
    return f"⏰ <b>{name}</b> всё ещё недоступен ({duration(event.duration)})\n{escape(event.error)}"
