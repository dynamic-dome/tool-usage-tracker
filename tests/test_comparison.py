"""Tests fuer die Run-Comparison-Aggregation (B-3).

Vergleicht Gruppen (per agent ODER per session) nebeneinander, um den
Dual-Agent-Setup (Claude Code vs. Codex) sichtbar zu machen. Pro Gruppe:
  - tool_calls      : Anzahl Spans (gepaart + ungepaart)
  - paired          : Anzahl gepaarter Spans
  - failures        : gepaarte Spans mit ok is False (fehlgeschlagene Calls)
  - retries         : == failures (fehlgeschlagene Calls ziehen Retry nach sich;
                      ehrlich benannt, da Schema kein explizites retry-Feld hat)
  - success_rate    : ok / (ok+fail) ueber gepaarte Spans mit bekanntem ok
  - total_duration_ms : Summe duration_ms ueber gepaarte Spans
  - risk            : {high,medium,low,unknown} Counts
  - mutating_count  : Anzahl mutierender Spans
  - total_cost_usd  : Summe cost_usd (None ignoriert)
"""
import importlib.util
from pathlib import Path

LOADER = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
_spec = importlib.util.spec_from_file_location("_load", LOADER)
load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(load)


def _pre(sid, tool, t, agent="claude-code", **kw):
    d = {"phase": "pre", "session_id": sid, "tool_name": tool, "ts_utc": t,
         "project": "P", "summary": "s", "cwd": "c", "agent": agent}
    d.update(kw)
    return d


def _post(sid, tool, t, ok=True, error="", agent="claude-code", **kw):
    d = {"phase": "post", "session_id": sid, "tool_name": tool, "ts_utc": t,
         "ok": ok, "error": error, "agent": agent}
    d.update(kw)
    return d


def test_comparison_by_agent_basic_counts():
    evs = [
        # claude-code: 2 calls, 1 fail
        _pre("s1", "Bash", "2026-06-05T10:00:00.000Z", agent="claude-code", risk="low"),
        _post("s1", "Bash", "2026-06-05T10:00:00.500Z", ok=True, agent="claude-code"),
        _pre("s1", "Edit", "2026-06-05T10:00:01.000Z", agent="claude-code", risk="high", mutating=True),
        _post("s1", "Edit", "2026-06-05T10:00:01.300Z", ok=False, error="boom", agent="claude-code"),
        # codex: 1 call, 0 fail
        _pre("s2", "Read", "2026-06-05T10:00:02.000Z", agent="codex", risk="low"),
        _post("s2", "Read", "2026-06-05T10:00:02.200Z", ok=True, agent="codex"),
    ]
    spans = load.pair_events(evs)
    comp = load.comparison(spans, key="agent")
    assert set(comp) == {"claude-code", "codex"}
    cc = comp["claude-code"]
    assert cc["tool_calls"] == 2
    assert cc["paired"] == 2
    assert cc["failures"] == 1
    assert cc["retries"] == 1
    assert cc["mutating_count"] == 1
    assert cc["total_duration_ms"] == 800  # 500 + 300
    assert abs(cc["success_rate"] - 0.5) < 1e-9
    assert cc["risk"]["low"] == 1
    assert cc["risk"]["high"] == 1
    cx = comp["codex"]
    assert cx["tool_calls"] == 1
    assert cx["failures"] == 0
    assert cx["retries"] == 0
    assert abs(cx["success_rate"] - 1.0) < 1e-9


def test_comparison_by_session():
    evs = [
        _pre("sA", "Bash", "2026-06-05T10:00:00.000Z"),
        _post("sA", "Bash", "2026-06-05T10:00:00.100Z", ok=True),
        _pre("sB", "Bash", "2026-06-05T10:01:00.000Z"),
        _post("sB", "Bash", "2026-06-05T10:01:00.200Z", ok=True),
        _pre("sB", "Edit", "2026-06-05T10:01:01.000Z"),
        _post("sB", "Edit", "2026-06-05T10:01:01.400Z", ok=True),
    ]
    spans = load.pair_events(evs)
    comp = load.comparison(spans, key="session_id")
    assert comp["sA"]["tool_calls"] == 1
    assert comp["sB"]["tool_calls"] == 2
    assert comp["sB"]["total_duration_ms"] == 600


def test_comparison_sums_cost_ignoring_none():
    evs = [
        _pre("s1", "Bash", "2026-06-05T10:00:00.000Z", agent="claude-code"),
        _post("s1", "Bash", "2026-06-05T10:00:00.100Z", ok=True, agent="claude-code", cost_usd=0.01),
        _pre("s1", "Read", "2026-06-05T10:00:01.000Z", agent="claude-code"),
        _post("s1", "Read", "2026-06-05T10:00:01.100Z", ok=True, agent="claude-code"),  # keine cost
    ]
    spans = load.pair_events(evs)
    comp = load.comparison(spans, key="agent")
    assert abs(comp["claude-code"]["total_cost_usd"] - 0.01) < 1e-9


def test_comparison_counts_unpaired_in_tool_calls_but_not_duration():
    evs = [
        _pre("s1", "Bash", "2026-06-05T10:00:00.000Z", agent="codex"),  # unpaired pre
        _pre("s1", "Read", "2026-06-05T10:00:01.000Z", agent="codex"),
        _post("s1", "Read", "2026-06-05T10:00:01.300Z", ok=True, agent="codex"),
    ]
    spans = load.pair_events(evs)
    comp = load.comparison(spans, key="agent")
    cx = comp["codex"]
    assert cx["tool_calls"] == 2      # beide Spans zaehlen
    assert cx["paired"] == 1          # nur Read ist gepaart
    assert cx["total_duration_ms"] == 300  # nur gepaarter Span


def test_comparison_empty_spans():
    assert load.comparison([], key="agent") == {}


def test_comparison_default_key_is_agent():
    evs = [
        _pre("s1", "Bash", "2026-06-05T10:00:00.000Z", agent="codex"),
        _post("s1", "Bash", "2026-06-05T10:00:00.100Z", ok=True, agent="codex"),
    ]
    spans = load.pair_events(evs)
    comp = load.comparison(spans)  # ohne key -> agent
    assert "codex" in comp
