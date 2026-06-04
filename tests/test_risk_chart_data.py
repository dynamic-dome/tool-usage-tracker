"""Tests fuer die reine Risk-Doughnut-Datenfunktion `riskChartData(risk)` im
Dashboard-JS (UX-Fix: 'unknown' wird im Doughnut ausgeblendet, damit die
sicherheitsrelevanten Stufen high/medium sichtbar werden).

Die Funktion ist bewusst DOM-/Chart.js-frei, damit sie isoliert in Node geprueft
werden kann — ohne Browser, ohne Server. Der Vertrag:
- labels/vals enthalten KEIN 'unknown'
- Reihenfolge high > medium > low (RISK_ORDER ohne unknown)
- `hidden` = Anzahl der unknown-Spans (fuer die Fussnote)
- nur vorhandene Stufen erscheinen
"""
import importlib.util
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / "analysis" / "dashboard_smoke.py"
SERVER = ROOT / "analysis" / "server.py"

_spec = importlib.util.spec_from_file_location("dashboard_smoke", SMOKE)
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

_server_spec = importlib.util.spec_from_file_location("server", SERVER)
server = importlib.util.module_from_spec(_server_spec)
_server_spec.loader.exec_module(server)


def _extract_fn(js_body, name):
    """Schneidet eine top-level `function name(...){ ... }` per Brace-Matching
    aus dem JS-Body. Zieht zusaetzlich die von riskChartData benoetigte
    RISK_ORDER-Konstante mit, damit die Funktion isoliert lauffaehig ist."""
    start = js_body.index("function " + name)
    i = js_body.index("{", start)
    depth = 0
    for j in range(i, len(js_body)):
        if js_body[j] == "{":
            depth += 1
        elif js_body[j] == "}":
            depth -= 1
            if depth == 0:
                fn = js_body[start:j + 1]
                break
    else:
        raise AssertionError("unbalanced braces for " + name)
    order = re.search(r"var RISK_ORDER = \[[^\]]*\];", js_body)
    prefix = (order.group(0) + "\n") if order else ""
    return prefix + fn


def _eval_risk(risk, tmp_path):
    """Laedt das Dashboard-JS in Node, ruft riskChartData(risk) und gibt das
    Ergebnis als dict zurueck. Skip, wenn node fehlt.

    Das JS wird in eine .js-Datei geschrieben und via `node <file>` ausgefuehrt,
    NICHT als `node -e <arg>` — der gesamte Script-Body sprengt sonst das
    Windows-Kommandozeilen-Limit (WinError 206; vgl. globale Regel: langen
    Input an Node ueber Datei/stdin, nicht als CLI-Arg)."""
    if not shutil.which("node"):
        pytest.skip("node is not available")
    scripts = smoke.extract_script_blocks(server.index_html())
    js_body = "\n".join(scripts)
    fn = _extract_fn(js_body, "riskChartData")
    # Nur die reine Funktion ausfuehren — der Script-Top-Level verdrahtet den
    # DOM (getElementById(...).addEventListener) und crasht in nacktem Node;
    # riskChartData() selbst ist global-frei und exakt das, was wir testen.
    harness = (
        fn
        + "\nvar __out = JSON.stringify(riskChartData("
        + json.dumps(risk)
        + "));\nprocess.stdout.write(__out);\n"
    )
    script_file = tmp_path / "risk_harness.js"
    script_file.write_text(harness, encoding="utf-8")
    result = subprocess.run(
        ["node", str(script_file)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_unknown_excluded_from_labels_and_values(tmp_path):
    out = _eval_risk({"unknown": 3893, "low": 1909, "medium": 30, "high": 5}, tmp_path)
    assert "unknown" not in out["labels"]
    assert out["labels"] == ["high", "medium", "low"]
    assert out["values"] == [5, 30, 1909]


def test_hidden_count_equals_unknown(tmp_path):
    out = _eval_risk({"unknown": 3893, "low": 1909, "medium": 30, "high": 5}, tmp_path)
    assert out["hidden"] == 3893


def test_only_present_levels_appear(tmp_path):
    out = _eval_risk({"unknown": 10, "low": 4}, tmp_path)
    assert out["labels"] == ["low"]
    assert out["values"] == [4]
    assert out["hidden"] == 10


def test_no_unknown_means_zero_hidden(tmp_path):
    out = _eval_risk({"high": 2, "low": 7}, tmp_path)
    assert out["labels"] == ["high", "low"]
    assert out["hidden"] == 0


def test_empty_risk_is_safe(tmp_path):
    out = _eval_risk({}, tmp_path)
    assert out["labels"] == []
    assert out["values"] == []
    assert out["hidden"] == 0
