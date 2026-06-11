"""Tests fuer analysis/quality_signal.py — Tool-Fehlerrate pro Session als
Quality-Signal fuer externe Konsumenten (agentic-os quality-gate, C5-Kopplung).

Fixtures spiegeln das ECHTE Event-Schema (schema_v 2, phase pre/post,
ok/error nur im Post-Event) — kein Wunsch-Spec-Beispiel (Anti-Pattern P5/P012:
auch der ok=None-Pfad unpaarer Spans wird explizit getestet)."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "analysis"))

from quality_signal import quality_signal  # noqa: E402

QS = Path(__file__).resolve().parents[1] / "analysis" / "quality_signal.py"


def _pre(session, tool, tuid, ts, project="proj-a", mutating=False):
    return {
        "ts_utc": ts, "ts_local": ts.replace("T", " ")[:19], "agent": "claude-code",
        "schema_v": 2, "phase": "pre", "tool_name": tool, "session_id": session,
        "tool_use_id": tuid, "cwd": "X:/somewhere", "project": project,
        "mutating": mutating, "risk": "low", "operation": "", "summary": "s",
        "app": "", "intent": "", "git_branch": "", "is_git_repo": False,
        "hook_event": "PreToolUse",
    }


def _post(session, tool, tuid, ts, ok=True, error=""):
    return {
        "ts_utc": ts, "ts_local": ts.replace("T", " ")[:19], "agent": "claude-code",
        "schema_v": 2, "phase": "post", "tool_name": tool, "session_id": session,
        "tool_use_id": tuid, "ok": ok, "error": error,
    }


def _events():
    """Session A: 3 gepaarte Calls (1 Failure, mutating), 1 unpaired pre (ok=None).
    Session B: 2 gepaarte Calls, beide ok."""
    return [
        _pre("sess-a", "Bash", "t1", "2026-06-11T10:00:00.000Z", mutating=True),
        _post("sess-a", "Bash", "t1", "2026-06-11T10:00:01.000Z", ok=False, error="exit 1"),
        _pre("sess-a", "Read", "t2", "2026-06-11T10:01:00.000Z"),
        _post("sess-a", "Read", "t2", "2026-06-11T10:01:01.000Z", ok=True),
        _pre("sess-a", "Bash", "t3", "2026-06-11T10:02:00.000Z"),
        _post("sess-a", "Bash", "t3", "2026-06-11T10:02:01.000Z", ok=True),
        # unpaired pre -> ok=None, darf NICHT in die Rate einfliessen
        _pre("sess-a", "Edit", "t4", "2026-06-11T10:03:00.000Z"),
        _pre("sess-b", "Read", "t5", "2026-06-11T11:00:00.000Z", project="proj-b"),
        _post("sess-b", "Read", "t5", "2026-06-11T11:00:01.000Z", ok=True),
        _pre("sess-b", "Grep", "t6", "2026-06-11T11:01:00.000Z", project="proj-b"),
        _post("sess-b", "Grep", "t6", "2026-06-11T11:01:01.000Z", ok=True),
    ]


def _signal(events=None, **kw):
    from _load import pair_events
    return quality_signal(pair_events(events if events is not None else _events()), **kw)


def test_contract_top_level_keys():
    sig = _signal()
    assert sig["schema_v"] == 1
    assert "generated_at" in sig
    assert set(sig) >= {"schema_v", "generated_at", "overall", "sessions"}


def test_per_session_failure_rate():
    sig = _signal()
    by_id = {s["session_id"]: s for s in sig["sessions"]}
    a = by_id["sess-a"]
    # nur Spans mit bekanntem ok zaehlen (t4 unpaired -> raus)
    assert a["tool_calls"] == 3
    assert a["failures"] == 1
    assert a["success_rate"] == 2 / 3
    assert a["mutating_failures"] == 1
    assert a["project"] == "proj-a"
    b = by_id["sess-b"]
    assert (b["tool_calls"], b["failures"], b["success_rate"]) == (2, 0, 1.0)
    assert b["mutating_failures"] == 0


def test_top_failing_tools_sorted():
    sig = _signal()
    a = {s["session_id"]: s for s in sig["sessions"]}["sess-a"]
    assert a["top_failing_tools"] == [{"tool": "Bash", "failures": 1}]
    b = {s["session_id"]: s for s in sig["sessions"]}["sess-b"]
    assert b["top_failing_tools"] == []


def test_overall_aggregation():
    sig = _signal()
    o = sig["overall"]
    assert o["sessions"] == 2
    assert o["tool_calls"] == 5
    assert o["failures"] == 1
    assert o["success_rate"] == 4 / 5
    assert o["mutating_failures"] == 1


def test_sessions_sorted_newest_first():
    sig = _signal()
    ids = [s["session_id"] for s in sig["sessions"]]
    assert ids == ["sess-b", "sess-a"]


def test_session_without_known_ok_is_excluded():
    # Nur ein unpaired pre -> kein ok-Signal -> Session liefert keinen Eintrag
    events = [_pre("sess-c", "Edit", "t9", "2026-06-11T12:00:00.000Z")]
    sig = _signal(events)
    assert sig["sessions"] == []
    assert sig["overall"]["sessions"] == 0
    assert sig["overall"]["success_rate"] is None


def test_limit_keeps_newest_sessions():
    sig = _signal(limit=1)
    assert [s["session_id"] for s in sig["sessions"]] == ["sess-b"]
    # overall bleibt ueber ALLE Sessions gerechnet, limit kuerzt nur die Liste
    assert sig["overall"]["sessions"] == 2


def test_cli_writes_contract_json(tmp_path):
    """P016: der reale Aufrufpfad (Subprozess auf __main__) gegen eine
    isolierte Events-Datei — nie gegen data/events.jsonl."""
    data = tmp_path / "events.jsonl"
    data.write_text(
        "\n".join(json.dumps(e) for e in _events()) + "\n", encoding="utf-8"
    )
    out = tmp_path / "quality-signal.json"
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(QS), "--data", str(data), "--out", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    sig = json.loads(out.read_text(encoding="utf-8"))
    assert sig["schema_v"] == 1
    assert sig["overall"]["failures"] == 1
    assert {s["session_id"] for s in sig["sessions"]} == {"sess-a", "sess-b"}


def test_cli_stdout_without_out_flag(tmp_path):
    data = tmp_path / "events.jsonl"
    data.write_text(
        "\n".join(json.dumps(e) for e in _events()) + "\n", encoding="utf-8"
    )
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(QS), "--data", str(data)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    sig = json.loads(r.stdout)
    assert sig["overall"]["tool_calls"] == 5


def test_cli_empty_data_exits_cleanly(tmp_path):
    data = tmp_path / "events.jsonl"
    data.write_text("", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(QS), "--data", str(data)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    sig = json.loads(r.stdout)
    assert sig["sessions"] == []
    assert sig["overall"]["success_rate"] is None
