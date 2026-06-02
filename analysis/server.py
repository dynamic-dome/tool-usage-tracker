"""Live-Dashboard-Server (Stdlib http.server, an 127.0.0.1 gebunden — Regel 16).
Enthält KEINE Aggregationslogik — nur HTTP + Delegation an _load.py.
Usage: python analysis/server.py [--data PFAD] [--port N]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from _load import (load_events, pair_events, success_rate_by,
                   duration_stats_by, path_activity)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "events.jsonl"


def parse_query(query_string):
    raw = parse_qs(query_string)
    return {k: v[0] for k, v in raw.items()}


def spans_payload(data_path, params):
    evs = load_events(data_path,
                      agent=params.get("agent"),
                      project=params.get("project"),
                      since=params.get("since"),
                      exclude_self=params.get("exclude_self") in ("1", "true", "True"))
    spans = pair_events(evs)
    return {
        "count": len([s for s in spans if s.get("paired")]),
        "total_events": len(evs),
        "spans": spans,
        "success_by_tool": success_rate_by(spans, "tool_name"),
        "success_by_project": success_rate_by(spans, "project"),
        "duration_by_tool": duration_stats_by(spans, "tool_name"),
        "path_activity": path_activity(spans),
    }


def make_handler(data_path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass  # keine Konsolen-Spam

        def _send(self, code, body, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/spans":
                params = parse_query(parsed.query)
                self._send(200, json.dumps(spans_payload(data_path, params)))
            elif parsed.path == "/":
                self._send(200, _INDEX_HTML, "text/html")
            else:
                self._send(404, json.dumps({"error": "not found"}))
    return Handler


_INDEX_HTML = "<!-- platzhalter, in Task 6 ersetzt -->"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args()
    httpd = HTTPServer(("127.0.0.1", a.port), make_handler(a.data))
    print(f"Dashboard-Server: http://127.0.0.1:{a.port}  (Ctrl-C zum Stoppen)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


if __name__ == "__main__":
    main()
