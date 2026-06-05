"""TEIL C — Duenner OTLP-Trace-Exporter (stdlib-only).

Mappt gepaarte Spans (aus analysis/_load.pair_events) auf ein OTLP/JSON-
Dokument (``resourceSpans``) mit gen_ai.*-konformen Attributen und kann es
optional an einen lokalen OTLP/HTTP-Collector (Jaeger all-in-one, Grafana
LGTM, OpenTelemetry Collector) POSTen.

Designentscheidungen
--------------------
* **Trace = Session**: alle Tool-Calls einer ``session_id`` teilen sich eine
  trace_id. So entsteht im Collector ein Trace pro Agent-Session.
* **Span = Tool-Call**: jeder gepaarte Span wird ein OTLP-Span. span_id ist
  deterministisch aus session_id + Identitaet (tool_use_id falls vorhanden,
  sonst tool_name) + ts_start abgeleitet.
* **Deterministische IDs**: trace_id (16 Byte / 32 hex) und span_id (8 Byte /
  16 hex) sind reine Hashes — gleicher Input ergibt immer dieselben IDs, damit
  wiederholter Export idempotent gegen den Collector ist.
* **Status**: ok -> UNSET (leeres status-Dict), ok=False -> ERROR (code 2,
  message = error).
* **Strikt stdlib-only**: json, urllib, hashlib, datetime. KEINE neue
  Abhaengigkeit. Hot-Path (hook/) bleibt unberuehrt.
* **Graceful-Fallback**: ein nicht erreichbarer Collector fuehrt NICHT zum
  Crash — ``export`` faengt jeden Fehler und liefert ``False``.

Mapping-Quelle: OpenTelemetry GenAI semantic conventions (gen_ai.*) sowie das
OTLP/JSON-Protobuf-Mapping (resourceSpans -> scopeSpans -> spans).
"""
from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

_TS_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"
_SCOPE_NAME = "tool-usage-tracker"

# OTLP Status-Codes (siehe trace.proto: StatusCode)
_STATUS_ERROR = 2


def _ts_to_unix_nano(ts):
    """ISO-Zeitstempel -> Nanosekunden seit Epoch (int) oder None."""
    if not ts:
        return None
    try:
        dt = datetime.strptime(ts, _TS_FMT).replace(tzinfo=timezone.utc)
        return int(round(dt.timestamp() * 1_000_000_000))
    except Exception:
        return None


def _trace_id(session_id):
    """Deterministische 16-Byte-Trace-ID (32 hex) aus der session_id.

    Sessions ohne ID landen in einem stabilen Sammel-Trace ("__none__").
    """
    key = "trace:%s" % (session_id if session_id is not None else "__none__")
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _span_id(span):
    """Deterministische 8-Byte-Span-ID (16 hex).

    Identitaet = session_id + (tool_use_id|tool_name) + ts_start. tool_use_id
    ist die stabilste Wahl, faellt aber auf tool_name zurueck (Schema-v1).
    """
    ident = (
        str(span.get("session_id")),
        str(span.get("tool_use_id") or span.get("tool_name")),
        str(span.get("ts_start")),
    )
    key = "span:" + "|".join(ident)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _av(value):
    """Python-Wert -> OTLP AnyValue-Dict. None-Werte filtert der Aufrufer."""
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": value}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _attrs(span):
    """Baut die OTLP-Attributliste (gen_ai.* + tracker.*).

    None-Werte werden ausgelassen (OTLP erwartet keine null-AnyValues).
    """
    pairs = [
        ("gen_ai.agent.name", span.get("agent")),
        ("gen_ai.tool.name", span.get("tool_name")),
        ("gen_ai.usage.input_tokens", span.get("input_tokens")),
        ("gen_ai.usage.output_tokens", span.get("output_tokens")),
        ("gen_ai.usage.cost_usd", span.get("cost_usd")),
        ("tracker.session_id", span.get("session_id")),
        ("tracker.project", span.get("project")),
        ("tracker.risk", span.get("risk")),
        ("tracker.app", span.get("app")),
        ("tracker.intent", span.get("intent")),
        ("tracker.mutating", span.get("mutating")),
    ]
    out = []
    for key, val in pairs:
        if val is None:
            continue
        out.append({"key": key, "value": _av(val)})
    return out


def _status(span):
    """ok=True -> {} (UNSET), ok=False -> {code: ERROR, message: error}.

    ok=None (z.B. ungepaarter Post ohne Pre) bleibt UNSET — wir behaupten
    keinen Fehler ohne Evidenz (Ground-Truth-Regel)."""
    if span.get("ok") is False:
        st = {"code": _STATUS_ERROR}
        err = span.get("error")
        if err:
            st["message"] = err
        return st
    return {}


def _to_otlp_span(span):
    """Ein gepaarter Span -> OTLP-Span-Dict, oder None wenn nicht exportierbar.

    Ohne gueltigen ts_start (Nanosekunden) ist kein valider Span moeglich ->
    None (Aufrufer laesst ihn aus). end faellt zur Not auf start zurueck.
    """
    start = _ts_to_unix_nano(span.get("ts_start"))
    if start is None:
        return None
    end = _ts_to_unix_nano(span.get("ts_end"))
    if end is None or end < start:
        end = start
    return {
        "traceId": _trace_id(span.get("session_id")),
        "spanId": _span_id(span),
        "name": span.get("tool_name") or "tool",
        "kind": 3,  # SPAN_KIND_CLIENT (Tool-Aufruf nach aussen)
        "startTimeUnixNano": start,
        "endTimeUnixNano": end,
        "attributes": _attrs(span),
        "status": _status(span),
    }


def build_resource_spans(spans):
    """Liste gepaarter Spans -> OTLP/JSON-Dokument ``{"resourceSpans": [...]}``.

    Gruppiert nach (agent, session_id): eine Resource pro Agent, ein ScopeSpan
    je Session. Spans ohne ts_start werden ausgelassen. Leere Eingabe ->
    ``{"resourceSpans": []}``.
    """
    # Gruppierung: agent -> session_id -> [otlp_span]
    by_agent = {}
    for sp in spans or []:
        otlp = _to_otlp_span(sp)
        if otlp is None:
            continue
        agent = sp.get("agent") or "unknown"
        sess = sp.get("session_id")
        by_agent.setdefault(agent, {}).setdefault(sess, []).append(otlp)

    resource_spans = []
    for agent, sessions in by_agent.items():
        scope_spans = []
        for _sess, otlp_spans in sessions.items():
            scope_spans.append({
                "scope": {"name": _SCOPE_NAME},
                "spans": otlp_spans,
            })
        resource_spans.append({
            "resource": {
                "attributes": [
                    {"key": "service.name", "value": _av("tool-usage-tracker")},
                    {"key": "gen_ai.agent.name", "value": _av(agent)},
                ]
            },
            "scopeSpans": scope_spans,
        })
    return {"resourceSpans": resource_spans}


def export(spans, endpoint="http://127.0.0.1:4318/v1/traces", timeout=5.0):
    """POSTet gemappte Spans als OTLP/JSON an einen lokalen Collector.

    Liefert ``True`` bei HTTP-2xx, sonst ``False``. Graceful-Fallback: ist der
    Collector nicht erreichbar (ConnectionRefused/Timeout/DNS/HTTP-Fehler),
    wird KEIN Fehler geworfen — Rueckgabe ``False``. So bleibt ein optionaler
    Export rein additiv und kann nie eine Analyse-Session abbrechen.
    """
    doc = build_resource_spans(spans)
    if not doc.get("resourceSpans"):
        # Nichts zu senden -> als Erfolg werten (kein Netzwerk noetig).
        return True
    payload = json.dumps(doc).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        return 200 <= exc.code < 300
    except Exception:
        # ConnectionRefused, Timeout, DNS, ungueltiger Endpoint, ...
        return False
