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
    assert s["pairing_method"] == "fifo"
    assert s["pairing_confidence"] == "fallback"


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
    assert spans[0]["pairing_method"] == "orphan"
    assert spans[0]["orphan_kind"] == "pre_without_post"


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
    assert {s["orphan_kind"] for s in spans} == {"pre_without_post", "post_without_pre"}


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


# --- tool_use_id-basierte Paarung (exakter Match, FIFO nur Fallback) ---
# Hinweis: die bestehenden _pre/_post bauen Events OHNE tool_use_id (FIFO-Pfad).
# Die folgenden Helfer bauen Events MIT tool_use_id (exakter Match-Pfad).


def _pre_id(sid, tool, t, tuid, **kw):
    d = {"phase": "pre", "session_id": sid, "tool_name": tool, "ts_utc": t,
         "tool_use_id": tuid, "project": "P", "summary": "s", "cwd": "c",
         "agent": "claude-code"}
    d.update(kw)
    return d


def _post_id(sid, tool, t, tuid, ok=True, error=""):
    return {"phase": "post", "session_id": sid, "tool_name": tool, "ts_utc": t,
            "tool_use_id": tuid, "ok": ok, "error": error, "agent": "claude-code"}


def test_pairs_by_tool_use_id_when_posts_out_of_order():
    # Two concurrent Bash calls; Post B arrives BEFORE Post A.
    # With id-based pairing each post must attach to ITS OWN pre, regardless of order.
    evs = [
        _pre_id("s1", "Bash", "2026-06-02T10:00:00.000Z", "idA", summary="A"),
        _pre_id("s1", "Bash", "2026-06-02T10:00:00.100Z", "idB", summary="B"),
        _post_id("s1", "Bash", "2026-06-02T10:00:00.200Z", "idB", ok=False, error="b failed"),
        _post_id("s1", "Bash", "2026-06-02T10:00:00.900Z", "idA", ok=True),
    ]
    spans = load.pair_events(evs)
    paired = {s["summary"]: s for s in spans if s["paired"]}
    assert paired["A"]["ok"] is True
    assert paired["A"]["duration_ms"] == 900
    assert paired["A"]["pairing_method"] == "tool_use_id"
    assert paired["A"]["pairing_confidence"] == "exact"
    assert paired["B"]["ok"] is False
    assert paired["B"]["error"] == "b failed"
    assert paired["B"]["duration_ms"] == 100
    assert paired["B"]["pairing_method"] == "tool_use_id"


def test_id_pairing_falls_back_to_fifo_when_no_id():
    # Events without tool_use_id still pair by FIFO (backward compat / schema v1/v2 no-id)
    evs = [
        {"phase": "pre", "session_id": "s1", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:00:00.000Z", "summary": "x", "project": "P",
         "cwd": "c", "agent": "claude-code"},
        {"phase": "post", "session_id": "s1", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:00:00.300Z", "ok": True, "agent": "claude-code"},
    ]
    spans = load.pair_events(evs)
    assert len([s for s in spans if s["paired"]]) == 1
    assert spans[0]["duration_ms"] == 300


def test_id_pairing_does_not_cross_sessions():
    evs = [
        _pre_id("s1", "Bash", "2026-06-02T10:00:00.000Z", "idX"),
        _post_id("s2", "Bash", "2026-06-02T10:00:00.300Z", "idX"),  # same id, different session
    ]
    spans = load.pair_events(evs)
    # Different sessions must NOT pair even with same id (id is only unique within a session/run)
    assert all(s["paired"] is False for s in spans)
