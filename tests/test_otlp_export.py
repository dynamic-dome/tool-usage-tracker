"""Tests fuer analysis/otlp_export.py (TEIL C — duenner OTLP-Trace-Exporter).

Mappt gepaarte Spans -> OTLP/JSON resourceSpans (gen_ai.*-konforme Attribute)
und kann sie optional an einen lokalen OTLP/HTTP-Collector (Jaeger/Grafana LGTM)
POSTen. Strikt stdlib-only (json + urllib), KEINE neue Abhaengigkeit, Hot-Path
unberuehrt. Der HTTP-Push hat einen Graceful-Fallback (kein Crash, klare RC).

Getestet:
  - Mapping-Vertrag: resourceSpans-Struktur, Trace/Span-IDs (hex, korrekte
    Laenge), Zeiten in UnixNano, Status (ok->UNSET/ERROR), gen_ai.*-Attribute.
  - Determinismus der IDs (gleicher Input -> gleiche trace_id/span_id).
  - Eine Session -> ein gemeinsamer trace_id ueber ihre Spans.
  - Ungepaarte Spans ohne ts_start werden ausgelassen (kein valider Span).
  - Negativ: leere Eingabe -> leere resourceSpans.
"""
import importlib.util
from pathlib import Path

MOD = Path(__file__).resolve().parents[1] / "analysis" / "otlp_export.py"
_spec = importlib.util.spec_from_file_location("otlp_export", MOD)
ox = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ox)


def _span(**kw):
    base = {
        "tool_name": "Bash", "agent": "claude-code", "session_id": "sess-1",
        "project": "P", "summary": "git status", "cwd": "/x/P",
        "ts_start": "2026-06-05T10:00:00.000Z", "ts_end": "2026-06-05T10:00:00.350Z",
        "duration_ms": 350, "ok": True, "error": "", "paired": True,
        "pairing_method": "tool_use_id", "risk": "low", "app": "git",
        "intent": "read", "mutating": False,
        "input_tokens": 100, "output_tokens": 20, "cost_usd": 0.001,
    }
    base.update(kw)
    return base


def _all_spans(doc):
    out = []
    for rs in doc.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            out.extend(ss.get("spans", []))
    return out


def _attr(span, key):
    for a in span.get("attributes", []):
        if a.get("key") == key:
            v = a.get("value", {})
            return (v.get("stringValue") if "stringValue" in v else
                    v.get("intValue") if "intValue" in v else
                    v.get("doubleValue") if "doubleValue" in v else
                    v.get("boolValue"))
    return None


def test_build_resource_spans_basic_structure():
    doc = ox.build_resource_spans([_span()])
    assert "resourceSpans" in doc
    spans = _all_spans(doc)
    assert len(spans) == 1
    s = spans[0]
    assert s["name"] == "Bash"
    # Trace/Span-IDs sind hex der korrekten Laenge (16 byte / 8 byte)
    assert len(s["traceId"]) == 32 and int(s["traceId"], 16) >= 0
    assert len(s["spanId"]) == 16 and int(s["spanId"], 16) >= 0
    # Zeiten in UnixNano (int, end > start)
    assert isinstance(s["startTimeUnixNano"], int)
    assert s["endTimeUnixNano"] > s["startTimeUnixNano"]


def test_gen_ai_attributes_present():
    doc = ox.build_resource_spans([_span()])
    s = _all_spans(doc)[0]
    assert _attr(s, "gen_ai.agent.name") == "claude-code"
    assert _attr(s, "gen_ai.tool.name") == "Bash"
    assert _attr(s, "gen_ai.usage.input_tokens") == 100
    assert _attr(s, "gen_ai.usage.output_tokens") == 20
    assert abs(_attr(s, "gen_ai.usage.cost_usd") - 0.001) < 1e-9
    # tracker-eigene Klassifizierung als eigener Namespace
    assert _attr(s, "tracker.risk") == "low"
    assert _attr(s, "tracker.app") == "git"
    assert _attr(s, "tracker.mutating") is False
    assert _attr(s, "tracker.session_id") == "sess-1"


def test_status_unset_when_ok_and_error_when_failed():
    ok_doc = ox.build_resource_spans([_span(ok=True)])
    assert _all_spans(ok_doc)[0].get("status", {}).get("code") in (0, "STATUS_CODE_UNSET", None) \
        or _all_spans(ok_doc)[0].get("status", {}) == {}
    err_doc = ox.build_resource_spans([_span(ok=False, error="boom")])
    st = _all_spans(err_doc)[0]["status"]
    assert st["code"] in (2, "STATUS_CODE_ERROR")
    assert st.get("message") == "boom"


def test_same_session_shares_trace_id():
    s1 = _span(tool_name="Bash", ts_start="2026-06-05T10:00:00.000Z",
               ts_end="2026-06-05T10:00:00.100Z", tool_use_id="a")
    s2 = _span(tool_name="Read", ts_start="2026-06-05T10:00:01.000Z",
               ts_end="2026-06-05T10:00:01.100Z", tool_use_id="b")
    doc = ox.build_resource_spans([s1, s2])
    spans = _all_spans(doc)
    assert len(spans) == 2
    assert spans[0]["traceId"] == spans[1]["traceId"]   # gleiche Session
    assert spans[0]["spanId"] != spans[1]["spanId"]     # verschiedene Spans


def test_different_session_different_trace_id():
    a = _span(session_id="sess-A")
    b = _span(session_id="sess-B", ts_start="2026-06-05T11:00:00.000Z",
              ts_end="2026-06-05T11:00:00.100Z")
    doc = ox.build_resource_spans([a, b])
    spans = _all_spans(doc)
    assert spans[0]["traceId"] != spans[1]["traceId"]


def test_ids_are_deterministic():
    doc1 = ox.build_resource_spans([_span()])
    doc2 = ox.build_resource_spans([_span()])
    s1, s2 = _all_spans(doc1)[0], _all_spans(doc2)[0]
    assert s1["traceId"] == s2["traceId"]
    assert s1["spanId"] == s2["spanId"]


def test_unpaired_span_without_ts_start_is_skipped():
    bad = _span(paired=False, ts_start=None, ts_end=None, duration_ms=None, ok=None)
    doc = ox.build_resource_spans([bad])
    assert _all_spans(doc) == []


def test_empty_input_yields_empty_doc():
    doc = ox.build_resource_spans([])
    assert doc["resourceSpans"] == []


def test_missing_tokens_omit_gen_ai_usage_attributes():
    s = _span(input_tokens=None, output_tokens=None, cost_usd=None,
              cache_read_tokens=None)
    doc = ox.build_resource_spans([s])
    sp = _all_spans(doc)[0]
    assert _attr(sp, "gen_ai.usage.input_tokens") is None
    assert _attr(sp, "gen_ai.usage.cost_usd") is None
    # nicht-usage-Attribute bleiben
    assert _attr(sp, "gen_ai.tool.name") == "Bash"


def test_export_to_collector_graceful_when_unreachable():
    # Kein laufender Collector -> kein Crash, RC signalisiert Misserfolg.
    rc = ox.export([_span()], endpoint="http://127.0.0.1:59999/v1/traces",
                   timeout=0.5)
    assert rc is False
