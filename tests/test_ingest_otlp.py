"""Tests fuer analysis/ingest_otlp.py (A-1 OTLP-Token/Kosten-Ingest, stdlib-only).

Deckt beide OTLP-Schreibweisen ab:
  - flaches console-Exporter-Format ({'descriptor':{'name':..}, 'dataPoints':[..]})
  - geschachteltes OTLP/JSON-Resource-Format ({'resourceMetrics':[...]})
Prueft Summierung pro session.id, Typ-Mapping der Token-Attribute, Kosten-
Aggregation, Robustheit gegen Muell und das No-Data-Verhalten.
"""
import importlib.util
import json
from pathlib import Path

MOD = Path(__file__).resolve().parents[1] / "analysis" / "ingest_otlp.py"
_spec = importlib.util.spec_from_file_location("ingest_otlp", MOD)
ing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ing)


def _console_token(sid, ttype, value, model="claude-sonnet-4"):
    return {
        "descriptor": {"name": "claude_code.token.usage"},
        "dataPoints": [
            {"attributes": {"session.id": sid, "type": ttype, "model": model},
             "value": value},
        ],
    }


def _console_cost(sid, value, model="claude-sonnet-4"):
    return {
        "descriptor": {"name": "claude_code.cost.usage"},
        "dataPoints": [
            {"attributes": {"session.id": sid, "model": model}, "value": value},
        ],
    }


def test_console_format_sums_tokens_and_cost_per_session():
    text = "\n".join(json.dumps(o) for o in [
        _console_token("sA", "input", 100),
        _console_token("sA", "output", 40),
        _console_token("sA", "cacheRead", 200),
        _console_cost("sA", 0.012),
    ])
    out = ing.parse_metrics(text)
    assert set(out) == {"sA"}
    rec = out["sA"]
    assert rec["input_tokens"] == 100
    assert rec["output_tokens"] == 40
    assert rec["cache_read_tokens"] == 200
    assert abs(rec["cost_usd"] - 0.012) < 1e-9


def test_counter_accumulates_across_multiple_datapoints():
    # Counter -> mehrere DataPoints derselben Session werden summiert
    text = "\n".join(json.dumps(o) for o in [
        _console_token("sB", "input", 50),
        _console_token("sB", "input", 25),
        _console_cost("sB", 0.001),
        _console_cost("sB", 0.002),
    ])
    out = ing.parse_metrics(text)
    assert out["sB"]["input_tokens"] == 75
    assert abs(out["sB"]["cost_usd"] - 0.003) < 1e-9


def test_multiple_sessions_kept_separate():
    text = "\n".join(json.dumps(o) for o in [
        _console_token("s1", "input", 10),
        _console_token("s2", "input", 999),
    ])
    out = ing.parse_metrics(text)
    assert out["s1"]["input_tokens"] == 10
    assert out["s2"]["input_tokens"] == 999


def test_otlp_json_resource_format():
    obj = {
        "resourceMetrics": [{
            "scopeMetrics": [{
                "metrics": [
                    {"name": "claude_code.token.usage",
                     "sum": {"dataPoints": [
                         {"attributes": [
                             {"key": "session.id", "value": {"stringValue": "sR"}},
                             {"key": "type", "value": {"stringValue": "output"}},
                         ], "asInt": "320"},
                     ]}},
                    {"name": "claude_code.cost.usage",
                     "sum": {"dataPoints": [
                         {"attributes": [
                             {"key": "session.id", "value": {"stringValue": "sR"}},
                         ], "asDouble": 0.05},
                     ]}},
                ],
            }],
        }],
    }
    out = ing.parse_metrics(json.dumps(obj))
    assert out["sR"]["output_tokens"] == 320
    assert abs(out["sR"]["cost_usd"] - 0.05) < 1e-9


def test_ignores_unrelated_metrics_and_garbage():
    text = (
        "garbage not json\n"
        + json.dumps({"descriptor": {"name": "some.other.metric"},
                      "dataPoints": [{"attributes": {"session.id": "sX"}, "value": 7}]})
        + "\n{ broken json here\n"
        + json.dumps(_console_token("sX", "input", 5))
    )
    out = ing.parse_metrics(text)
    # nur der token-Eintrag zaehlt, der fremde wird ignoriert
    assert out["sX"]["input_tokens"] == 5
    assert "cost_usd" not in out["sX"] or out["sX"].get("cost_usd", 0) == 0


def test_datapoint_without_session_id_skipped():
    text = json.dumps({
        "descriptor": {"name": "claude_code.token.usage"},
        "dataPoints": [{"attributes": {"type": "input"}, "value": 100}],
    })
    out = ing.parse_metrics(text)
    assert out == {}


def test_empty_input_returns_empty_dict():
    assert ing.parse_metrics("") == {}
    assert ing.parse_metrics("   \n\t ") == {}


def test_unknown_token_type_ignored():
    text = json.dumps(_console_token("sQ", "weirdtype", 123))
    out = ing.parse_metrics(text)
    # unbekannter type -> kein Feld gesetzt
    assert out.get("sQ", {}) == {}


def test_main_writes_output_file(tmp_path):
    src = tmp_path / "otlp.jsonl"
    src.write_text("\n".join(json.dumps(o) for o in [
        _console_token("sMain", "input", 11),
        _console_cost("sMain", 0.009),
    ]), encoding="utf-8")
    out = tmp_path / "usage_by_session.json"
    rc = ing.main([str(src), str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["sMain"]["input_tokens"] == 11
    assert abs(data["sMain"]["cost_usd"] - 0.009) < 1e-9
