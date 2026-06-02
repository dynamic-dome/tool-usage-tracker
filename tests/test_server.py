import importlib.util
import json
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "analysis" / "server.py"
_spec = importlib.util.spec_from_file_location("server", SERVER)
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)


def _write(tmp_path, rows):
    p = tmp_path / "ev.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def test_spans_json_pairs_events(tmp_path):
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "P", "cwd": "c",
         "summary": "x", "agent": "claude-code"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.200Z", "ok": True, "error": "",
         "agent": "claude-code"},
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["count"] == 1
    assert payload["spans"][0]["duration_ms"] == 200
    assert "success_by_tool" in payload
    assert payload["success_by_tool"]["Bash"] == 1.0


def test_spans_json_respects_exclude_self(tmp_path):
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "tool-usage-tracker",
         "cwd": "c", "summary": "x", "agent": "claude-code"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.200Z", "ok": True, "agent": "claude-code"},
    ])
    payload = srv.spans_payload(str(p), {"exclude_self": "1"})
    assert payload["count"] == 0  # self-Projekt rausgefiltert vor Paarung


def test_spans_payload_lists_distinct_agents_and_projects(tmp_path):
    # Für die Filter-Dropdowns: sortierte, eindeutige Werte aller Events.
    # (projects nur git-Repos -> Fixtures als is_git_repo=true markiert)
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "zeta", "cwd": "c",
         "summary": "x", "agent": "codex", "is_git_repo": True},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.200Z", "ok": True, "agent": "codex"},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z", "project": "alpha", "cwd": "c",
         "summary": "y", "agent": "claude-code", "is_git_repo": True},
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["agents"] == ["claude-code", "codex"]   # sortiert, unique
    assert payload["projects"] == ["alpha", "zeta"]        # sortiert, unique


def test_spans_payload_filter_options_ignore_active_filter(tmp_path):
    # Die Auswahl-Listen müssen ALLE Werte zeigen, auch wenn gerade gefiltert
    # wird — sonst könnte man nie auf einen anderen Wert umschalten.
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "zeta", "cwd": "c",
         "summary": "x", "agent": "codex", "is_git_repo": True},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z", "project": "alpha", "cwd": "c",
         "summary": "y", "agent": "claude-code", "is_git_repo": True},
    ])
    payload = srv.spans_payload(str(p), {"agent": "codex"})
    # gefilterte spans betreffen nur codex/zeta, aber die Optionen bleiben voll
    assert payload["agents"] == ["claude-code", "codex"]
    assert payload["projects"] == ["alpha", "zeta"]


def test_spans_payload_filter_options_skip_empty_values(tmp_path):
    # Events ohne agent/project dürfen keine leeren Optionen erzeugen.
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "cwd": "c", "summary": "x"},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z", "project": "alpha", "cwd": "c",
         "summary": "y", "agent": "claude-code", "is_git_repo": True},
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["agents"] == ["claude-code"]
    assert payload["projects"] == ["alpha"]


def test_projects_dropdown_only_git_repos(tmp_path):
    # projects-Dropdown listet NUR Projekte, die mind. 1 Event mit
    # is_git_repo=true haben — cwd-Ordner-Rauschen (.agent-memory, plans, …)
    # fliegt raus.
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "real-repo", "cwd": "c",
         "summary": "x", "agent": "claude-code", "is_git_repo": True},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z", "project": "plans", "cwd": "c",
         "summary": "y", "agent": "claude-code", "is_git_repo": False},
        {"phase": "pre", "session_id": "s3", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:02:00.000Z", "project": "noise", "cwd": "c",
         "summary": "z", "agent": "claude-code"},  # gar kein is_git_repo-Feld
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["projects"] == ["real-repo"]


def test_projects_dropdown_one_git_event_qualifies(tmp_path):
    # Ein Projekt mit gemischten Events (mind. 1 git=true) zählt als git-Repo —
    # robust gegen ein einzelnes Ausreißer-nongit-Event (real: 'wiki' 13/1).
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "mixed", "cwd": "c",
         "summary": "x", "agent": "claude-code", "is_git_repo": False},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z", "project": "mixed", "cwd": "c",
         "summary": "y", "agent": "claude-code", "is_git_repo": True},
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["projects"] == ["mixed"]


def test_parse_query_flags():
    params = srv.parse_query("agent=codex&exclude_self=1&since=2026-06-01")
    assert params["agent"] == "codex"
    assert params["exclude_self"] == "1"
    assert params["since"] == "2026-06-01"


def test_spans_payload_error_does_not_crash_handler(tmp_path, monkeypatch):
    # spans_payload raises -> do_GET should send a 500 JSON, not propagate
    import io

    def boom(*a, **k):
        raise ValueError("corrupt data")
    monkeypatch.setattr(srv, "spans_payload", boom)

    Handler = srv.make_handler("dummy-path")
    # Minimal fake request plumbing to drive do_GET without a real socket
    captured = {}

    class FakeHandler(Handler):
        def __init__(self):
            self.path = "/api/spans"
            self.wfile = io.BytesIO()
        def send_response(self, code): captured["code"] = code
        def send_header(self, *a, **k): pass
        def end_headers(self): pass

    h = FakeHandler()
    h.do_GET()
    assert captured["code"] == 500
    body = h.wfile.getvalue().decode("utf-8")
    assert "error" in body
