#!/usr/bin/env python3
"""Serves the dashboard and auto-refreshes data.js from yfinance when stale.

  python3 serve.py            # http://localhost:4380

Endpoints:
  /api/status   {refreshing, progress, generated, ageHours}
  /api/refresh  (POST) start a refresh now
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
PORT = 4380
MAX_AGE_HOURS = 24
RETRY_MINUTES = 60  # min gap between auto-refresh attempts if one fails
LOG = os.path.join(ROOT, "fetch.log")

_proc = None
_last_attempt = 0.0
_lock = threading.Lock()


def data_generated():
    try:
        with open(os.path.join(ROOT, "data.js")) as f:
            m = re.search(r'"generated":\s*"([^"]+)"', f.read(300))
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M")
    except Exception:
        return None


def age_hours():
    gen = data_generated()
    return None if gen is None else (datetime.now() - gen).total_seconds() / 3600


def external_fetch_running():
    """A fetch_data.py started outside this server (CLI, another session)."""
    try:
        out = subprocess.run(["pgrep", "-f", "fetch_data.py"],
                             capture_output=True, text=True)
        pids = {int(p) for p in out.stdout.split()}
        if _proc is not None:
            pids.discard(_proc.pid)
        return bool(pids)
    except Exception:
        return False


def is_refreshing():
    return (_proc is not None and _proc.poll() is None) or external_fetch_running()


def start_refresh():
    global _proc, _last_attempt
    with _lock:
        if is_refreshing():
            return False
        _last_attempt = time.time()
        logf = open(LOG, "w")
        _proc = subprocess.Popen(
            [sys.executable, "-u", os.path.join(ROOT, "fetch_data.py")],
            cwd=ROOT, stdout=logf, stderr=subprocess.STDOUT)
        print(f"refresh started (pid {_proc.pid})")
        return True


def maybe_auto_refresh():
    age = age_hours()
    stale = age is None or age > MAX_AGE_HOURS
    if stale and not is_refreshing() and time.time() - _last_attempt > RETRY_MINUTES * 60:
        start_refresh()


def progress():
    if not is_refreshing():
        return None
    try:
        with open(LOG) as f:
            lines = f.read().strip().splitlines()
        for line in reversed(lines):
            m = re.match(r"\[(\d+/\d+)\]", line)
            if m:
                return m.group(1)
    except Exception:
        pass
    return None


class Handler(SimpleHTTPRequestHandler):
    def send_json(self, obj):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/status":
            maybe_auto_refresh()
            gen = data_generated()
            return self.send_json({
                "refreshing": is_refreshing(),
                "progress": progress(),
                "generated": gen.strftime("%Y-%m-%d %H:%M") if gen else None,
                "ageHours": round(age_hours(), 1) if age_hours() is not None else None,
            })
        if self.path in ("/", "/index.html"):
            maybe_auto_refresh()
        super().do_GET()

    def do_POST(self):
        if self.path == "/api/refresh":
            return self.send_json({"started": start_refresh()})
        self.send_error(404)

    def log_message(self, fmt, *args):
        if "/api/status" not in (args[0] if args else ""):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", PORT), partial(Handler, directory=ROOT))
    print(f"Stock screener at http://localhost:{PORT} "
          f"(auto-refresh when data older than {MAX_AGE_HOURS}h)")
    server.serve_forever()
