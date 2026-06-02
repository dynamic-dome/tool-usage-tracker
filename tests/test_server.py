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


def test_parse_query_flags():
    params = srv.parse_query("agent=codex&exclude_self=1&since=2026-06-01")
    assert params["agent"] == "codex"
    assert params["exclude_self"] == "1"
    assert params["since"] == "2026-06-01"
