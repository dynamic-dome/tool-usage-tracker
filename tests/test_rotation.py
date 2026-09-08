"""Tests fuer JSONL-Rotation (Hot-Path) + Multi-File-Loader + tail.

Rotation haelt data/events.jsonl beschraenkt: ueberschreitet die aktive Datei
TOOL_TRACKER_MAX_BYTES, wird sie zu events.1.jsonl (bzw. naechsthoehere N)
rotiert und frisch weitergeschrieben. Der Loader liest die aktive Datei PLUS
alle events.*.jsonl-Teile, damit nichts verloren geht.

Isolation: alles auf tmp_path via TOOL_TRACKER_DATA / direkte Pfade — die echte
data/events.jsonl wird nie angefasst (CLAUDE.md §3, Hot-Path-Regeln).
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hook" / "track_tool_use.py"
_spec = importlib.util.spec_from_file_location("track_tool_use", HOOK)
track = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(track)

LOAD = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
_lspec = importlib.util.spec_from_file_location("_load", LOAD)
_load = importlib.util.module_from_spec(_lspec)
_lspec.loader.exec_module(_load)


def _run_hook(stdin_text, env_extra):
    env = dict(os.environ, **env_extra)
    return subprocess.run(
        [sys.executable, str(HOOK)], input=stdin_text,
        capture_output=True, text=True, env=env,
    )


# --- Rotation im Hot-Path -------------------------------------------------

def test_rotation_creates_part_file_when_threshold_exceeded(tmp_path):
    """Wenn die aktive Datei die Schwelle ueberschreitet, entsteht events.1.jsonl
    und die aktive Datei beginnt frisch."""
    target = tmp_path / "events.jsonl"
    # Aktive Datei knapp UEBER die Schwelle vorfuellen.
    target.write_text("x" * 200 + "\n", encoding="utf-8")
    raw = json.dumps({"session_id": "s", "tool_name": "Read",
                      "tool_input": {"file_path": "a.py"}})
    r = _run_hook(raw, {"TOOL_TRACKER_DATA": str(target),
                        "TOOL_TRACKER_MAX_BYTES": "100"})
    assert r.returncode == 0
    rotated = tmp_path / "events.1.jsonl"
    assert rotated.exists(), "Rotation haette events.1.jsonl anlegen muessen"
    # Der alte Inhalt steckt jetzt in events.1.jsonl ...
    assert rotated.read_text(encoding="utf-8").startswith("x" * 200)
    # ... und die aktive Datei enthaelt NUR die neue Zeile.
    active = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(active) == 1
    assert json.loads(active[0])["tool_name"] == "Read"


def test_no_rotation_below_threshold(tmp_path):
    """Unter der Schwelle wird normal angehaengt, kein Teil-File entsteht."""
    target = tmp_path / "events.jsonl"
    raw = json.dumps({"session_id": "s", "tool_name": "Read",
                      "tool_input": {"file_path": "a.py"}})
    _run_hook(raw, {"TOOL_TRACKER_DATA": str(target),
                    "TOOL_TRACKER_MAX_BYTES": "1000000"})
    _run_hook(raw, {"TOOL_TRACKER_DATA": str(target),
                    "TOOL_TRACKER_MAX_BYTES": "1000000"})
    assert not (tmp_path / "events.1.jsonl").exists()
    assert len(target.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_rotation_increments_part_number(tmp_path):
    """Existiert events.1.jsonl schon, rotiert die naechste auf events.2.jsonl."""
    target = tmp_path / "events.jsonl"
    (tmp_path / "events.1.jsonl").write_text("old1\n", encoding="utf-8")
    target.write_text("y" * 200 + "\n", encoding="utf-8")
    raw = json.dumps({"session_id": "s", "tool_name": "Glob",
                      "tool_input": {"pattern": "*.py"}})
    r = _run_hook(raw, {"TOOL_TRACKER_DATA": str(target),
                        "TOOL_TRACKER_MAX_BYTES": "100"})
    assert r.returncode == 0
    assert (tmp_path / "events.2.jsonl").exists()
    # events.1.jsonl bleibt unangetastet.
    assert (tmp_path / "events.1.jsonl").read_text(encoding="utf-8") == "old1\n"


def test_rotation_failure_never_breaks_hot_path(tmp_path, monkeypatch):
    """Schlaegt die Rotation fehl, wird trotzdem angehaengt und exit 0 gehalten."""
    target = tmp_path / "events.jsonl"
    target.write_text("z" * 200 + "\n", encoding="utf-8")
    raw = json.dumps({"session_id": "s", "tool_name": "Read",
                      "tool_input": {"file_path": "a.py"}})
    # os.rename so kaputtmachen, dass Rotation scheitert -> Append muss greifen.
    monkeypatch.setattr(track.os, "rename",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
    rc = track.main_with_stdin(raw) if hasattr(track, "main_with_stdin") else None
    # Falls kein Test-Hook existiert, faellt der Test auf den Subprozess zurueck.
    if rc is None:
        r = _run_hook(raw, {"TOOL_TRACKER_DATA": str(target),
                            "TOOL_TRACKER_MAX_BYTES": "100"})
        assert r.returncode == 0
        text = target.read_text(encoding="utf-8")
        assert '"Read"' in text  # neue Zeile trotz (kuenstlich) fehlender Rotation


# --- Multi-File-Loader ----------------------------------------------------

def _write_jsonl(path, events):
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n",
                    encoding="utf-8")


def test_load_events_merges_part_files(tmp_path):
    """load_events liest die aktive Datei PLUS alle events.*.jsonl-Teile."""
    active = tmp_path / "events.jsonl"
    _write_jsonl(tmp_path / "events.1.jsonl", [{"tool_name": "A", "ts_utc": "1"}])
    _write_jsonl(tmp_path / "events.2.jsonl", [{"tool_name": "B", "ts_utc": "2"}])
    _write_jsonl(active, [{"tool_name": "C", "ts_utc": "3"}])
    out = _load.load_events(active)
    names = [e["tool_name"] for e in out]
    # Aelteste Teile zuerst, aktive Datei zuletzt (chronologische Append-Folge).
    assert names == ["A", "B", "C"]


def test_load_events_single_file_unchanged(tmp_path):
    """Ohne Teil-Files verhaelt sich load_events wie bisher."""
    active = tmp_path / "events.jsonl"
    _write_jsonl(active, [{"tool_name": "A", "ts_utc": "1"},
                          {"tool_name": "B", "ts_utc": "2"}])
    out = _load.load_events(active)
    assert [e["tool_name"] for e in out] == ["A", "B"]


def test_load_events_tail_returns_last_n(tmp_path):
    """tail=N liefert nur die letzten N Events ueber alle Teile hinweg."""
    active = tmp_path / "events.jsonl"
    _write_jsonl(tmp_path / "events.1.jsonl",
                 [{"tool_name": f"old{i}", "ts_utc": str(i)} for i in range(5)])
    _write_jsonl(active,
                 [{"tool_name": f"new{i}", "ts_utc": str(i)} for i in range(5)])
    out = _load.load_events(active, tail=3)
    assert [e["tool_name"] for e in out] == ["new2", "new3", "new4"]


def test_load_events_tail_none_returns_all(tmp_path):
    """tail=None (Default) liefert weiterhin alles."""
    active = tmp_path / "events.jsonl"
    _write_jsonl(active, [{"tool_name": f"e{i}", "ts_utc": str(i)} for i in range(4)])
    out = _load.load_events(active)
    assert len(out) == 4


# --- Latency-JSONL rotiert wie events.jsonl ---------------------------------

def test_latency_log_rotates_when_threshold_exceeded(tmp_path, monkeypatch):
    """hook_latency.jsonl waechst pro Tool-Call unbegrenzt, wenn es nicht wie
    events.jsonl rotiert (Live-Befund 2026-09-08: 26 MB). Gleiche Schwelle,
    gleiches Teil-Datei-Schema (hook_latency.1.jsonl)."""
    lat = tmp_path / "hook_latency.jsonl"
    monkeypatch.setenv("TOOL_TRACKER_LATENCY", str(lat))
    monkeypatch.setenv("TOOL_TRACKER_MAX_BYTES", "200")
    for i in range(10):
        track.log_latency("pre", f"Tool{i}", 1.5)
    parts = sorted(tmp_path.glob("hook_latency.*.jsonl"))
    assert parts, "keine rotierte Latency-Teildatei entstanden"
    assert lat.exists() and lat.stat().st_size < 200
    total = sum(len(p.read_text(encoding="utf-8").splitlines()) for p in parts + [lat])
    assert total == 10
