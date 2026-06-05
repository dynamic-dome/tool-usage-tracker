"""Tests fuer D-3 — Drift/Spend-Score pro Session (Themen-Drift).

'On-Task' = das dominante (app, intent)-Thema einer Session (haeufigster Span).
Drift = Anteil Tool-Calls AUSSERHALB davon, sowohl nach Anzahl als auch
kosten-gewichtet (Off-Task-Spend). Mutierende Off-Task-Spans werden separat
gezaehlt (gefaehrlichstes Signal). Unklassifizierte Spans (kein app) zaehlen
weder on- noch off-task.

Kosten sind turn-dedupliziert (ein requestId zaehlt einmal), konsistent mit
cost_breakdown.
"""
import importlib.util
from pathlib import Path

LOAD = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
_spec = importlib.util.spec_from_file_location("_load", LOAD)
_load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_load)


def _span(session, app, intent, **extra):
    s = {"session_id": session, "app": app, "intent": intent}
    s.update(extra)
    return s


def test_drift_dominant_theme_is_on_task():
    """Das haeufigste (app,intent) ist On-Task; der Rest driftet."""
    spans = [
        _span("s", "git", "read"),
        _span("s", "git", "read"),
        _span("s", "git", "read"),
        _span("s", "python", "test"),   # off-task
    ]
    d = _load.drift_breakdown(spans)["s"]
    assert d["dominant"] == "git/read"
    assert d["on_task_count"] == 3
    assert d["off_task_count"] == 1
    assert abs(d["drift_ratio"] - 0.25) < 1e-9


def test_drift_zero_when_single_theme():
    """Eine Session mit nur einem Thema hat Drift 0."""
    spans = [_span("s", "git", "read"), _span("s", "git", "read")]
    d = _load.drift_breakdown(spans)["s"]
    assert d["drift_ratio"] == 0.0
    assert d["off_task_count"] == 0


def test_drift_spend_weighted_by_cost():
    """Off-Task-Spend = Off-Task-Kosten / Gesamtkosten (turn-dedupliziert)."""
    spans = [
        _span("s", "git", "read", cost_usd=1.0, request_id="r1"),
        _span("s", "git", "read", cost_usd=1.0, request_id="r2"),
        _span("s", "node", "write", cost_usd=8.0, request_id="r3"),  # off-task, teuer
    ]
    d = _load.drift_breakdown(spans)["s"]
    assert d["dominant"] == "git/read"
    # Off-Task-Kosten 8 von 10 gesamt.
    assert abs(d["spend_drift_ratio"] - 0.8) < 1e-9
    assert abs(d["off_task_cost_usd"] - 8.0) < 1e-9
    assert abs(d["total_cost_usd"] - 10.0) < 1e-9


def test_drift_spend_dedupes_turn():
    """Mehrere Calls desselben Turns (request_id) zaehlen die Kosten EINMAL."""
    spans = [
        _span("s", "git", "read", cost_usd=2.0, request_id="r1"),
        _span("s", "node", "write", cost_usd=5.0, request_id="r2"),
        _span("s", "node", "write", cost_usd=5.0, request_id="r2"),  # selber Turn
    ]
    d = _load.drift_breakdown(spans)["s"]
    # node/write ist 2 Calls vs git/read 1 -> node/write dominant.
    assert d["dominant"] == "node/write"
    # Gesamtkosten turn-dedupliziert: r1=2 + r2=5 = 7 (NICHT 12).
    assert abs(d["total_cost_usd"] - 7.0) < 1e-9


def test_drift_counts_mutating_off_task():
    """Mutierende Off-Task-Spans werden separat gezaehlt (gefaehrlichstes Signal)."""
    spans = [
        _span("s", "git", "read"),
        _span("s", "git", "read"),
        _span("s", "git", "write", mutating=True),   # off-task + mutating
        _span("s", "node", "write", mutating=True),  # off-task + mutating
    ]
    d = _load.drift_breakdown(spans)["s"]
    assert d["dominant"] == "git/read"
    assert d["off_task_mutating"] == 2


def test_drift_unclassified_spans_excluded():
    """Spans ohne app (unklassifiziert) zaehlen weder on- noch off-task."""
    spans = [
        _span("s", "git", "read"),
        _span("s", "git", "read"),
        {"session_id": "s"},          # kein app -> unclassified
        {"session_id": "s", "app": ""},  # leeres app -> unclassified
    ]
    d = _load.drift_breakdown(spans)["s"]
    assert d["on_task_count"] == 2
    assert d["off_task_count"] == 0
    assert d["unclassified_count"] == 2
    assert d["drift_ratio"] == 0.0


def test_drift_per_session_isolated():
    """Jede Session bekommt ihren eigenen Drift-Score."""
    spans = [
        _span("a", "git", "read"),
        _span("a", "node", "write"),   # drift in a
        _span("b", "python", "test"),
        _span("b", "python", "test"),  # kein drift in b
    ]
    out = _load.drift_breakdown(spans)
    assert set(out.keys()) == {"a", "b"}
    assert out["a"]["off_task_count"] == 1
    assert out["b"]["off_task_count"] == 0


def test_drift_tiebreak_deterministic():
    """Bei Gleichstand der Haeufigkeit entscheiden Kosten, dann Alphabet —
    deterministisch, kein Zufall."""
    spans = [
        _span("s", "git", "read", cost_usd=1.0, request_id="r1"),
        _span("s", "node", "write", cost_usd=9.0, request_id="r2"),
    ]
    # Beide 1x -> hoehere Kosten (node/write) gewinnt als dominant.
    d = _load.drift_breakdown(spans)["s"]
    assert d["dominant"] == "node/write"


def test_drift_empty_spans():
    """Keine Spans -> leeres Dict, kein Crash."""
    assert _load.drift_breakdown([]) == {}


# --- Tool-app-Ableitung (Datei-Tools klassifizieren, Auswerte-Pfad) ----------

def test_span_app_intent_uses_existing_classification():
    """Hat der Span bereits app (Bash/MCP), wird sie genutzt."""
    s = {"tool_name": "Bash", "app": "git", "intent": "read"}
    assert _load._span_app_intent(s) == ("git", "read")


def test_span_app_intent_derives_file_tools():
    """Read/Edit/Write/NotebookEdit -> app='file' mit read/write-intent."""
    assert _load._span_app_intent({"tool_name": "Read"}) == ("file", "read")
    assert _load._span_app_intent({"tool_name": "Edit"}) == ("file", "write")
    assert _load._span_app_intent({"tool_name": "Write"}) == ("file", "write")
    assert _load._span_app_intent({"tool_name": "NotebookEdit"}) == ("file", "write")


def test_span_app_intent_derives_search_and_agent():
    """Grep/Glob -> search; Task/Agent -> agent."""
    assert _load._span_app_intent({"tool_name": "Grep"}) == ("search", "read")
    assert _load._span_app_intent({"tool_name": "Glob"}) == ("search", "read")
    assert _load._span_app_intent({"tool_name": "Task"}) == ("agent", "delegate")
    assert _load._span_app_intent({"tool_name": "Agent"}) == ("agent", "delegate")


def test_span_app_intent_unknown_tool_is_none():
    """Unbekanntes Tool ohne app -> (None, None), zaehlt als unclassified."""
    assert _load._span_app_intent({"tool_name": "SomethingNew"}) == (None, None)


def test_drift_uses_derived_app_for_file_tools():
    """drift_breakdown nutzt die abgeleitete app — Read/Edit zaehlen jetzt mit."""
    spans = [
        {"session_id": "s", "tool_name": "Read"},
        {"session_id": "s", "tool_name": "Read"},
        {"session_id": "s", "tool_name": "Read"},
        {"session_id": "s", "tool_name": "Bash", "app": "git", "intent": "write"},
    ]
    d = _load.drift_breakdown(spans)["s"]
    assert d["dominant"] == "file/read"
    assert d["on_task_count"] == 3
    assert d["off_task_count"] == 1
    assert d["unclassified_count"] == 0
