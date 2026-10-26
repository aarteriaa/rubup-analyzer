# -*- coding: utf-8 -*-
"""
Автономный сборщик данных RubUp. Работает в фоне БЕЗ браузера:
  - /api/feed          → чужие игры в реальном времени (только новые по id)
  - /api/me            → RTP-окна бота + онлайн (каждые 30 с)
  - /api/fair          → аудит бота + раунды краша с seed'ами (каждые 60 с)
  - /api/fair_history  → полная история игр всех игроков (бэкфилл при старте)
Только чтение. Ничего не ставит, не крутит, не меняет.

Файлы:
  init_data.txt — твой X-Init-Data (обновляй, если сервер скажет, что устарел)
  base_url.txt  — адрес туннеля (обновляй, если бот перезапустили)
База: live.db (SQLite)

Запуск: python harvester.py   (Ctrl+C — стоп)
"""

import io
import json
import os
import sqlite3
import sys
import time
import pathlib
import urllib.request
import urllib.error

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = pathlib.Path(__file__).resolve().parent
DB = HERE / "live.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS games_hist (
    id INTEGER PRIMARY KEY, ts INTEGER, game TEXT, bet REAL, prize REAL, x REAL, name TEXT
);
CREATE TABLE IF NOT EXISTS feed_items (
    id INTEGER PRIMARY KEY, recv_ts INTEGER, game TEXT, bet REAL, prize REAL, mult REAL, name TEXT, me INTEGER
);
CREATE TABLE IF NOT EXISTS rtp_windows (
    ts INTEGER PRIMARY KEY, rtp REAL, crtp REAL, urtp REAL, mrtp REAL, prtp REAL, drtp REAL, lrtp REAL,
    online INTEGER, balance REAL
);
CREATE TABLE IF NOT EXISTS fair_snapshots (ts INTEGER PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS crash_rounds (rid INTEGER PRIMARY KEY, ts INTEGER, data TEXT);
CREATE TABLE IF NOT EXISTS harvest_log (ts INTEGER, what TEXT, note TEXT);
"""

def db():
    conn = sqlite3.connect(DB, timeout=30)
    conn.executescript(SCHEMA)
    return conn


def read_conf():
    # на сервере (Render и т.п.) ключи берём из переменных окружения, локально — из файлов
    base = os.environ.get("BASE_URL") or (HERE / "base_url.txt").read_text(encoding="utf-8").strip()
    init = os.environ.get("INIT_DATA") or (HERE / "init_data.txt").read_text(encoding="utf-8").strip()
    return base.strip().rstrip("/"), init.strip()


def call(base, init, path, body=None, timeout=15):
    data = json.dumps(body or {}).encode()
    req = urllib.request.Request(
        base + path, data=data, method="POST",
        headers={"Content-Type": "application/json", "X-Init-Data": init},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def log(conn, what, note):
    conn.execute("INSERT INTO harvest_log (ts, what, note) VALUES (?,?,?)",
                 (int(time.time()), what, note))
    conn.commit()
    print(f"[{time.strftime('%H:%M:%S')}] {what}: {note}")


def backfill_history(conn, base, init, max_pages=1200):
    """Полная выкачка fair_history от свежих к старым."""
    before, pages, saved = 0, 0, 0
    while pages < max_pages:
        try:
            d = call(base, init, "/api/fair_history", {"before": before})
        except Exception as e:
            log(conn, "backfill", f"ошибка: {e!r}")
            time.sleep(5)
            continue
        items = d.get("items", [])
        if not items:
            break
        conn.executemany(
            "INSERT OR IGNORE INTO games_hist (id, ts, game, bet, prize, x, name)"
            " VALUES (?,?,?,?,?,?,?)",
            [(i["id"], i.get("ts"), i.get("game"), i.get("bet", 0),
              i.get("prize", 0), i.get("x"), i.get("name", "")) for i in items],
        )
        conn.commit()
        saved += len(items)
        pages += 1
        oldest = items[-1]["id"]
        if not d.get("more") or oldest == before:
            break
        before = oldest
        time.sleep(0.12)
    log(conn, "backfill", f"+{saved} игр всего (страниц: {pages})")


def poll_feed(conn, base, init, state):
    d = call(base, init, "/api/feed", {"after": state.get("feed_after", 0)})
    items = d.get("items", [])
    new = 0
    for it in items:
        cur = conn.execute("INSERT OR IGNORE INTO feed_items (id, recv_ts, game, bet, prize, mult, name, me)"
                           " VALUES (?,?,?,?,?,?,?,?)",
                           (it["id"], int(time.time()), it.get("game"), it.get("bet", 0),
                            it.get("prize", 0), it.get("mult"), it.get("name", ""),
                            1 if it.get("me") else 0))
        if cur.rowcount:
            new += 1
        state["feed_after"] = max(state.get("feed_after", 0), it["id"])
    conn.commit()
    return new, len(items)


def poll_me(conn, base, init):
    d = call(base, init, "/api/me")
    conn.execute("INSERT OR REPLACE INTO rtp_windows (ts, rtp, crtp, urtp, mrtp, prtp, drtp, lrtp, online, balance)"
                 " VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (int(time.time()), d.get("rtp"), d.get("crtp"), d.get("urtp"),
                  d.get("mrtp"), d.get("prtp"), d.get("drtp"), d.get("lrtp"),
                  d.get("online"), d.get("balance")))
    conn.commit()


def poll_fair(conn, base, init):
    d = call(base, init, "/api/fair")
    now = int(time.time())
    conn.execute("INSERT OR REPLACE INTO fair_snapshots (ts, data) VALUES (?,?)",
                 (now, json.dumps(d, ensure_ascii=False)))
    for r in d.get("rounds", []):
        if isinstance(r, dict) and "rid" in r:
            conn.execute("INSERT OR REPLACE INTO crash_rounds (rid, ts, data) VALUES (?,?,?)",
                         (r["rid"], r.get("ts"), json.dumps(r, ensure_ascii=False)))
    conn.commit()


def main():
    base, init = read_conf()
    print("API:", base)
    conn = db()
    state = {}

    # где остановился в прошлый раз
    row = conn.execute("SELECT MAX(id) FROM feed_items").fetchone()
    state["feed_after"] = row[0] or 0
    log(conn, "start", f"feed_after={state['feed_after']}")

    backfill_history(conn, base, init)

    t_me, t_fair, t_refill = 0, 0, time.time() + 1800
    while True:
        try:
            base, init = read_conf()  # мог обновиться
        except Exception:
            pass
        now = time.time()
        try:
            if now - t_me >= 30:
                poll_me(conn, base, init)
                t_me = now
            new, total = poll_feed(conn, base, init, state)
            if new:
                print(f"[{time.strftime('%H:%M:%S')}] лента: +{new} (онлайн по /me)")
            if now - t_fair >= 60:
                poll_fair(conn, base, init)
                t_fair = now
            if now > t_refill:  # раз в полчаса добираем новую историю
                backfill_history(conn, base, init, max_pages=200)
                t_refill = time.time() + 1800
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                log(conn, "auth", "init_data отклонён — обнови init_data.txt (location.href в консоли RubUp)")
            elif e.code == 404:
                log(conn, "api", "404 — туннель умер? обнови base_url.txt")
            else:
                log(conn, "http", repr(e))
            time.sleep(10)
        except Exception as e:
            log(conn, "err", repr(e))
            time.sleep(10)
        time.sleep(10)


if __name__ == "__main__":
    main()
