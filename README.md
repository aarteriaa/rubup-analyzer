# RubUp Analyzer

**Passive RTP / fairness analytics for third-party casino bots built on [StaticGram](https://staticgram.top) — a standalone MTProto messenger network. Case study: `@RubUpBot`.**

[English](#english) · [Русский](#русский)

---

<a id="english"></a>
## English

### What is this

This project is a **read-only analytics toolkit** that passively collects publicly
available telemetry from `@RubUpBot` — a **third-party casino bot created on
StaticGram** ([docs](https://docs.staticgram.top/tos)). StaticGram is a standalone
messenger network: per its Terms of Service, it is an isolated network with its own
servers, built on its **own implementation of the MTProto protocol** — it is not a
Telegram product, partner or affiliate in any way. Bots and Mini Apps on it are
user-built third-party services.

Personally for me, `@RubUp` is a casino bot made in StaticGram (a standalone
MTProto network), and this repo documents how to audit such a bot with nothing
but its own client-side API.

**Important framing:** this is *my own* analytics of *my own* play sessions. The
tool never places bets, never automates gameplay, and never sends anything to the
bot's API beyond read-only POST requests carrying my own session data. It is a
consumer-transparency experiment: when a casino exposes its own RTP telemetry,
you can simply watch it.

### Why "case study"

Most Telegram-like casino bots are closed boxes. RubUp (as of Oct 2026) exposes:

- self-reported RTP windows (`rtp / crtp / urtp / mrtp / prtp / drtp / lrtp`),
- a global feed of all players' finished games,
- a **provably fair** crash game (`crash = min(100000, max(110, floor(100 * rtp / u)))`,
  where `u = (int(sha256(seed)[:13], 16) + 1) / 2^52`) with verifiable commits,
- a per-game RTP knob on the owner's admin panel.

So the interesting research question becomes: *does the owner actually turn the
RTP knob, and when?* This tool collects the time series needed to answer that.

### Architecture

```
┌─────────────────────────────┐
│  StaticGram client (web)    │
│  RubUp Mini App             │
└──────────────┬──────────────┘
               │ HTTPS (POST + X-Init-Data)
               ▼
┌─────────────────────────────┐
│  harvester.py  (poller)     │   read-only, stdlib only
│  • /api/feed   → others'    │
│  • /api/me     → RTP + online│
│  • /api/fair   → audit+seeds│
│  • /api/fair_history → all │
└──────────────┬──────────────┘
               ▼
        SQLite (live.db)
               ▼
┌─────────────────────────────┐     ┌──────────────────────┐
│  analyze.py                 │     │  collector/          │
│  rolling RTP, hourly z-test │     │  optional browser    │
│  Markov "memory" test       │     │  hooks (inject.js)   │
│  win-streak analysis        │     │  + live dashboard    │
└─────────────────────────────┘     └──────────────────────┘
```

| Component | Purpose |
|---|---|
| `harvester.py` | 24/7 poller: game feed, RTP windows, fairness audit, full game history. SQLite storage. Runs on plain Python 3.8+, no dependencies |
| `render_app.py` | Thin HTTP wrapper for Render free tier: `/health` (for UptimeRobot) + `/stats` (live status JSON), harvester in a background thread |
| `collector/` *(optional)* | Browser-console hook (`inject.js`: fetch/XHR/WebSocket capture) and live dashboard — useful if you want in-game real-time view |
| `docs/` | Deployment notes (Render + UptimeRobot, VPS systemd unit) |

### What the data shows (early observations, Oct 2026)

- Bot's self-audit over the last 5000 games: wheel actual return **0.916**
  (declared 0.94), crash **0.941**, dice **0.949** — z-tests "within norm".
- Crash rounds are verifiable via seed → sha256 → formula; commits are stored
  client-side before betting.
- The wheel result is a server-side boolean — **not** provably fair; its odds are
  derived from the single server-side `RTP` variable (`chance = RTP / target`).

### Setup (short version)

1. Local: `python harvester.py` — keys live in `init_data.txt` / `base_url.txt` (not committed).
2. Serverless-ish: GitHub repo → Render free Web Service (`python render_app.py`,
   keys in `BASE_URL` / `INIT_DATA` env vars) → UptimeRobot pings `/health`.
3. Analysis: `python analyze.py` on the collected DB.

### Using it on other casino bots

The method generalizes to any bot on StaticGram (or a Telegram-like platform)
that exposes a client-side HTTP API:

1. Open the bot's Mini App in a browser, capture requests (DevTools → Network).
2. Identify: game endpoints, the session header (`X-Init-Data` here), and any
   self-reported RTP/fairness fields in responses.
3. Point `BASE_URL` + `INIT_DATA` at the new bot; adjust endpoints in `harvester.py`
   if they differ; check whether outcomes carry a seed/hash (provably fair) or not.
4. Collect read-only. Verify fairness where possible, compare declared vs actual
   return, and watch how self-reported metrics drift over time and load.

### Disclaimer

- StaticGram and `@RubUpBot` are third-party services; this project is not
  affiliated with them. Statics (XTR) are an internal, non-exchangeable currency.
- Nothing here is gambling advice. If you interact with casino bots, you do so at
  your own risk — check the platform's terms and the bot's own rules.
- If you run this, run it only with **your own** session keys, in read-only mode.

---

<a id="русский"></a>
## Русский

### Что это

**Аналитический набор «только чтение»**, который пассивно собирает открытую
телеметрию `@RubUpBot` — **стороннего бота-казино, созданного в StaticGram**
([правила](https://docs.staticgram.top/tos)). StaticGram — отдельный мессенджер:
по его Правилам использования это собственная изолированная сеть со своими
серверами, построенная на **собственной реализации протокола MTProto**; сервис
никак не связан с Telegram и не является его продуктом. Боты и Mini Apps в нём —
пользовательские, сторонние сервисы.

Лично для меня `@rubup` — это бот-казино, созданный в StaticGram (отдельной
MTProto-сети), и этот репозиторий — пример того, как можно проверять такие
боты, используя только их же клиентский API.

**Важно:** это личная аналитика моих собственных сессий. Инструмент не ставит
ставки, не автоматизирует игру и не отправляет в API ничего, кроме
read-only POST-запросов с моими собственными сессионными данными. Это
эксперимент по прозрачности: когда казино само публикует свою телеметрию RTP —
её можно просто наблюдать.

### Почему «пример проверки»

Обычно такие боты — закрытый ящик. RubUp (на октябрь 2026) раскрывает:

- самосообщаемые RTP-окна (`rtp / crtp / urtp / mrtp / prtp / drtp / lrtp`),
- глобальную ленту завершённых игр всех игроков,
- **provably fair** краш (`crash = min(100000, max(110, floor(100 * rtp / u)))`,
  где `u = (int(sha256(seed)[:13], 16) + 1) / 2^52`) с проверяемыми коммитами,
- «ручку» RTP на админ-панели владельца — отдельно для каждой игры.

Отсюда исследовательский вопрос: *крутит ли владелец эту ручку — и когда?*
Инструмент собирает временную серию, нужную для ответа.

### Архитектура

См. схему в английской части. Состав:

| Компонент | Назначение |
|---|---|
| `harvester.py` | фоновый поллер 24/7: лента игр, RTP-окна, аудит, полная история. SQLite. Чистый Python 3.8+, без зависимостей |
| `render_app.py` | тонкий HTTP-сервер для free-тарифа Render: `/health` (пинг UptimeRobot) + `/stats` (статус JSON), harvester в фоне |
| `collector/` *(опционально)* | хук для консоли браузера (`inject.js`: перехват fetch/XHR/WebSocket) и живой дашборд — если хочется видеть всё в реальном времени во время игры |
| `docs/` | заметки по деплою (Render + UptimeRobot, systemd-юнит для VPS) |

### Что показывают данные (первые наблюдения, октябрь 2026)

- Аудит самого бота за последние 5000 игр: фактический возврат колеса **0.916**
  (заявлено 0.94), краша **0.941**, костей **0.949** — z-тесты «в пределах нормы».
- Раунды краша проверяются: seed → sha256 → формула; коммиты хранятся клиентом
  до ставок.
- Результат колеса — булево с сервера, **не** provably fair; шансы выводятся из
  одной серверной переменной `RTP` (`шанс = RTP / цель`).

### Установка (кратко)

1. Локально: `python harvester.py` — ключи в `init_data.txt` / `base_url.txt` (не коммитятся).
2. «Серверный» вариант: репо → free Web Service на Render (`python render_app.py`,
   ключи в переменных `BASE_URL` / `INIT_DATA`) → UptimeRobot пингует `/health`.
3. Анализ: `python analyze.py` по собранной базе.

### Как адаптировать под другой казик

Метод работает для любого бота в StaticGram (или на Telegram-подобной платформе),
у которого клиент общается с сервером по HTTP:

1. Открой Mini App бота в браузере, посмотри запросы (DevTools → Network).
2. Определи: игровые эндпоинты, заголовок сессии (здесь `X-Init-Data`) и любые
   самосообщаемые RTP/честность поля в ответах.
3. Пропиши `BASE_URL` + `INIT_DATA` нового бота; поправь эндпоинты в `harvester.py`,
   если они отличаются; проверь, есть ли у результатов сид/хэш (provably fair) или нет.
4. Собирай только на чтение. Проверяй честность, где возможно, сравнивай заявленный
   и фактический возврат, следи, как «официальные» метрики плавают во времени и нагрузке.

### Отказ от ответственности

- StaticGram и `@RubUpBot` — сторонние сервисы; проект с ними не связан.
  Стастики (XTR) — внутренняя, необмениваемая валюта.
- Здесь нет gambling-советов. Взаимодействуя с казино-ботами, вы действуете на
  свой риск — проверяйте правила платформы и самого бота.
- Если запускаете это — запускайте только со **своими** сессионными ключами и
  в режиме «только чтение».

---

## License / Лицензия

MIT — see [LICENSE](LICENSE).
