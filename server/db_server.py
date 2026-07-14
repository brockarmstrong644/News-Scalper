"""Central database receiver.

Runs on the machine behind your Cloudflare Tunnel. Agents POST finished
CSV exports here and everything is organized into one SQLite database:
server/newsscalper.db (exports table, one row per file, newest version
of a filename replaces the old one).

Endpoints (all require the X-Api-Key header except /health):
  GET  /health               -> {"ok": true, "exports": <count>}
  POST /ingest-file          -> body {"filename","symbol","dtype","start",
                                      "end","source","csv_text"}
  GET  /files                -> JSON list of stored exports
  GET  /download/<filename>  -> the stored CSV

Config: server/config.json  (copy config.example.json, set api_key)
Run:    python db_server.py   (or run_server.bat)
"""

import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
DB_PATH = ROOT / "newsscalper.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL UNIQUE,
    symbol TEXT,
    dtype TEXT,
    start_date TEXT,
    end_date TEXT,
    source TEXT,
    csv_text TEXT,
    received_at TEXT NOT NULL
);
"""


def load_config():
    if not CONFIG_PATH.exists():
        raise SystemExit(
            "server/config.json not found - copy config.example.json to "
            "config.json and set your api_key."
        )
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not config.get("api_key"):
        raise SystemExit("config.json must set a non-empty api_key.")
    return config


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    return conn


CONFIG = load_config()


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self):
        return self.headers.get("X-Api-Key", "") == CONFIG["api_key"]

    def do_GET(self):
        conn = connect()
        try:
            if self.path == "/health":
                count = conn.execute("SELECT COUNT(*) FROM exports").fetchone()[0]
                self._send(200, {"ok": True, "exports": count})
            elif self.path == "/files":
                if not self._authorized():
                    self._send(401, {"error": "bad api key"})
                    return
                rows = conn.execute(
                    "SELECT filename, symbol, dtype, start_date, end_date, "
                    "source, received_at FROM exports ORDER BY symbol, filename"
                ).fetchall()
                self._send(200, [
                    dict(zip(["filename", "symbol", "dtype", "start", "end",
                              "source", "received_at"], r))
                    for r in rows
                ])
            elif self.path.startswith("/download/"):
                if not self._authorized():
                    self._send(401, {"error": "bad api key"})
                    return
                filename = unquote(self.path[len("/download/"):])
                row = conn.execute(
                    "SELECT csv_text FROM exports WHERE filename = ?", (filename,)
                ).fetchone()
                if row is None:
                    self._send(404, {"error": "no such file"})
                else:
                    self._send(200, row[0].encode("utf-8"), "text/csv")
            else:
                self._send(404, {"error": "not found"})
        finally:
            conn.close()

    def do_POST(self):
        if self.path != "/ingest-file":
            self._send(404, {"error": "not found"})
            return
        if not self._authorized():
            self._send(401, {"error": "bad api key"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            filename = payload["filename"]
            csv_text = payload["csv_text"]
        except (json.JSONDecodeError, KeyError, ValueError):
            self._send(400, {"error": "bad payload"})
            return

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO exports (filename, symbol, dtype, start_date, "
                "end_date, source, csv_text, received_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(filename) DO UPDATE SET csv_text = excluded.csv_text, "
                "source = excluded.source, received_at = excluded.received_at",
                (
                    filename,
                    payload.get("symbol"),
                    payload.get("dtype"),
                    payload.get("start"),
                    payload.get("end"),
                    payload.get("source"),
                    csv_text,
                    now,
                ),
            )
            conn.commit()
            self._send(200, {"ok": True, "filename": filename})
        finally:
            conn.close()

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} {fmt % args}")


def main():
    port = int(CONFIG.get("port", 8899))
    connect().close()  # create the database up front
    print(f"NewsScalper database server on http://0.0.0.0:{port}")
    print(f"Database: {DB_PATH}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
