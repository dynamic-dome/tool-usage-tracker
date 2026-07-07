import importlib.util
import json
from pathlib import Path

_MOD = Path(__file__).resolve().parents[1] / "analysis" / "hook_latency_report.py"
_spec = importlib.util.spec_from_file_location("hook_latency_report", _MOD)
report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(report)


def test_stats_empty():
    assert report.stats([]) == {"count": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0}


def test_stats_single_value():
    s = report.stats([10.0])
    assert s["count"] == 1
    assert s["avg"] == 10.0
    assert s["p50"] == 10.0
    assert s["p95"] == 10.0


def test_stats_median_and_p95_odd_count():
    s = report.stats([1, 2, 3, 4, 100])
    assert s["count"] == 5
    assert s["p50"] == 3
    assert s["p95"] == 100


def test_stats_median_even_count_averages_middle_two():
    s = report.stats([1, 2, 3, 4])
    assert s["p50"] == 2.5


def test_load_records_skips_malformed_lines(tmp_path):
    path = tmp_path / "lat.jsonl"
    path.write_text(
        json.dumps({"hook": "pre", "duration_ms": 1.0}) + "\n"
        + "not json {{{\n"
        + json.dumps({"hook": "post", "duration_ms": 2.0}) + "\n",
        encoding="utf-8",
    )
    recs = report.load_records(path)
    assert len(recs) == 2


def test_load_records_missing_file_returns_empty(tmp_path):
    assert report.load_records(tmp_path / "nope.jsonl") == []
