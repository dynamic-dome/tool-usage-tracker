"""Live-Dashboard-Server (Stdlib http.server, an 127.0.0.1 gebunden — Regel 16).
Enthält KEINE Aggregationslogik — nur HTTP + Delegation an _load.py.
Usage: python analysis/server.py [--data PFAD] [--port N]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from _load import (load_events, pair_events, pairing_summary, success_rate_by,
                   duration_stats_by, path_activity, classification_breakdown,
                   compute_turn_gap_threshold, assign_turns, cost_breakdown,
                   comparison, enrich_spans_with_tokens, drift_breakdown)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "events.jsonl"
DEFAULT_TOKENS = ROOT / "data" / "tokens_by_request.json"


def _tokens_path():
    """LAZY: Pfad zum ccusage-Token-Aggregat. Env TOOL_TRACKER_TOKENS ueber-
    schreibt (Test-Isolation); Default data/tokens_by_request.json."""
    override = os.environ.get("TOOL_TRACKER_TOKENS")
    return Path(override) if override else DEFAULT_TOKENS


def _load_tokens_by_request():
    """tokens_by_request.json laden, wenn vorhanden. Graceful: fehlende/kaputte
    Datei -> leeres Dict (Token-Anreicherung ist optional, nie blockierend)."""
    path = _tokens_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}
CHARTJS = ROOT / "vendor" / "chart.umd.min.js"
DASHBOARD_TEMPLATE = Path(__file__).resolve().with_name("dashboard_template.html")


def parse_query(query_string):
    raw = parse_qs(query_string)
    return {k: v[0] for k, v in raw.items()}


def _distinct_sorted(events, key):
    """Sortierte, eindeutige nicht-leere Werte eines Feldes — speist die
    Filter-Dropdowns im Dashboard."""
    return sorted({v for ev in events if (v := ev.get(key))})


def _git_projects_sorted(events):
    """Sortierte, eindeutige Projekte, die mindestens EIN Event mit
    is_git_repo=true haben — filtert cwd-Ordner-Rauschen (.agent-memory, plans,
    queries …) aus dem project-Dropdown. Ein einzelnes git-Event qualifiziert
    (robust gegen vereinzelte nongit-Ausreißer, z.B. 'wiki' 13/1)."""
    return sorted({v for ev in events
                   if (v := ev.get("project")) and ev.get("is_git_repo")})


def spans_payload(data_path, params):
    evs = load_events(data_path,
                      agent=params.get("agent"),
                      project=params.get("project"),
                      since=params.get("since"),
                      exclude_self=params.get("exclude_self") in ("1", "true", "True"))
    spans = pair_events(evs)
    # Token-/Kosten-Anreicherung aus dem ccusage-Ingest (optional, graceful):
    # joint Turn-Token ueber tool_use_id, sobald data/tokens_by_request.json da ist.
    by_req = _load_tokens_by_request()
    if by_req:
        spans = enrich_spans_with_tokens(spans, by_req)
    turn_gap_ms = compute_turn_gap_threshold(spans)
    assign_turns(spans, turn_gap_ms)
    # Auswahl-Optionen aus ALLEN Events (ungefiltert) — sonst könnte man von
    # einem aktiven Filter nie auf einen anderen Wert umschalten.
    all_evs = load_events(data_path)
    return {
        "count": len([s for s in spans if s.get("paired")]),
        "total_events": len(evs),
        "spans": spans,
        "turn_gap_ms": turn_gap_ms,
        "agents": _distinct_sorted(all_evs, "agent"),
        "projects": _git_projects_sorted(all_evs),
        "success_by_tool": success_rate_by(spans, "tool_name"),
        "success_by_project": success_rate_by(spans, "project"),
        "duration_by_tool": duration_stats_by(spans, "tool_name"),
        "path_activity": path_activity(spans),
        "pairing": pairing_summary(spans),
        "classification": classification_breakdown(spans),
        "cost": cost_breakdown(spans),
        "comparison": {
            "by_agent": comparison(spans, key="agent"),
            "by_session": comparison(spans, key="session_id"),
        },
        "drift": drift_breakdown(spans),
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
                try:
                    self._send(200, json.dumps(spans_payload(data_path, params)))
                except Exception as e:
                    self._send(500, json.dumps({"error": str(e)}))
            elif parsed.path == "/":
                self._send(200, index_html(), "text/html")
            elif parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            else:
                self._send(404, json.dumps({"error": "not found"}))
    return Handler


def index_html():
    """Vollständiges Dashboard-Dokument. Chart.js wird zur Aufruf-Zeit aus
    vendor/ inline gebettet (kein CDN, Regel). Das HTML/CSS/JS-Template liegt
    separat, damit die Server-Logik reviewbar bleibt."""
    chartjs = CHARTJS.read_text(encoding="utf-8") if CHARTJS.exists() else ""
    template = DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("/*CHARTJS*/", chartjs)


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
