"""Test-Isolation, strukturell erzwungen (Muster: wiki test-db-isolation, dual-bridge ff70df3).

Jeder Test laeuft mit TOOL_TRACKER_DATA und TOOL_TRACKER_LATENCY in einem eigenen
tmp-Ordner. Subprozess-Tests bauen ihre Umgebung per dict(os.environ, ...) und erben
die Overrides damit automatisch. Der Poison-Guard prueft vor UND nach jedem Test den
real aufgeloesten Hook-Pfad und bricht ab, falls er je in die echte data/ zeigt.
"""
import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_REAL_DATA = (_ROOT / "data").resolve()

_spec = importlib.util.spec_from_file_location("track_tool_use_conftest", _ROOT / "hook" / "track_tool_use.py")
_track = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_track)


def _poison_guard(when: str) -> None:
    for name, path in (("events", _track._events_path()), ("latency", _track._latency_path())):
        p = Path(path).resolve()
        if p == _REAL_DATA or _REAL_DATA in p.parents:
            raise RuntimeError(f"REFUSING: {name}-Pfad zeigt {when} auf echte Daten: {p}")


@pytest.fixture(autouse=True)
def isolated_tracker_paths(tmp_path_factory, monkeypatch):
    d = tmp_path_factory.mktemp("tracker-data")
    monkeypatch.setenv("TOOL_TRACKER_DATA", str(d / "events.jsonl"))
    monkeypatch.setenv("TOOL_TRACKER_LATENCY", str(d / "hook_latency.jsonl"))
    _poison_guard("vor dem Test")
    yield
    _poison_guard("nach dem Test")
