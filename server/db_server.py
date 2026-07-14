"""Central database receiver.

Runs on the machine behind your Cloudflare Tunnel. Agents POST finished
report rows (plus the raw Finnhub/FRED payloads) here and everything is
organized into one SQLite database: server/newsscalper.db

Endpoints (all require the X-Api-Key header except /health):
  GET  /health       -> {"ok": true, "reports": <count>}
  POST /ingest       -> body {"row": {...}, "raw": {...}} ; inserts one report
  GET  /export.csv   -> the entire reports table as CSV

Config: server/config.json  (copy config.example.json, set api_key)
Run:    python db_server.py   (or run_server.bat)
"""

import csv
import io
import json
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
DB_PATH = ROOT / "newsscalper.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    earnings_date TEXT,
    eps_actual REAL,
    eps_estimate REAL,
    surprise_pct REAL,
    earnings_signal INTEGER,
    market_signal INTEGER,
    fed_signal INTEGER,
    econ_signal INTEGER,
    composite_score REAL,
    notes TEXT,
    generated_at TEXT,
    source TEXT,
    received_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_reports_unique
    ON reports (symbol, generated_at);
CREATE TABLE IF NOT EXISTS raw_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id INTEGER REFERENCES reports(id),
    payload TEXT,
    received_at TEXT NOT NULL
);
"""

REPORT_COLUMNS = [
    "symbol", "earnings_date", "eps_actual", "eps_estimate", "surprise_pct",
    "earnings_signal", "market_signal", "fed_signal", "econ_signal",
    "composite_score", "notes", "generated_at", "source",
]


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
                count = conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
                self._send(200, {"ok": True, "reports": count})
            elif self.path == "/export.csv":
                if not self._authorized():
                    self._send(401, {"error": "bad api key"})
                    return
                rows = conn.execute(
                    f"SELECT {', '.join(REPORT_COLUMNS)}, received_at "
                    "FROM reports ORDER BY id"
                ).fetchall()
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(REPORT_COLUMNS + ["received_at"])
                writer.writerows(rows)
                self._send(200, buf.getvalue().encode("utf-8"), "text/csv")
            else:
                self._send(404, {"error": "not found"})
        finally:
            conn.close()

    def do_POST(self):
        if self.path != "/ingest":
            self._send(404, {"error": "not found"})
            return
        if not self._authorized():
            self._send(401, {"error": "bad api key"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            row = payload["row"]
        except (json.JSONDecodeError, KeyError, ValueError):
            self._send(400, {"error": "bad payload"})
            return

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn = connect()
        try:
            cur = conn.execute(
                f"INSERT OR IGNORE INTO reports ({', '.join(REPORT_COLUMNS)}, received_at) "
                f"VALUES ({', '.join('?' * len(REPORT_COLUMNS))}, ?)",
                [row.get(c) for c in REPORT_COLUMNS] + [now],
            )
            inserted = cur.rowcount > 0
            if inserted and payload.get("raw") is not None:
                conn.execute(
                    "INSERT INTO raw_data (report_id, payload, received_at) VALUES (?, ?, ?)",
                    (cur.lastrowid, json.dumps(payload["raw"]), now),
                )
            conn.commit()
            self._send(200, {"ok": True, "inserted": inserted})
        finally:
            conn.close()

    def log_message(self, fmt, *args):  # quieter console
        print(f"{self.address_string()} {fmt % args}")


def main():
    port = int(CONFIG.get("port", 8899))
    connect().close()  # create the database up front
    print(f"NewsScalper database server on http://0.0.0.0:{port}")
    print(f"Database: {DB_PATH}")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
