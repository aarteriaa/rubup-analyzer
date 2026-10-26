# -*- coding: utf-8 -*-
"""
Обёртка для Render (free Web Service) + UptimeRobot:
  - поднимает HTTP-сервер: /health (для пинга UptimeRobot) и /stats (мини-статус)
  - harvester.py крутится в фоновом потоке

Start command:  python render_app.py
Переменные окружения (Render → Environment):
  BASE_URL   = https://...trycloudflare.com
  INIT_DATA  = строка initData (обновляется ~раз в сутки)
Порт Render задаёт через переменную PORT.
"""

import io
import json
import os
import sqlite3
import sys
import threading
import time
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import harvester  # noqa: E402


def stats_payload():
    try:
        with harvester.db() as conn:
            n_games = conn.execute("SELECT COUNT(*) FROM games_hist").fetchone()[0]
            n_feed = conn.execute("SELECT COUNT(*) FROM feed_items").fetchone()[0]
            n_win = conn.execute("SELECT COUNT(*) FROM rtp_windows").fetchone()[0]
            n_crash = conn.execute("SELECT COUNT(*) FROM crash_rounds").fetchone()[0]
            row = conn.execute("SELECT ts, rtp, online FROM rtp_windows ORDER BY ts DESC LIMIT 1").fetchone()
            log = conn.execute("SELECT ts, what, note FROM harvest_log ORDER BY ts DESC LIMIT 3").fetchall()
        last = None
        if row:
            last = {"ts": row[0], "rtp": row[1], "online": row[2],
                    "age_sec": int(time.time() - row[0])}
        return {"ok": True, "games_hist": n_games, "feed_items": n_feed,
                "rtp_windows": n_win, "crash_rounds": n_crash,
                "last_rtp_window": last,
                "log": [{"ts": l[0], "what": l[1], "note": l[2]} for l in log]}
    except Exception as e:
        return {"ok": False, "error": repr(e)}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body = b"ok"
            self.send_response(200)
        elif self.path == "/stats":
            body = json.dumps(stats_payload(), ensure_ascii=False).encode()
            self.send_response(200)
        else:
            body = b"RubUp harvester is running. /health /stats"
            self.send_response(200)
        self.send_header("Content-Type", "application/json" if self.path == "/stats" else "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    t = threading.Thread(target=harvester.main, daemon=True)
    t.start()
    print(f"HTTP on :{port} (/health, /stats), harvester запущен в фоне")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
