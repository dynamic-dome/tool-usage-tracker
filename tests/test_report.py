import json
import subprocess
import sys
from pathlib import Path

REPORT = Path(__file__).resolve().parents[1] / "analysis" / "report.py"


def _write(tmp_path, rows):
    p = tmp_path / "ev.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def test_report_defaults_to_span_metrics(tmp_path):
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.000Z",
         "ts_local": "2026-06-02 12:00:00", "project": "P", "cwd": "c",
         "summary": "x", "agent": "codex"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.200Z",
         "ts_local": "2026-06-02 12:00:00", "ok": False, "error": "boom",
         "agent": "codex"},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z",
         "ts_local": "2026-06-02 12:01:00", "project": "P", "cwd": "c",
         "summary": "y", "agent": "codex"},
    ])
    r = subprocess.run([sys.executable, str(REPORT), "--data", str(p)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0
    assert "2 Spans / 3 Events" in r.stdout
    assert "Pairing" in r.stdout
    assert "Paired" in r.stdout
    assert "Unpaired" in r.stdout
    assert "Failures" in r.stdout
    assert "Bash" in r.stdout
    assert "boom" in r.stdout


def test_report_raw_events_flag_keeps_legacy_event_view(tmp_path):
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z",
         "ts_local": "2026-06-02 12:00:00", "project": "P", "agent": "codex"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.200Z",
         "ts_local": "2026-06-02 12:00:00", "ok": True, "agent": "codex"},
    ])
    r = subprocess.run([sys.executable, str(REPORT), "--data", str(p), "--raw-events"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0
    assert "2 Events" in r.stdout
    assert "Top-Tools" in r.stdout
    assert "Pairing" not in r.stdout
