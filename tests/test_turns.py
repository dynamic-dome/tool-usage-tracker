import importlib.util
from pathlib import Path

_LOAD = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
_spec = importlib.util.spec_from_file_location("_load", _LOAD)
load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(load)


def test_ts_to_ms_parses_iso_z():
    a = load._ts_to_ms("2026-06-04T10:00:00.000Z")
    b = load._ts_to_ms("2026-06-04T10:00:01.500Z")
    assert b - a == 1500


def test_ts_to_ms_returns_none_on_garbage():
    assert load._ts_to_ms("not-a-ts") is None
    assert load._ts_to_ms("") is None
    assert load._ts_to_ms(None) is None


def _span(sid, start_ms, dur_ms):
    # Minimaler Span mit ts_start/ts_end aus ms-Offsets (Basis 2026-06-04T10:00:00Z)
    base = load._ts_to_ms("2026-06-04T10:00:00.000Z")
    from datetime import datetime, timezone
    def ms_to_ts(ms):
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(ms % 1000):03d}Z"
    s = base + start_ms
    return {"session_id": sid, "ts_start": ms_to_ts(s),
            "ts_end": ms_to_ts(s + dur_ms), "duration_ms": dur_ms}


def test_threshold_fallback_when_too_few_gaps():
    spans = [_span("a", 0, 100), _span("a", 200, 100)]  # 1 Gap
    assert load.compute_turn_gap_threshold(spans) == 30000


def test_threshold_fallback_on_empty():
    assert load.compute_turn_gap_threshold([]) == 30000


def test_threshold_adaptive_with_enough_gaps():
    # 9 Spans derselben Session, je 100ms Gap -> 8 Gaps, alle gleich 100
    # median=100, MAD=0 -> threshold=100, aber Klammer min 5000 -> 5000
    spans = [_span("a", i * 200, 100) for i in range(9)]
    assert load.compute_turn_gap_threshold(spans) == 5000


def test_threshold_clamped_to_max():
    # 8 Gaps von je 300000ms (5 min) -> median gross -> Klammer max 120000
    spans = [_span("a", i * 600000, 100) for i in range(9)]
    assert load.compute_turn_gap_threshold(spans) == 120000


def test_threshold_ignores_cross_session_gaps():
    spans = ([_span("a", 0, 100), _span("a", 200, 100)]
             + [_span("b", 0, 100), _span("b", 200, 100)])
    assert load.compute_turn_gap_threshold(spans) == 30000


def test_intra_session_gaps_overlapping_clamped_to_zero():
    # Span 2 startet (1000ms) bevor Span 1 endet (3000ms) -> negativer Gap -> 0
    spans = [_span("a", 0, 3000), _span("a", 1000, 500)]
    assert load._intra_session_gaps(spans) == [0.0]


def test_intra_session_gaps_skips_none_session_id():
    # Spans ohne session_id duerfen NICHT zu einer Pseudo-Session gepoolt werden
    spans = [
        {"session_id": None, "ts_start": "2026-06-04T10:00:00.000Z", "ts_end": "2026-06-04T10:00:00.100Z"},
        {"session_id": None, "ts_start": "2026-06-04T10:00:05.000Z", "ts_end": "2026-06-04T10:00:05.100Z"},
    ]
    assert load._intra_session_gaps(spans) == []


def test_assign_turns_single_burst_is_one_turn():
    spans = [_span("a", 0, 100), _span("a", 200, 100), _span("a", 400, 100)]
    out = load.assign_turns(spans, threshold=30000)
    assert [s["turn_index"] for s in out] == [0, 0, 0]


def test_assign_turns_splits_on_large_gap():
    # Gap zwischen Span 2 und 3 = 60000ms > Schwelle 30000 -> neuer Turn
    spans = [_span("a", 0, 100), _span("a", 200, 100), _span("a", 60300, 100)]
    out = load.assign_turns(spans, threshold=30000)
    assert [s["turn_index"] for s in out] == [0, 0, 1]


def test_assign_turns_independent_per_session():
    spans = [_span("a", 0, 100), _span("a", 60300, 100), _span("b", 0, 100)]
    out = load.assign_turns(spans, threshold=30000)
    by_sid = {}
    for s in out:
        by_sid.setdefault(s["session_id"], []).append(s["turn_index"])
    assert by_sid["a"] == [0, 1]
    assert by_sid["b"] == [0]


def test_assign_turns_orphans_without_ts_start_go_last():
    spans = [_span("a", 0, 100),
             {"session_id": "a", "ts_start": None, "ts_end": None, "duration_ms": None}]
    out = load.assign_turns(spans, threshold=30000)
    orphan = [s for s in out if s.get("ts_start") is None][0]
    real = [s for s in out if s.get("ts_start") is not None][0]
    assert orphan["turn_index"] == real["turn_index"]


def test_assign_turns_robust_to_unsorted_input():
    spans = [_span("a", 400, 100), _span("a", 0, 100), _span("a", 200, 100)]
    out = load.assign_turns(spans, threshold=30000)
    assert all(s["turn_index"] == 0 for s in out)


def test_assign_turns_is_deterministic():
    spans = [_span("a", 0, 100), _span("a", 60300, 100)]
    a = [s["turn_index"] for s in load.assign_turns(spans, 30000)]
    b = [s["turn_index"] for s in load.assign_turns(spans, 30000)]
    assert a == b
