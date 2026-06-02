import importlib.util
from pathlib import Path

LOADER = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
_spec = importlib.util.spec_from_file_location("_load", LOADER)
load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(load)


def _pre(sid, tool, t, **kw):
    d = {"phase": "pre", "session_id": sid, "tool_name": tool, "ts_utc": t,
         "project": "P", "summary": "s", "cwd": "c", "agent": "claude-code"}
    d.update(kw)
    return d


def _post(sid, tool, t, ok=True, error=""):
    return {"phase": "post", "session_id": sid, "tool_name": tool, "ts_utc": t,
            "ok": ok, "error": error, "agent": "claude-code"}


def test_pairs_pre_and_post_into_span():
    evs = [_pre("s1", "Bash", "2026-06-02T10:00:00.000Z"),
           _post("s1", "Bash", "2026-06-02T10:00:00.340Z")]
    spans = load.pair_events(evs)
    assert len(spans) == 1
    s = spans[0]
    assert s["paired"] is True
    assert s["duration_ms"] == 340
    assert s["ok"] is True
    assert s["tool_name"] == "Bash"
    assert s["project"] == "P"  # aus dem Pre-Event übernommen


def test_fifo_same_tool_twice():
    evs = [_pre("s1", "Bash", "2026-06-02T10:00:00.000Z", summary="first"),
           _pre("s1", "Bash", "2026-06-02T10:00:01.000Z", summary="second"),
           _post("s1", "Bash", "2026-06-02T10:00:00.500Z"),
           _post("s1", "Bash", "2026-06-02T10:00:02.000Z")]
    spans = load.pair_events(evs)
    paired = [s for s in spans if s["paired"]]
    assert len(paired) == 2
    # FIFO: erstes Post paart mit erstem Pre (summary "first")
    assert paired[0]["summary"] == "first"
    assert paired[0]["duration_ms"] == 500


def test_unpaired_pre_is_kept_but_marked():
    evs = [_pre("s1", "Read", "2026-06-02T10:00:00.000Z")]
    spans = load.pair_events(evs)
    assert len(spans) == 1
    assert spans[0]["paired"] is False
    assert spans[0]["duration_ms"] is None
    assert spans[0]["ok"] is None


def test_schema_v1_event_without_phase_treated_as_pre():
    # Altdaten ohne phase-Feld
    evs = [{"session_id": "s1", "tool_name": "Glob",
            "ts_utc": "2026-06-02T10:00:00.000Z", "agent": "claude-code"}]
    spans = load.pair_events(evs)
    assert len(spans) == 1
    assert spans[0]["paired"] is False  # kein Post -> ungepaart, aber da


def test_post_only_session_does_not_cross_sessions():
    evs = [_pre("s1", "Bash", "2026-06-02T10:00:00.000Z"),
           _post("s2", "Bash", "2026-06-02T10:00:00.500Z")]
    spans = load.pair_events(evs)
    # Pre s1 ungepaart, Post s2 verwaist -> beide da, beide unpaired
    assert all(s["paired"] is False for s in spans)


def _span(tool, ok, dur, project="P", agent="claude-code", cwd="c"):
    return {"tool_name": tool, "ok": ok, "duration_ms": dur, "project": project,
            "agent": agent, "cwd": cwd, "paired": dur is not None}


def test_success_rate_by_tool():
    spans = [_span("Bash", True, 100), _span("Bash", False, 200),
             _span("Read", True, 50)]
    rates = load.success_rate_by(spans, "tool_name")
    assert rates["Bash"] == 0.5
    assert rates["Read"] == 1.0


def test_success_rate_ignores_unpaired():
    spans = [_span("Bash", True, 100), {"tool_name": "Bash", "ok": None,
             "duration_ms": None, "paired": False}]
    rates = load.success_rate_by(spans, "tool_name")
    assert rates["Bash"] == 1.0  # das ungepaarte zählt nicht


def test_duration_stats_by_tool():
    spans = [_span("Bash", True, 100), _span("Bash", True, 300)]
    stats = load.duration_stats_by(spans, "tool_name")
    assert stats["Bash"]["avg"] == 200
    assert stats["Bash"]["median"] == 200
    assert stats["Bash"]["p95"] >= 300 - 1  # p95 nahe Max bei 2 Werten


def test_path_activity_counts_by_cwd():
    spans = [_span("Bash", True, 100, cwd="C:/a/dual-bridge"),
             _span("Read", True, 50, cwd="C:/a/dual-bridge"),
             _span("Edit", True, 70, cwd="C:/a/Hooks-bau")]
    act = load.path_activity(spans)
    assert act["C:/a/dual-bridge"] == 2
    assert act["C:/a/Hooks-bau"] == 1
