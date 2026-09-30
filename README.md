# 📡 Uptime Monitor

<p>
  <a href="https://github.com/sonoyumi/uptime-monitor/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/sonoyumi/uptime-monitor/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white">
  <img alt="asyncio" src="https://img.shields.io/badge/asyncio-httpx-4B8BBE">
  <img alt="Prometheus" src="https://img.shields.io/badge/Prometheus-metrics-E6522C?logo=prometheus&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green">
</p>

**🇬🇧 [English](#en)** · **🇮🇹 [Italiano](#it)** · **🇺🇦 [Українська](#uk)** · **🇷🇺 [Русский](#ru)**

---

<a name="en"></a>

## 🇬🇧 English

A self-hosted uptime monitor: it checks websites, APIs, ports and TLS certificates on a schedule, sends a Telegram
alert when something goes down (and when it comes back, with the downtime), keeps the history, calculates uptime and
latency, serves a public status page and exposes metrics for Prometheus/Grafana. One small process, one SQLite file.

```
monitors.toml ──► engine (one asyncio task per monitor) ──► check: http · tcp · tls
                        │                                         │
                        ▼                                         ▼
              state machine (anti-flapping) ──event──► Telegram alert + incident
                        │
                        ▼
              SQLite history ──► status page · /api/status · /metrics (Prometheus)
```

### Features

- **Checks:** HTTP(S) with expected status codes, a keyword that must be on the page and a latency limit; TCP ports
  (databases, Redis, mail); TLS certificates: verified chain and host name, alert N days before expiry.
- **No false alarms:** a monitor goes DOWN only after N consecutive failures and UP after M successes (anti-flapping).
  A single network hiccup at night does not wake anyone up.
- **Alerts:** "down" with the reason, reminders while it stays down, "back up" with the downtime. Telegram, or the log
  when no token is set; the notifier is an interface, so e-mail or Slack are one class away.
- **History and numbers:** every result in SQLite, incidents with start and end, uptime for 24 h / 7 days / 30 days,
  average and p95 latency, old results cleaned up automatically. After a restart, open incidents are restored,
  so the recovery is still announced.
- **Status page** (auto-refresh, light and dark theme), **JSON** at `/api/status`, **Prometheus** metrics at `/metrics`
  (`uptime_monitor_up`, latency, check counters, certificate days left).
- **Configuration in TOML** with defaults; every mistake in the file is reported at once with the monitor name.
- **CLI:** `run` (schedule + web page), `check` (one pass, exit code 1 if something is down: for cron and CI), `stats`.

### Example

```bash
uptime-monitor check
```

```
✅ Сайт example.com         http    102.9 мс
✅ API health               http    457.6 мс
✅ DNS Cloudflare (TCP 53)  tcp      15.9 мс
✅ Сертификат github.com    tls     114.9 мс  сертификат: 61 дн.

Всего: 4 · работают: 4 · недоступны: 0
```

Real run of [`monitors.example.toml`](monitors.example.toml): a website with a keyword, an API, a TCP port and a TLS
certificate (61 days left). Output is in Russian: "All: 4 · up: 4 · down: 0". Failures look like this:

```
❌ HTTP 500                 http    485.1 мс  HTTP 500
❌ Нет слова                http     70.9 мс  keyword «Prenota ora» not found
❌ Закрытый порт            tcp    4014.7 мс  timeout after 4 s
❌ Просроченный сертификат  tls     667.6 мс  certificate is not valid: certificate has expired
❌ Чужой домен              tls     628.5 мс  certificate is not valid: Hostname mismatch, …
```

Telegram alerts: `🔴 Сайт недоступен — HTTP 503`, `⏰ … всё ещё недоступен (30 мин)`, `🟢 Сайт снова работает — не работал: 12 мин`.

### Quick start

```bash
git clone https://github.com/sonoyumi/uptime-monitor.git
cd uptime-monitor
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env && cp monitors.example.toml monitors.toml    # your services; BOT_TOKEN and CHAT_ID for alerts
uptime-monitor check
uptime-monitor run                                                 # status page on http://127.0.0.1:8090
```

Tests: `pytest` (31 tests: config validation, every check with a fake network, the anti-flapping state machine,
uptime and percentiles, incidents across a restart, the scheduler loop, metrics escaping, the status page against HTML
injection, CLI). No network needed.

### Project structure

```
src/uptime_monitor/
├── config.py    # .env + monitors.toml, validation with all errors at once
├── models.py    # Monitor, CheckResult
├── checks.py    # http, tcp, tls checks (never raise)
├── state.py     # anti-flapping state machine: a pure function
├── store.py     # SQLite: results, incidents, uptime, p95
├── engine.py    # one asyncio task per monitor, alerts, restore after restart
├── notifier.py  # Telegram / log
├── metrics.py   # Prometheus text format
├── web.py       # status page, /api/status, /metrics
├── texts.py     # alert texts
└── cli.py       # uptime-monitor run | check | stats
```

### Author

**Vladyslav Shokun** ([@sonoyumi](https://github.com/sonoyumi)), Python developer: Telegram bots, web scraping, automation.

[![Telegram](https://img.shields.io/badge/Telegram-write%20me-2CA5E0?logo=telegram&logoColor=white)](https://t.me/sonoyumiii)
[![Email](https://img.shields.io/badge/Email-contact-EA4335?logo=gmail&logoColor=white)](mailto:sonoyumiii@gmail.com)

> 💼 Learn about outages from your customers? Get in touch, I'll set up monitoring for your services.

### License

MIT, see [LICENSE](LICENSE).

---

<a name="it"></a>

## 🇮🇹 Italiano

**[🇬🇧 English](#en)** · **🇮🇹 Italiano** · **[🇺🇦 Українська](#uk)** · **[🇷🇺 Русский](#ru)**

Un monitor di disponibilità da installare sul proprio server: controlla siti, API, porte e certificati TLS a intervalli
regolari, manda un avviso su Telegram quando qualcosa smette di funzionare (e quando torna, con la durata del disservizio),
conserva lo storico, calcola disponibilità e tempi di risposta, pubblica una pagina di stato ed espone metriche per
Prometheus/Grafana. Un solo piccolo processo, un solo file SQLite.

### Funzionalità

- **Controlli:** HTTP(S) con codici di stato attesi, una parola che deve comparire nella pagina e un limite di tempo;
  porte TCP (database, Redis, posta); certificati TLS: catena e nome host verificati, avviso N giorni prima della scadenza.
- **Niente falsi allarmi:** un monitor va DOWN solo dopo N errori consecutivi e torna UP dopo M successi (anti-flapping).
  Un singolo intoppo di rete di notte non sveglia nessuno.
- **Avvisi:** «non raggiungibile» con il motivo, promemoria finché resta giù, «di nuovo attivo» con la durata. Telegram,
  oppure il log se non c'è un token; il notificatore è un'interfaccia, quindi e-mail o Slack sono a una classe di distanza.
- **Storico e numeri:** ogni risultato in SQLite, incidenti con inizio e fine, disponibilità a 24 ore / 7 / 30 giorni,
  latenza media e p95, pulizia automatica dei vecchi risultati. Dopo un riavvio gli incidenti aperti vengono ripristinati,
  così il ritorno in servizio viene comunque annunciato.
- **Pagina di stato** (aggiornamento automatico, tema chiaro e scuro), **JSON** su `/api/status`, metriche **Prometheus**
  su `/metrics` (`uptime_monitor_up`, latenza, contatori, giorni alla scadenza del certificato).
- **Configurazione in TOML** con valori predefiniti; ogni errore nel file viene segnalato insieme agli altri con il nome del monitor.
- **CLI:** `run` (pianificazione + pagina), `check` (un passaggio, codice 1 se qualcosa non va: per cron e CI), `stats`.

### Esempio

Vedi la sezione inglese: un giro reale di [`monitors.example.toml`](monitors.example.toml) (sito con parola chiave, API,
porta TCP, certificato TLS con 61 giorni rimasti) e i casi di errore: HTTP 500, parola non trovata, porta chiusa,
certificato scaduto, certificato per un altro dominio. L'output è in russo: «Totale: 4 · attivi: 4 · non raggiungibili: 0».

### Avvio rapido

```bash
git clone https://github.com/sonoyumi/uptime-monitor.git
cd uptime-monitor
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env && cp monitors.example.toml monitors.toml    # i vostri servizi; BOT_TOKEN e CHAT_ID per gli avvisi
uptime-monitor check
uptime-monitor run                                                 # pagina di stato su http://127.0.0.1:8090
```

Test: `pytest` (31 test: validazione della configurazione, ogni controllo con una rete finta, la macchina a stati
anti-flapping, disponibilità e percentili, incidenti dopo un riavvio, il ciclo di pianificazione, l'escape delle metriche,
la pagina di stato contro l'iniezione HTML, CLI). Non serve la rete.

### Struttura del progetto

```
src/uptime_monitor/
├── config.py    # .env + monitors.toml, validazione con tutti gli errori insieme
├── models.py    # Monitor, CheckResult
├── checks.py    # controlli http, tcp, tls (non sollevano mai eccezioni)
├── state.py     # macchina a stati anti-flapping: una funzione pura
├── store.py     # SQLite: risultati, incidenti, disponibilità, p95
├── engine.py    # un task asyncio per monitor, avvisi, ripristino dopo il riavvio
├── notifier.py  # Telegram / log
├── metrics.py   # formato testo di Prometheus
├── web.py       # pagina di stato, /api/status, /metrics
├── texts.py     # testi degli avvisi
└── cli.py       # uptime-monitor run | check | stats
```

### Autore

**Vladyslav Shokun** ([@sonoyumi](https://github.com/sonoyumi)), sviluppatore Python: bot Telegram, web scraping, automazione.

[![Telegram](https://img.shields.io/badge/Telegram-write%20me-2CA5E0?logo=telegram&logoColor=white)](https://t.me/sonoyumiii)
[![Email](https://img.shields.io/badge/Email-contact-EA4335?logo=gmail&logoColor=white)](mailto:sonoyumiii@gmail.com)

> 💼 Scoprite i guasti dai vostri clienti? Scrivetemi, configuro il monitoraggio dei vostri servizi.

### Licenza

MIT, vedi [LICENSE](LICENSE).

---

<a name="uk"></a>

## 🇺🇦 Українська

**[🇬🇧 English](#en)** · **[🇮🇹 Italiano](#it)** · **🇺🇦 Українська** · **[🇷🇺 Русский](#ru)**

Монітор доступності на власному сервері: за розкладом перевіряє сайти, API, порти й TLS-сертифікати, надсилає
в Telegram сповіщення, коли щось «падає» (і коли повертається — з тривалістю простою), зберігає історію, рахує
доступність і час відгуку, показує сторінку статусу й віддає метрики для Prometheus/Grafana. Один невеликий процес,
один файл SQLite.

### Можливості

- **Перевірки:** HTTP(S) з очікуваними кодами, словом, яке має бути на сторінці, і лімітом часу; TCP-порти (бази,
  Redis, пошта); TLS-сертифікати: перевірка ланцюжка й імені хоста, тривога за N днів до закінчення.
- **Без хибних тривог:** монітор стає DOWN лише після N невдач поспіль і UP — після M успіхів (anti-flapping).
  Один нічний збій мережі нікого не будить.
- **Сповіщення:** «недоступний» з причиною, нагадування, поки лежить, «знову працює» з тривалістю. Telegram або лог,
  якщо токена немає; сповіщувач — інтерфейс, тож e-mail чи Slack — це один клас.
- **Історія й цифри:** кожен результат у SQLite, інциденти з початком і кінцем, доступність за 24 години / 7 / 30 днів,
  середній і p95 час відгуку, автоочищення старих результатів. Після перезапуску відкриті інциденти відновлюються,
  тож повернення все одно оголошується.
- **Сторінка статусу** (автооновлення, світла й темна тема), **JSON** на `/api/status`, метрики **Prometheus** на
  `/metrics` (`uptime_monitor_up`, час відгуку, лічильники, дні до закінчення сертифіката).
- **Налаштування в TOML** зі значеннями за замовчуванням; усі помилки у файлі показуються разом з назвою монітора.
- **CLI:** `run` (розклад + сторінка), `check` (один прохід, код 1, якщо щось лежить: для cron і CI), `stats`.

### Приклад

Дивіться англійський розділ: реальний прогін [`monitors.example.toml`](monitors.example.toml) (сайт зі словом, API,
TCP-порт, TLS-сертифікат із 61 днем) і випадки збоїв: HTTP 500, слово не знайдено, закритий порт, прострочений
сертифікат, сертифікат для іншого домену. Вивід російською: «Всього: 4 · працюють: 4 · недоступні: 0».

### Швидкий старт

```bash
git clone https://github.com/sonoyumi/uptime-monitor.git
cd uptime-monitor
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env && cp monitors.example.toml monitors.toml    # ваші сервіси; BOT_TOKEN і CHAT_ID для сповіщень
uptime-monitor check
uptime-monitor run                                                 # сторінка статусу на http://127.0.0.1:8090
```

Тести: `pytest` (31 тест: перевірка налаштувань, кожна перевірка з підробленою мережею, машина станів anti-flapping,
доступність і перцентилі, інциденти після перезапуску, цикл розкладу, екранування метрик, сторінка статусу проти
HTML-ін'єкцій, CLI). Мережа не потрібна.

### Структура проєкту

```
src/uptime_monitor/
├── config.py    # .env + monitors.toml, перевірка з усіма помилками разом
├── models.py    # Monitor, CheckResult
├── checks.py    # перевірки http, tcp, tls (ніколи не кидають винятків)
├── state.py     # машина станів anti-flapping: чиста функція
├── store.py     # SQLite: результати, інциденти, доступність, p95
├── engine.py    # одна asyncio-задача на монітор, сповіщення, відновлення після перезапуску
├── notifier.py  # Telegram / лог
├── metrics.py   # текстовий формат Prometheus
├── web.py       # сторінка статусу, /api/status, /metrics
├── texts.py     # тексти сповіщень
└── cli.py       # uptime-monitor run | check | stats
```

### Автор

**Vladyslav Shokun** ([@sonoyumi](https://github.com/sonoyumi)) — Python-розробник: Telegram-боти, парсинг, автоматизація.

[![Telegram](https://img.shields.io/badge/Telegram-write%20me-2CA5E0?logo=telegram&logoColor=white)](https://t.me/sonoyumiii)
[![Email](https://img.shields.io/badge/Email-contact-EA4335?logo=gmail&logoColor=white)](mailto:sonoyumiii@gmail.com)

> 💼 Дізнаєтеся про збої від клієнтів? Напишіть мені, налаштую моніторинг ваших сервісів.

### Ліцензія

MIT — див. [LICENSE](LICENSE).

---

<a name="ru"></a>

## 🇷🇺 Русский

**[🇬🇧 English](#en)** · **[🇮🇹 Italiano](#it)** · **[🇺🇦 Українська](#uk)** · **🇷🇺 Русский**

Монитор доступности на своём сервере: по расписанию проверяет сайты, API, порты и TLS-сертификаты, присылает
в Telegram уведомление, когда что-то «упало» (и когда вернулось — с длительностью простоя), хранит историю, считает
доступность и время отклика, показывает страницу статуса и отдаёт метрики для Prometheus/Grafana. Один небольшой
процесс, один файл SQLite.

### Возможности

- **Проверки:** HTTP(S) с ожидаемыми кодами, словом, которое должно быть на странице, и лимитом времени; TCP-порты
  (базы, Redis, почта); TLS-сертификаты: проверка цепочки и имени хоста, тревога за N дней до окончания.
- **Без ложных тревог:** монитор становится DOWN только после N неудач подряд и UP — после M успехов (anti-flapping).
  Один ночной сбой сети никого не будит.
- **Уведомления:** «недоступен» с причиной, напоминания, пока лежит, «снова работает» с длительностью. Telegram или лог,
  если токена нет; уведомитель — интерфейс, поэтому e-mail или Slack — это один класс.
- **История и цифры:** каждый результат в SQLite, инциденты с началом и концом, доступность за 24 часа / 7 / 30 дней,
  среднее и p95 время отклика, автоочистка старых результатов. После перезапуска открытые инциденты восстанавливаются,
  поэтому возвращение всё равно объявляется.
- **Страница статуса** (автообновление, светлая и тёмная тема), **JSON** на `/api/status`, метрики **Prometheus** на
  `/metrics` (`uptime_monitor_up`, время отклика, счётчики, дни до окончания сертификата).
- **Настройки в TOML** со значениями по умолчанию; все ошибки в файле показываются сразу с именем монитора.
- **CLI:** `run` (расписание + страница), `check` (один проход, код 1, если что-то лежит: для cron и CI), `stats`.

### Пример

Вывод настоящего прогона — в английском разделе выше: сайт с ключевым словом, API, TCP-порт, TLS-сертификат
(осталось 61 день) и случаи сбоев: HTTP 500, слово не найдено, закрытый порт, просроченный сертификат, сертификат
для другого домена.

### Быстрый старт

```bash
git clone https://github.com/sonoyumi/uptime-monitor.git
cd uptime-monitor
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env && cp monitors.example.toml monitors.toml    # ваши сервисы; BOT_TOKEN и CHAT_ID для уведомлений
uptime-monitor check
uptime-monitor run                                                 # страница статуса на http://127.0.0.1:8090
```

Тесты: `pytest` (31 тест: проверка настроек, каждая проверка с поддельной сетью, машина состояний anti-flapping,
доступность и перцентили, инциденты после перезапуска, цикл расписания, экранирование метрик, страница статуса
против HTML-инъекций, CLI). Сеть не нужна.

### Структура проекта

```
src/uptime_monitor/
├── config.py    # .env + monitors.toml, проверка со всеми ошибками сразу
├── models.py    # Monitor, CheckResult
├── checks.py    # проверки http, tcp, tls (никогда не бросают исключений)
├── state.py     # машина состояний anti-flapping: чистая функция
├── store.py     # SQLite: результаты, инциденты, доступность, p95
├── engine.py    # одна asyncio-задача на монитор, уведомления, восстановление после перезапуска
├── notifier.py  # Telegram / лог
├── metrics.py   # текстовый формат Prometheus
├── web.py       # страница статуса, /api/status, /metrics
├── texts.py     # тексты уведомлений
└── cli.py       # uptime-monitor run | check | stats
```

### Автор

**Vladyslav Shokun** ([@sonoyumi](https://github.com/sonoyumi)) — Python-разработчик: Telegram-боты, парсинг, автоматизация.

[![Telegram](https://img.shields.io/badge/Telegram-write%20me-2CA5E0?logo=telegram&logoColor=white)](https://t.me/sonoyumiii)
[![Email](https://img.shields.io/badge/Email-contact-EA4335?logo=gmail&logoColor=white)](mailto:sonoyumiii@gmail.com)

> 💼 Узнаёте о сбоях от клиентов? Напишите мне, настрою мониторинг ваших сервисов.

### Лицензия

MIT — см. [LICENSE](LICENSE).
