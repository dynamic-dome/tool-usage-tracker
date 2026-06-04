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
