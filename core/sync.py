"""Syncs finished reports to the central database server.

After each CSV row is written locally, the same row (plus the raw skill
outputs) is POSTed to the receiver behind your Cloudflare Tunnel. If the
server is unreachable the payload is queued in data/outbox/ and retried
automatically the next time the agent starts.

Settings (config/settings.json):
  sync_enabled  - true/false
  sync_url      - e.g. "https://your-tunnel.example.com/ingest"
  sync_api_key  - must match api_key in server/config.json
"""

import json
import socket
import uuid
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTBOX_DIR = PROJECT_ROOT / "data" / "outbox"


def _configured(settings):
    return bool(
        settings.get("sync_enabled")
        and settings.get("sync_url")
        and settings.get("sync_api_key")
    )


def _post(payload, settings):
    resp = requests.post(
        settings["sync_url"],
        json=payload,
        headers={"X-Api-Key": settings["sync_api_key"]},
        timeout=15,
    )
    resp.raise_for_status()


def _queue(payload):
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTBOX_DIR / f"{uuid.uuid4().hex}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")


def send_report(row, raw_context, settings):
    """Send one report. Returns 'synced', 'queued', or 'disabled'."""
    if not _configured(settings):
        return "disabled"
    payload = {"row": {**row, "source": socket.gethostname()}, "raw": raw_context}
    try:
        _post(payload, settings)
        return "synced"
    except Exception:
        _queue(payload)
        return "queued"


def flush_outbox(settings):
    """Retry queued payloads. Returns (sent, remaining)."""
    if not _configured(settings) or not OUTBOX_DIR.exists():
        return 0, 0
    files = sorted(OUTBOX_DIR.glob("*.json"))
    sent = 0
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            _post(payload, settings)
            path.unlink()
            sent += 1
        except Exception:
            break  # server still unreachable - keep the rest for next time
    return sent, len(files) - sent
