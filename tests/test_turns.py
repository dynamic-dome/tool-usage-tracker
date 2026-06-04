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
