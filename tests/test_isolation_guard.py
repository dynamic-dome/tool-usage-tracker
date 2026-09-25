"""Regressionsschutz Test-Isolation (Review 2026-09-08 P1, Lagebericht 2026-09-25).

Befund: Subprozess-Tests setzten nur TOOL_TRACKER_DATA. Der Hook schrieb seine
Eigenlaufzeit dann ueber den Default von TOOL_TRACKER_LATENCY in die echte
data/hook_latency.jsonl, und test_rotation (TOOL_TRACKER_MAX_BYTES=100) konnte die
echte Datei rotieren. Diese Tests pruefen den real aufgeloesten Pfad, nicht nur die
Env-Var (Muster: wiki test-db-isolation, dual-bridge ff70df3).
"""
import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL_DATA = (ROOT / "data").resolve()

_spec = importlib.util.spec_from_file_location("track_tool_use_iso", ROOT / "hook" / "track_tool_use.py")
track = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(track)


def _outside_real_data(p) -> bool:
    p = Path(p).resolve()
    return p != REAL_DATA and REAL_DATA not in p.parents


def test_env_overrides_are_set_and_isolated():
    # Subprozesse erben os.environ: fehlt eine Var, schreibt das Kind in data/.
    for var in ("TOOL_TRACKER_DATA", "TOOL_TRACKER_LATENCY"):
        val = os.environ.get(var)
        assert val, f"{var} ist im Test nicht gesetzt"
        assert _outside_real_data(val), f"{var} zeigt auf echte Daten: {val}"


def test_hook_paths_resolve_outside_real_data():
    assert _outside_real_data(track._events_path()), track._events_path()
    assert _outside_real_data(track._latency_path()), track._latency_path()
