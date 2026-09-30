# uptime-monitor

Короткое описание: что делает проект и зачем.

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # заполнить своими значениями
uptime-monitor           # или: python -m uptime_monitor
```

## Тесты и линтер

```bash
pytest
ruff check .
```

## Структура

```
src/uptime_monitor/   код
tests/              тесты
```
