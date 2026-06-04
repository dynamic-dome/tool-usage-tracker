import importlib.util
import json
from pathlib import Path

LOADER = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
_spec = importlib.util.spec_from_file_location("_load", LOADER)
load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(load)


def _write(tmp_path, rows):
    p = tmp_path / "ev.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def test_load_skips_broken_lines(tmp_path):
    p = tmp_path / "ev.jsonl"
    p.write_text('{"tool_name":"Bash","agent":"claude-code"}\nNOT JSON\n', encoding="utf-8")
    evs = load.load_events(p)
    assert len(evs) == 1


def test_filter_by_agent_and_project(tmp_path):
    p = _write(tmp_path, [
        {"agent": "claude-code", "project": "A", "ts_utc": "2026-06-01T10:00:00.000Z"},
        {"agent": "codex", "project": "A", "ts_utc": "2026-06-01T10:00:00.000Z"},
        {"agent": "claude-code", "project": "B", "ts_utc": "2026-06-01T10:00:00.000Z"},
    ])
    assert len(load.load_events(p, agent="claude-code")) == 2
    assert len(load.load_events(p, project="A")) == 2


def test_filter_since(tmp_path):
    p = _write(tmp_path, [
        {"ts_utc": "2026-05-01T10:00:00.000Z", "agent": "x", "project": "P"},
        {"ts_utc": "2026-06-02T10:00:00.000Z", "agent": "x", "project": "P"},
    ])
    assert len(load.load_events(p, since="2026-06-01")) == 1


def test_missing_file_returns_empty(tmp_path):
    assert load.load_events(tmp_path / "nope.jsonl") == []


def test_exclude_self_drops_own_project(tmp_path):
    p = _write(tmp_path, [
        {"agent": "x", "project": "tool-usage-tracker", "summary": "edit hook",
         "ts_utc": "2026-06-02T10:00:00.000Z"},
        {"agent": "x", "project": "RealWork", "summary": "do stuff",
         "ts_utc": "2026-06-02T10:00:00.000Z"},
    ])
    evs = load.load_events(p, exclude_self=True)
    assert len(evs) == 1
    assert evs[0]["project"] == "RealWork"


def test_exclude_self_drops_analysis_invocations(tmp_path):
    # Auswertungs-Aufrufe aus FREMDEM Projekt: per summary erkannt
    p = _write(tmp_path, [
        {"agent": "x", "project": "RealWork",
         "summary": "python analysis/report.py --since 2026-06-01",
         "ts_utc": "2026-06-02T10:00:00.000Z"},
        {"agent": "x", "project": "RealWork",
         "summary": "python analysis/dashboard.py",
         "ts_utc": "2026-06-02T10:00:00.000Z"},
        {"agent": "x", "project": "RealWork", "summary": "ls -la",
         "ts_utc": "2026-06-02T10:00:00.000Z"},
    ])
    evs = load.load_events(p, exclude_self=True)
    assert len(evs) == 1
    assert evs[0]["summary"] == "ls -la"


def test_exclude_self_off_by_default(tmp_path):
    p = _write(tmp_path, [
        {"agent": "x", "project": "tool-usage-tracker", "summary": "x",
         "ts_utc": "2026-06-02T10:00:00.000Z"},
    ])
    assert len(load.load_events(p)) == 1  # Rohdaten unangetastet ohne Flag


def test_pair_events_propagates_git_branch_and_file_ext():
    events = [
        {"phase": "pre", "session_id": "s", "tool_use_id": "t1", "tool_name": "Edit",
         "ts_utc": "2026-06-04T10:00:00.000Z", "cwd": "x", "project": "p",
         "git_branch": "main", "file_ext": "py"},
        {"phase": "post", "session_id": "s", "tool_use_id": "t1", "tool_name": "Edit",
         "ts_utc": "2026-06-04T10:00:00.100Z", "ok": True},
    ]
    spans = load.pair_events(events)
    assert spans[0]["git_branch"] == "main"
    assert spans[0]["file_ext"] == "py"


def test_unpaired_pre_keeps_git_branch_and_file_ext():
    events = [
        {"phase": "pre", "session_id": "s", "tool_use_id": "t9", "tool_name": "Read",
         "ts_utc": "2026-06-04T10:00:00.000Z", "cwd": "x", "project": "p",
         "git_branch": "feature/x", "file_ext": "md"},
    ]
    spans = load.pair_events(events)
    s = [x for x in spans if not x.get("paired")][0]
    assert s["git_branch"] == "feature/x"
    assert s["file_ext"] == "md"
