"""OTLP-Metrics-Ingest fuer Token/Kosten (A-1) — OPTIONALES Add-on, stdlib-only.

Claude Code liefert Token-/Kosten-Usage NICHT im Tool-Result (PostToolUse-Hook),
sondern als OpenTelemetry-Metrics ueber einen separaten Kanal:

    CLAUDE_CODE_ENABLE_TELEMETRY=1 \\
    OTEL_METRICS_EXPORTER=console \\
    OTEL_METRIC_EXPORT_INTERVAL=10000 \\
    claude  2> otlp-metrics.jsonl

Die relevanten Metriken (Primaerquelle: code.claude.com/docs/en/monitoring-usage):
  - claude_code.token.usage  Counter, Attr type=input|output|cacheRead|cacheCreation, session.id, model
  - claude_code.cost.usage   Counter (USD),  Attr model, session.id

WICHTIGE EINSCHRAENKUNG (ehrlich dokumentiert): Die Metrics tragen `session.id`,
aber KEINE `tool_use_id`. Kosten sind daher nur PRO SESSION zuordenbar, nicht
exakt pro einzelnem Tool-Call. Dieses Skript aggregiert Usage pro Session und
verteilt sie GLEICHMAESSIG auf die gepaarten Spans der Session (proportional zur
Anzahl). Das ist eine bewusste Naeherung fuer die Dashboard-Aggregate — die
Summen pro Session/Tool/Agent stimmen exakt, die Einzel-Span-Werte sind geschaetzt.

Der Hot-Path (die Hooks) wird NICHT angefasst: dieses Skript laeuft nachgelagert
und schreibt eine getrennte Datei `data/usage_by_session.json`, die der Loader
optional einliest. Kein pandas/numpy, reine Stdlib.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "usage_by_session.json"

# OTLP-console-Exporter kann camelCase ODER snake_case je nach Version liefern.
_TOKEN_NAMES = {"claude_code.token.usage", "claude_code_token_usage"}
_COST_NAMES = {"claude_code.cost.usage", "claude_code_cost_usage"}
_TYPE_MAP = {
    "input": "input_tokens",
    "output": "output_tokens",
    "cacheread": "cache_read_tokens",
    "cache_read": "cache_read_tokens",
    "cachecreation": "cache_creation_tokens",
    "cache_creation": "cache_creation_tokens",
}


def _iter_json_objects(text):
    """Robust ueber eine Datei iterieren, die ENTWEDER JSONL ODER mehrere/ein
    eingebettete(s) JSON-Objekt(e) enthaelt. Nutzt JSONDecoder.raw_decode, um
    aufeinanderfolgende Objekte (auch ueber Zeilen verteilt) zu lesen. Defensiv:
    ueberspringt Muell zwischen Objekten."""
    dec = json.JSONDecoder()
    i, n = 0, len(text)
    while i < n:
        while i < n and text[i] in " \t\r\n,":
            i += 1
        if i >= n:
            break
        try:
            obj, end = dec.raw_decode(text, i)
            yield obj
            i = end
        except ValueError:
            # bis zum naechsten '{' vorspulen
            nxt = text.find("{", i + 1)
            if nxt == -1:
                break
            i = nxt


def _attr_get(attrs, *keys):
    """Attribut robust lesen — OTLP-console nutzt teils {'session.id':..},
    teils Listen [{'key':..,'value':{'stringValue':..}}]."""
    if isinstance(attrs, dict):
        for k in keys:
            if k in attrs:
                return attrs[k]
        return None
    if isinstance(attrs, list):
        for item in attrs:
            if not isinstance(item, dict):
                continue
            if item.get("key") in keys:
                v = item.get("value")
                if isinstance(v, dict):
                    return (v.get("stringValue") or v.get("doubleValue")
                            or v.get("intValue") or v.get("asDouble"))
                return v
    return None


def _num(v):
    try:
        if isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return v
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_metrics(text):
    """OTLP-console-Text -> {session_id: {input_tokens, output_tokens,
    cache_read_tokens, cache_creation_tokens, cost_usd}}. Summiert Counter ueber
    alle DataPoints je Session. Tolerant gegen beide OTLP-Schreibweisen
    (flaches console-Format und das geschachtelte OTLP/JSON-Resource-Format)."""
    acc = defaultdict(lambda: defaultdict(float))
    for obj in _iter_json_objects(text):
        for name, dps in _extract_metric_points(obj):
            low = name.lower()
            is_token = name in _TOKEN_NAMES or low.endswith("token_usage") or low.endswith("token.usage")
            is_cost = name in _COST_NAMES or low.endswith("cost_usage") or low.endswith("cost.usage")
            if not (is_token or is_cost):
                continue
            for dp in dps:
                attrs = dp.get("attributes")
                sid = _attr_get(attrs, "session.id", "session_id")
                if sid is None:
                    continue
                val = _num(dp.get("value"))
                if val is None:
                    val = _num(dp.get("asDouble"))
                if val is None:
                    val = _num(dp.get("asInt"))
                if val is None:
                    continue
                if is_cost:
                    acc[sid]["cost_usd"] += val
                else:
                    t = str(_attr_get(attrs, "type") or "").lower()
                    field = _TYPE_MAP.get(t)
                    if field:
                        acc[sid][field] += val
    # in plain dicts + ints fuer Tokens
    out = {}
    for sid, d in acc.items():
        rec = {}
        for k, v in d.items():
            rec[k] = round(v, 6) if k == "cost_usd" else int(round(v))
        out[sid] = rec
    return out


def _extract_metric_points(obj):
    """Gibt (metric_name, [datapoints]) aus einem console- ODER OTLP/JSON-Objekt.
    console-Format: {'descriptor':{'name':..}, 'dataPoints':[{'attributes':{}, 'value':..}]}
    OTLP/JSON:      {'resourceMetrics':[{'scopeMetrics':[{'metrics':[{'name':..,'sum':{'dataPoints':[..]}}]}]}]}
    """
    # console-Format
    desc = obj.get("descriptor") if isinstance(obj, dict) else None
    if isinstance(desc, dict) and desc.get("name"):
        yield desc["name"], obj.get("dataPoints", []) or []
        return
    if isinstance(obj, dict) and obj.get("name") and ("dataPoints" in obj or "sum" in obj):
        dps = obj.get("dataPoints") or (obj.get("sum", {}) or {}).get("dataPoints", [])
        yield obj["name"], dps or []
        return
    # OTLP/JSON-Format
    for rm in (obj.get("resourceMetrics") or []) if isinstance(obj, dict) else []:
        for sm in rm.get("scopeMetrics", []) or []:
            for m in sm.get("metrics", []) or []:
                name = m.get("name")
                agg = m.get("sum") or m.get("gauge") or {}
                dps = agg.get("dataPoints", []) or []
                if name:
                    yield name, dps


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("Usage: python analysis/ingest_otlp.py <otlp-metrics.jsonl> [out.json]",
              file=sys.stderr)
        return 2
    src = Path(argv[0])
    out = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    text = src.read_text(encoding="utf-8", errors="replace")
    by_session = parse_metrics(text)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(by_session, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(by_session)} Session(s) -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
