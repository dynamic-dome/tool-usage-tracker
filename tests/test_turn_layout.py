import json
import shutil
import subprocess
from pathlib import Path

import pytest

TEMPLATE = Path(__file__).resolve().parents[1] / "analysis" / "dashboard_template.html"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _extract(fn_name):
    text = TEMPLATE.read_text(encoding="utf-8")
    start = text.index("function " + fn_name)
    i = text.index("{", start)
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[start:j + 1]
    raise AssertionError("unbalanced braces for " + fn_name)


def _run_node(js):
    proc = subprocess.run(["node", "-"], input=js, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def _harness(body):
    return _extract("tsToMs") + "\n" + _extract("turnLayout") + "\n" + body


def test_turn_layout_sequential_spans_offset_increases():
    body = """
    var spans = [
      {ts_start:'2026-06-04T10:00:00.000Z', ts_end:'2026-06-04T10:00:00.100Z'},
      {ts_start:'2026-06-04T10:00:00.500Z', ts_end:'2026-06-04T10:00:00.600Z'}
    ];
    var out = turnLayout(spans);
    console.log(JSON.stringify([out[0].left, out[1].left, out[0].lane, out[1].lane]));
    """
    left0, left1, lane0, lane1 = json.loads(_run_node(_harness(body)))
    assert left0 == 0
    assert left1 > left0
    assert lane0 == 0 and lane1 == 0


def test_turn_layout_overlapping_spans_stack_in_lanes():
    body = """
    var spans = [
      {ts_start:'2026-06-04T10:00:00.000Z', ts_end:'2026-06-04T10:00:01.000Z'},
      {ts_start:'2026-06-04T10:00:00.200Z', ts_end:'2026-06-04T10:00:00.800Z'}
    ];
    var out = turnLayout(spans);
    console.log(JSON.stringify([out[0].lane, out[1].lane]));
    """
    lane0, lane1 = json.loads(_run_node(_harness(body)))
    assert {lane0, lane1} == {0, 1}


def test_turn_layout_zero_span_guard():
    body = """
    var spans = [
      {ts_start:'2026-06-04T10:00:00.000Z', ts_end:'2026-06-04T10:00:00.000Z'},
      {ts_start:'2026-06-04T10:00:00.000Z', ts_end:'2026-06-04T10:00:00.000Z'}
    ];
    var out = turnLayout(spans);
    console.log(JSON.stringify(out.map(function(o){return o.width;})));
    """
    widths = json.loads(_run_node(_harness(body)))
    assert all(w >= 0.5 for w in widths)


def test_turn_layout_orphan_without_ts_start_goes_end():
    body = """
    var spans = [
      {ts_start:'2026-06-04T10:00:00.000Z', ts_end:'2026-06-04T10:00:01.000Z'},
      {ts_start:null, ts_end:null}
    ];
    var out = turnLayout(spans);
    var orphan = out.filter(function(o){return !o.dated;})[0];
    console.log(JSON.stringify([orphan.dated, orphan.left >= 0]));
    """
    dated, leftOk = json.loads(_run_node(_harness(body)))
    assert dated is False and leftOk is True
