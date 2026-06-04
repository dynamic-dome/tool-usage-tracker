# Trace-Waterfall pro Turn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Den Timeline-Tab des Live-Dashboards zu einem Trace-Waterfall ausbauen, der Tool-Spans pro Turn (Gap-Heuristik) auf einer echten Zeitachse darstellt.

**Architecture:** Turn-Erkennung als reine Python-Funktionen in `analysis/_load.py` (`compute_turn_gap_threshold` global-adaptiv + `assign_turns`), aufgerufen in `spans_payload` (`analysis/server.py`). Das JS in `analysis/dashboard_template.html` rendert die Turn-Gruppen mit echter Zeitachse und vertikalem Stapeln; eine reine `turnLayout`-Helferfunktion ist isoliert in Node testbar.

**Tech Stack:** Python-Stdlib (kein pandas), Chart.js inline, Vanilla-JS, Dark-Theme/Command-Center.

---

## Kontext für den Implementierer (lesen, bevor du startest)

- **Nur der Live-Server hat einen Timeline-Tab.** `analysis/dashboard.py` (statisches HTML) hat ein eigenes, anderes Template ohne Timeline — es wird hier NICHT angefasst. B-1 betrifft ausschließlich `analysis/server.py` + `analysis/dashboard_template.html`.
- **Span-Datenstruktur** (aus `pair_events` in `_load.py`, ein dict pro Span): relevante Felder für B-1:
  - `session_id` (str), `ts_start` (str `"%Y-%m-%dT%H:%M:%S.%fZ"` oder `None`), `ts_end` (str oder `None`), `duration_ms` (int oder `None`), `tool_name`, `summary`, `ok` (`True`/`False`/`None`), `error`, `risk`, `mutating`, `cwd`.
  - Ungepaarte Spans haben `ts_start` ODER `ts_end` `None` (Orphans).
- **Zeitstempel-Parsing** gibt es schon: `_duration_ms(start_ts, end_ts)` in `_load.py:50` nutzt `datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ")`. Für Gaps brauchst du einen ms-Wert pro Zeitstempel — baue einen kleinen Helfer `_ts_to_ms(ts)` analog.
- **Teststil:** Tests laden den Loader per `from _load import ...` (siehe `tests/test_load.py`). Lauf-Kommando immer `python -X utf8 -m pytest -q tests/...` (UTF-8-Flag ist Pflicht auf Windows).
- **JS-Test-Muster (L4):** ganzes Modul via `node -e` sprengt das Windows-Arg-Limit (WinError 206) UND der Template-Top-Level verdrahtet DOM (crasht in nacktem Node). Daher: die reine Funktion per Brace-Matching aus dem Template extrahieren, in eine temp-`.js` schreiben, `module.exports`-Zeile anhängen, mit `node <file>` ausführen. Vorbild: `tests/test_risk_chart_data.py`.
- **Commit-Konvention:** Co-Author-Trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Chirurgisch stagen (nur die genannten Pfade), NICHT `.agent-memory/` mitcommitten.

## File Structure

| Datei | Verantwortung | Aktion |
|---|---|---|
| `analysis/_load.py` | `_ts_to_ms`, `compute_turn_gap_threshold`, `assign_turns` | Modify (anhängen) |
| `analysis/server.py` | `assign_turns(spans, threshold)` in `spans_payload`, `turn_gap_ms` ins Payload | Modify (`spans_payload`, ~Z.52-64) |
| `analysis/dashboard_template.html` | `turnLayout` (rein) + `renderTimeline`-Umbau + CSS | Modify (CSS ~Z.38-44, `renderTimeline` Z.346-409) |
| `tests/test_turns.py` | Python-Tests für Schwelle + Turn-Zuweisung | Create |
| `tests/test_turn_layout.py` | Node-isolierter Test für `turnLayout` | Create |
| `docs/CAPABILITIES.md`, `HOW-TO-USE.md` | Timeline→Waterfall-Beschreibung | Modify |

---

## Task 1: `_ts_to_ms` — Zeitstempel zu Millisekunden

**Files:**
- Modify: `analysis/_load.py` (nach `_duration_ms`, ~Z.58)
- Test: `tests/test_turns.py`

- [ ] **Step 1: Testdatei mit erstem Test anlegen**

Create `tests/test_turns.py`:

```python
import importlib.util
from pathlib import Path

_LOAD = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
_spec = importlib.util.spec_from_file_location("_load", _LOAD)
load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(load)


def test_ts_to_ms_parses_iso_z():
    a = load._ts_to_ms("2026-06-04T10:00:00.000Z")
    b = load._ts_to_ms("2026-06-04T10:00:01.500Z")
    assert b - a == 1500


def test_ts_to_ms_returns_none_on_garbage():
    assert load._ts_to_ms("not-a-ts") is None
    assert load._ts_to_ms("") is None
    assert load._ts_to_ms(None) is None
```

- [ ] **Step 2: Test laufen — muss fehlschlagen**

Run: `python -X utf8 -m pytest -q tests/test_turns.py -v`
Expected: FAIL mit `AttributeError: module '_load' has no attribute '_ts_to_ms'`

- [ ] **Step 3: `_ts_to_ms` implementieren**

In `analysis/_load.py` direkt nach `_duration_ms` (nach Z.58) einfügen:

```python
def _ts_to_ms(ts):
    """ISO-Zeitstempel ('%Y-%m-%dT%H:%M:%S.%fZ') -> Millisekunden (float, ab
    Epoch). None bei unparsebarer/leerer Eingabe."""
    from datetime import datetime, timezone
    if not ts:
        return None
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        return dt.timestamp() * 1000.0
    except Exception:
        return None
```

- [ ] **Step 4: Test laufen — muss bestehen**

Run: `python -X utf8 -m pytest -q tests/test_turns.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add analysis/_load.py tests/test_turns.py
git commit -m "feat(load): _ts_to_ms Helfer fuer Turn-Gap-Berechnung

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: `compute_turn_gap_threshold` — global-adaptive Gap-Schwelle

**Files:**
- Modify: `analysis/_load.py` (nach `_ts_to_ms`)
- Test: `tests/test_turns.py`

- [ ] **Step 1: Failing-Tests schreiben**

Anhängen an `tests/test_turns.py`:

```python
def _span(sid, start_ms, dur_ms):
    # Minimaler Span mit ts_start/ts_end aus ms-Offsets (Basis 2026-06-04T10:00:00Z)
    base = load._ts_to_ms("2026-06-04T10:00:00.000Z")
    from datetime import datetime, timezone
    def ms_to_ts(ms):
        dt = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(ms % 1000):03d}Z"
    s = base + start_ms
    return {"session_id": sid, "ts_start": ms_to_ts(s),
            "ts_end": ms_to_ts(s + dur_ms), "duration_ms": dur_ms}


def test_threshold_fallback_when_too_few_gaps():
    # < 8 Gaps -> fester 30000ms-Default
    spans = [_span("a", 0, 100), _span("a", 200, 100)]  # 1 Gap
    assert load.compute_turn_gap_threshold(spans) == 30000


def test_threshold_fallback_on_empty():
    assert load.compute_turn_gap_threshold([]) == 30000


def test_threshold_adaptive_with_enough_gaps():
    # 9 Spans derselben Session, je 100ms Gap -> 8 Gaps, alle gleich 100
    # median=100, MAD=0 -> threshold=100, aber Klammer min 5000 -> 5000
    spans = [_span("a", i * 200, 100) for i in range(9)]
    assert load.compute_turn_gap_threshold(spans) == 5000


def test_threshold_clamped_to_max():
    # 8 Gaps von je 300000ms (5 min) -> median gross -> Klammer max 120000
    spans = [_span("a", i * 600000, 100) for i in range(9)]
    assert load.compute_turn_gap_threshold(spans) == 120000


def test_threshold_ignores_cross_session_gaps():
    # Gaps werden NUR innerhalb derselben Session gezaehlt. Zwei Sessions mit je
    # 1 Gap = 2 Gaps insgesamt (<8) -> Fallback, NICHT die Luecke zwischen den
    # Sessions als Gap zaehlen.
    spans = ([_span("a", 0, 100), _span("a", 200, 100)]
             + [_span("b", 0, 100), _span("b", 200, 100)])
    assert load.compute_turn_gap_threshold(spans) == 30000
```

- [ ] **Step 2: Tests laufen — müssen fehlschlagen**

Run: `python -X utf8 -m pytest -q tests/test_turns.py -k threshold -v`
Expected: FAIL mit `AttributeError: ... 'compute_turn_gap_threshold'`

- [ ] **Step 3: Implementieren**

In `analysis/_load.py` nach `_ts_to_ms` einfügen:

```python
def _intra_session_gaps(spans):
    """Alle Inter-Span-Gaps (ms) innerhalb je einer Session. Ein Gap ist die
    Pause zwischen ts_end eines Spans und ts_start des chronologisch naechsten
    DERSELBEN Session. Nur Spans mit gueltigem ts_start; negative Gaps (Ueber-
    lappung) werden auf 0 geklammert."""
    from collections import defaultdict
    by_sid = defaultdict(list)
    for s in spans:
        start = _ts_to_ms(s.get("ts_start"))
        if start is None:
            continue
        end = _ts_to_ms(s.get("ts_end"))
        by_sid[s.get("session_id")].append((start, end if end is not None else start))
    gaps = []
    for items in by_sid.values():
        items.sort(key=lambda t: t[0])
        for (s_prev, e_prev), (s_next, _e) in zip(items, items[1:]):
            gaps.append(max(0.0, s_next - e_prev))
    return gaps


def compute_turn_gap_threshold(spans):
    """Global-adaptive Turn-Gap-Schwelle (ms) ueber den ganzen View. Schwelle =
    median + 3*MAD aller Intra-Session-Gaps, hart geklammert auf [5000, 120000].
    Fallback 30000, wenn < 8 Gaps (zu wenig Daten fuer stabile Schaetzung).
    Deterministisch."""
    gaps = _intra_session_gaps(spans)
    if len(gaps) < 8:
        return 30000
    gaps.sort()
    n = len(gaps)
    median = gaps[n // 2] if n % 2 else (gaps[n // 2 - 1] + gaps[n // 2]) / 2.0
    devs = sorted(abs(g - median) for g in gaps)
    mad = devs[n // 2] if n % 2 else (devs[n // 2 - 1] + devs[n // 2]) / 2.0
    threshold = median + 3.0 * mad
    return int(max(5000, min(120000, threshold)))
```

- [ ] **Step 4: Tests laufen — müssen bestehen**

Run: `python -X utf8 -m pytest -q tests/test_turns.py -k threshold -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add analysis/_load.py tests/test_turns.py
git commit -m "feat(load): compute_turn_gap_threshold (global-adaptiv, geklammert)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `assign_turns` — Turn-Index pro Span

**Files:**
- Modify: `analysis/_load.py` (nach `compute_turn_gap_threshold`)
- Test: `tests/test_turns.py`

- [ ] **Step 1: Failing-Tests schreiben**

Anhängen an `tests/test_turns.py`:

```python
def test_assign_turns_single_burst_is_one_turn():
    # Alle Gaps < Schwelle -> ein einziger Turn (index 0)
    spans = [_span("a", 0, 100), _span("a", 200, 100), _span("a", 400, 100)]
    out = load.assign_turns(spans, threshold=30000)
    assert [s["turn_index"] for s in out] == [0, 0, 0]


def test_assign_turns_splits_on_large_gap():
    # Gap zwischen Span 2 und 3 = 60000ms > Schwelle 30000 -> neuer Turn
    spans = [_span("a", 0, 100), _span("a", 200, 100), _span("a", 60300, 100)]
    out = load.assign_turns(spans, threshold=30000)
    assert [s["turn_index"] for s in out] == [0, 0, 1]


def test_assign_turns_independent_per_session():
    spans = [_span("a", 0, 100), _span("a", 60300, 100),
             _span("b", 0, 100)]
    out = load.assign_turns(spans, threshold=30000)
    by_sid = {}
    for s in out:
        by_sid.setdefault(s["session_id"], []).append(s["turn_index"])
    assert by_sid["a"] == [0, 1]
    assert by_sid["b"] == [0]  # eigene Zaehlung ab 0


def test_assign_turns_orphans_without_ts_start_go_last():
    # Ein Span ohne ts_start landet im letzten Turn seiner Session
    spans = [_span("a", 0, 100),
             {"session_id": "a", "ts_start": None, "ts_end": None,
              "duration_ms": None}]
    out = load.assign_turns(spans, threshold=30000)
    orphan = [s for s in out if s.get("ts_start") is None][0]
    real = [s for s in out if s.get("ts_start") is not None][0]
    assert orphan["turn_index"] == real["turn_index"]


def test_assign_turns_robust_to_unsorted_input():
    spans = [_span("a", 400, 100), _span("a", 0, 100), _span("a", 200, 100)]
    out = load.assign_turns(spans, threshold=30000)
    # Reihenfolge der Rueckgabe ist egal; entscheidend: alle im selben Turn 0
    assert all(s["turn_index"] == 0 for s in out)


def test_assign_turns_is_deterministic():
    spans = [_span("a", 0, 100), _span("a", 60300, 100)]
    a = [s["turn_index"] for s in load.assign_turns(spans, 30000)]
    b = [s["turn_index"] for s in load.assign_turns(spans, 30000)]
    assert a == b
```

- [ ] **Step 2: Tests laufen — müssen fehlschlagen**

Run: `python -X utf8 -m pytest -q tests/test_turns.py -k assign -v`
Expected: FAIL mit `AttributeError: ... 'assign_turns'`

- [ ] **Step 3: Implementieren**

In `analysis/_load.py` nach `compute_turn_gap_threshold` einfügen:

```python
def assign_turns(spans, threshold):
    """Setzt auf jedem Span ein session-lokales `turn_index` (0-basiert). Neuer
    Turn, sobald der Gap zum vorherigen Span derselben Session > threshold (ms).
    Spans ohne ts_start (Orphans) landen im LETZTEN Turn ihrer Session (bzw.
    Turn 0, wenn die Session keinen datierten Span hat). Mutiert die Spans in
    place und gibt die Liste zurueck."""
    from collections import defaultdict
    by_sid = defaultdict(list)
    orphans = defaultdict(list)
    for s in spans:
        if _ts_to_ms(s.get("ts_start")) is None:
            orphans[s.get("session_id")].append(s)
        else:
            by_sid[s.get("session_id")].append(s)
    for sid, items in by_sid.items():
        items.sort(key=lambda s: _ts_to_ms(s.get("ts_start")))
        turn = 0
        prev_end = None
        for s in items:
            start = _ts_to_ms(s.get("ts_start"))
            end = _ts_to_ms(s.get("ts_end"))
            if prev_end is not None and (start - prev_end) > threshold:
                turn += 1
            s["turn_index"] = turn
            prev_end = end if end is not None else start
    for sid, items in orphans.items():
        last_turn = by_sid[sid][-1]["turn_index"] if by_sid.get(sid) else 0
        for s in items:
            s["turn_index"] = last_turn
    return spans
```

- [ ] **Step 4: Tests laufen — müssen bestehen**

Run: `python -X utf8 -m pytest -q tests/test_turns.py -k assign -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Volle Turn-Suite + Regression `test_load.py`**

Run: `python -X utf8 -m pytest -q tests/test_turns.py tests/test_load.py`
Expected: PASS (alle grün, keine Regression im Loader)

- [ ] **Step 6: Commit**

```bash
git add analysis/_load.py tests/test_turns.py
git commit -m "feat(load): assign_turns setzt session-lokalen turn_index per Gap-Heuristik

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Server reicht Turns durch

**Files:**
- Modify: `analysis/server.py` (`spans_payload`, Z.42-64)
- Test: `tests/test_server.py` (anhängen)

- [ ] **Step 1: Failing-Test schreiben**

Erst kurz `tests/test_server.py` ansehen, wie `spans_payload` dort getestet wird (Importstil, evtl. tmp-events-Fixture). Dann analog anhängen:

```python
def test_spans_payload_assigns_turn_index_and_threshold(tmp_path):
    # Zwei Spans derselben Session mit kleinem Gap -> beide turn_index 0,
    # turn_gap_ms im Payload vorhanden.
    import json as _json
    ev = tmp_path / "ev.jsonl"
    rows = [
        {"phase": "pre", "session_id": "s", "tool_use_id": "t1",
         "tool_name": "Read", "ts_utc": "2026-06-04T10:00:00.000Z",
         "cwd": "x", "project": "p"},
        {"phase": "post", "session_id": "s", "tool_use_id": "t1",
         "tool_name": "Read", "ts_utc": "2026-06-04T10:00:00.100Z", "ok": True},
    ]
    ev.write_text("\n".join(_json.dumps(r) for r in rows), encoding="utf-8")
    payload = server.spans_payload(str(ev), {})
    assert "turn_gap_ms" in payload
    assert all("turn_index" in s for s in payload["spans"] if s.get("ts_start"))
```

(Importzeile `import server` / `from analysis import server` an den bestehenden Stil in `tests/test_server.py` anpassen.)

- [ ] **Step 2: Test laufen — muss fehlschlagen**

Run: `python -X utf8 -m pytest -q tests/test_server.py -k turn_index -v`
Expected: FAIL mit `KeyError: 'turn_gap_ms'` (oder fehlendem `turn_index`)

- [ ] **Step 3: `spans_payload` erweitern**

In `analysis/server.py`: Import-Zeile Z.13-14 um die neuen Funktionen ergänzen:

```python
from _load import (load_events, pair_events, pairing_summary, success_rate_by,
                   duration_stats_by, path_activity, classification_breakdown,
                   compute_turn_gap_threshold, assign_turns)
```

Dann in `spans_payload` direkt nach `spans = pair_events(evs)` (Z.48) einfügen:

```python
    turn_gap_ms = compute_turn_gap_threshold(spans)
    assign_turns(spans, turn_gap_ms)
```

Und im Rückgabe-dict (nach `"spans": spans,`) ergänzen:

```python
        "turn_gap_ms": turn_gap_ms,
```

- [ ] **Step 4: Test laufen — muss bestehen**

Run: `python -X utf8 -m pytest -q tests/test_server.py -k turn_index -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add analysis/server.py tests/test_server.py
git commit -m "feat(server): spans_payload weist turn_index zu + liefert turn_gap_ms

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `turnLayout` — reine Layout-Funktion im Template (Node-getestet)

Diese Funktion berechnet aus den Spans EINES Turns die Pixel-Geometrie: pro Span
`left`/`width` (%) auf der Turn-Zeitachse und die `lane` (Stapelzeile) für
gleichzeitige Spans. Sie ist rein (keine DOM-Zugriffe) und wird isoliert getestet.

**Files:**
- Modify: `analysis/dashboard_template.html` (neue Funktion vor `renderTimeline`, ~Z.345)
- Test: `tests/test_turn_layout.py` (Create)

- [ ] **Step 1: `turnLayout` ins Template einfügen**

In `analysis/dashboard_template.html` unmittelbar vor `function renderTimeline(data){` (Z.346) einfügen:

```javascript
// Reine Layout-Funktion fuer EINEN Turn: berechnet pro Span left/width (% der
// Turn-Breite) anhand des Offsets ab Turn-Start, und eine lane (0-basierte
// Stapelzeile) fuer zeitlich ueberlappende Spans. Kein DOM-Zugriff -> isoliert
// in Node testbar (L4-Muster). tsToMs: ISO-Z -> ms oder null.
function tsToMs(ts){
  if (!ts) return null;
  var m = Date.parse(ts);
  return isNaN(m) ? null : m;
}
function turnLayout(spans){
  // Sortiere chronologisch; Spans ohne ts_start ans Ende.
  var sorted = spans.slice().sort(function(a, b){
    var ta = tsToMs(a.ts_start), tb = tsToMs(b.ts_start);
    if (ta === null && tb === null) return 0;
    if (ta === null) return 1;
    if (tb === null) return -1;
    return ta - tb;
  });
  var starts = sorted.map(function(s){ return tsToMs(s.ts_start); }).filter(function(v){ return v !== null; });
  var ends = sorted.map(function(s){
    var e = tsToMs(s.ts_end); var st = tsToMs(s.ts_start);
    return e !== null ? e : st;
  }).filter(function(v){ return v !== null; });
  var turnStart = starts.length ? Math.min.apply(null, starts) : 0;
  var turnEnd = ends.length ? Math.max.apply(null, ends) : turnStart;
  var span = turnEnd - turnStart;
  if (span <= 0) span = 1;  // Division-Guard (alle gleichzeitig / Nulldauer)
  var laneEnds = [];  // pro lane das bisher belegte Ende (ms)
  var MINW_PCT = 0.5;
  return sorted.map(function(s){
    var st = tsToMs(s.ts_start);
    var en = tsToMs(s.ts_end);
    var dated = st !== null;
    var startMs = dated ? st : turnEnd;       // Orphan -> ans Ende
    var endMs = (en !== null) ? en : startMs;
    var left = ((startMs - turnStart) / span) * 100;
    var width = Math.max(MINW_PCT, ((endMs - startMs) / span) * 100);
    // lane: erste freie Stapelzeile, deren letztes Ende <= startMs
    var lane = 0;
    while (lane < laneEnds.length && laneEnds[lane] > startMs) lane++;
    laneEnds[lane] = endMs;
    return { span: s, left: left, width: width, lane: lane, dated: dated };
  });
}
```

- [ ] **Step 2: Node-isolierten Test schreiben**

Erst `tests/test_risk_chart_data.py` als Vorbild ansehen (wie es die Funktion per Brace-Matching extrahiert + in Node fährt). Dann `tests/test_turn_layout.py` analog:

```python
import re
import subprocess
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "analysis" / "dashboard_template.html"


def _extract(fn_name):
    text = TEMPLATE.read_text(encoding="utf-8")
    start = text.index("function " + fn_name)
    # Brace-Matching ab der ersten {
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
    # tsToMs + turnLayout zusammen extrahieren (turnLayout ruft tsToMs)
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
    res = _run_node(_harness(body))
    import json
    left0, left1, lane0, lane1 = json.loads(res)
    assert left0 == 0
    assert left1 > left0      # spaeterer Span weiter rechts
    assert lane0 == 0 and lane1 == 0   # nicht ueberlappend -> selbe lane


def test_turn_layout_overlapping_spans_stack_in_lanes():
    body = """
    var spans = [
      {ts_start:'2026-06-04T10:00:00.000Z', ts_end:'2026-06-04T10:00:01.000Z'},
      {ts_start:'2026-06-04T10:00:00.200Z', ts_end:'2026-06-04T10:00:00.800Z'}
    ];
    var out = turnLayout(spans);
    console.log(JSON.stringify([out[0].lane, out[1].lane]));
    """
    res = _run_node(_harness(body))
    import json
    lane0, lane1 = json.loads(res)
    assert {lane0, lane1} == {0, 1}   # ueberlappend -> verschiedene lanes


def test_turn_layout_zero_span_guard():
    # Alle Spans gleichzeitig & Nulldauer -> kein Crash, width >= MINW
    body = """
    var spans = [
      {ts_start:'2026-06-04T10:00:00.000Z', ts_end:'2026-06-04T10:00:00.000Z'},
      {ts_start:'2026-06-04T10:00:00.000Z', ts_end:'2026-06-04T10:00:00.000Z'}
    ];
    var out = turnLayout(spans);
    console.log(JSON.stringify(out.map(function(o){return o.width;})));
    """
    res = _run_node(_harness(body))
    import json
    widths = json.loads(res)
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
    res = _run_node(_harness(body))
    import json
    dated, leftOk = json.loads(res)
    assert dated is False and leftOk is True
```

- [ ] **Step 3: Tests laufen — müssen bestehen**

Run: `python -X utf8 -m pytest -q tests/test_turn_layout.py -v`
Expected: PASS (4 passed). Falls `node` fehlt: Test überspringt analog `test_risk_chart_data.py` — den dortigen Skip-Mechanismus übernehmen (z.B. `pytest.importorskip` bzw. `shutil.which("node")`-Guard).

- [ ] **Step 4: Commit**

```bash
git add analysis/dashboard_template.html tests/test_turn_layout.py
git commit -m "feat(dashboard): turnLayout reine Zeitachsen-/Lane-Geometrie (Node-getestet)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `renderTimeline` zum Turn-Waterfall umbauen + CSS

**Files:**
- Modify: `analysis/dashboard_template.html` — CSS (Z.38-44 erweitern), `renderTimeline` (Z.346-409 ersetzen)

- [ ] **Step 1: CSS für Turn-Container + Track + absolute Balken ergänzen**

In `analysis/dashboard_template.html` nach Z.44 (`.tl-bar.open{...}`) einfügen:

```css
.tl-turn{margin:0 0 10px;border:1px solid var(--border);border-radius:8px;padding:8px 10px;background:rgba(255,255,255,.02)}
.tl-turn-head{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--fg);opacity:.7;margin-bottom:6px}
.tl-turn-head .idx{color:var(--accent);opacity:1}
.tl-track{position:relative;width:100%}
.tl-track .tl-bar{position:absolute;top:0;min-width:2px}
.tl-lane{position:relative;height:26px;margin-bottom:3px}
```

- [ ] **Step 2: `renderTimeline` ersetzen**

Die bestehende Funktion `function renderTimeline(data){ ... }` (Z.346 bis zur schließenden `}` bei Z.409) komplett ersetzen durch:

```javascript
function renderTimeline(data){
  var spans = data.spans || [];
  var tl = $('timeline');
  tl.innerHTML = '';
  if (!spans.length) { tl.innerHTML = '<div class="muted">Keine Spans.</div>'; return; }
  try {
    // Gruppieren nach session_id (Reihenfolge des ersten Auftretens)
    var groups = {}; var order = [];
    spans.forEach(function(s){
      var sid = s.session_id || '?';
      if (!groups[sid]) { groups[sid] = { sid: sid, project: s.project || '', spans: [] }; order.push(sid); }
      groups[sid].spans.push(s);
    });
    var gapTxt = data.turn_gap_ms ? (Math.round(data.turn_gap_ms / 1000) + 's') : '–';
    order.forEach(function(sid){
      var g = groups[sid];
      var shortSid = String(sid).length > 12 ? String(sid).slice(0, 8) + '…' : String(sid);
      var sec = document.createElement('div');
      sec.className = 'tl-session';
      var head = '<h3>' + esc(shortSid);
      if (g.project) head += '<span class="proj">' + esc(g.project) + '</span>';
      head += '<span class="proj">turn-gap ' + esc(gapTxt) + '</span></h3>';
      // In Turns aufteilen (turn_index kommt vom Server)
      var turns = {}; var turnOrder = [];
      g.spans.forEach(function(s){
        var ti = (s.turn_index != null) ? s.turn_index : 0;
        if (!turns[ti]) { turns[ti] = []; turnOrder.push(ti); }
        turns[ti].push(s);
      });
      turnOrder.sort(function(a, b){ return a - b; });
      var body = '';
      turnOrder.forEach(function(ti){
        var layout = turnLayout(turns[ti]);
        var laneCount = layout.reduce(function(m, it){ return Math.max(m, it.lane + 1); }, 1);
        var durs = turns[ti].map(function(s){ return s.duration_ms || 0; });
        var sumDur = durs.reduce(function(a, b){ return a + b; }, 0);
        body += '<div class="tl-turn"><div class="tl-turn-head"><span class="idx">Turn ' + ti + '</span>'
              + ' · ' + turns[ti].length + ' Spans · Σ' + sumDur + 'ms</div>';
        body += '<div class="tl-track" style="height:' + (laneCount * 29) + 'px">';
        layout.forEach(function(it){
          var s = it.span;
          var cls = 'tl-bar';
          var style = 'left:' + it.left.toFixed(2) + '%;width:' + it.width.toFixed(2) + '%;top:' + (it.lane * 29) + 'px;';
          if (!it.dated) { cls += ' open'; }
          else if (s.ok === true) { cls += ' ok'; style += 'background:' + AC + ';'; }
          else if (s.ok === false) { cls += ' fail'; style += 'background:' + AC2 + ';'; }
          else { cls += ' open'; }
          var tool = s.tool_name || '?';
          var summ = s.summary || '';
          var dur = (s.duration_ms != null) ? s.duration_ms : null;
          var durTxt = dur !== null ? dur + 'ms' : 'offen';
          var label = [tool]; if (summ) label.push(summ); label.push(durTxt);
          var fullLabel = label.join(' · ');
          var title = fullLabel;
          if (s.risk && s.risk !== 'unknown') title += ' · risk:' + s.risk;
          if (s.mutating) title += ' · mutating';
          if (s.git_branch) title += ' · ' + s.git_branch;
          if (s.file_ext) title += ' · .' + s.file_ext;
          if (s.error) title += ' · ' + s.error;
          if (s.cwd) title += ' · ' + s.cwd;
          body += '<div class="' + cls + '" style="' + style + '" title="' + esc(title) + '">' + esc(fullLabel) + '</div>';
        });
        body += '</div></div>';
      });
      sec.innerHTML = head + body;
      tl.appendChild(sec);
    });
  } catch (e) {
    tl.innerHTML = '<div class="muted">Timeline-Render-Fehler: ' + esc(e && e.message ? e.message : e) + '</div>';
  }
}
```

- [ ] **Step 3: JS-Syntax des Templates prüfen**

Da das Template kein Standalone-JS ist, prüfe die Syntax der geänderten Funktionen per Node-Extraktion (Brace-Matching wie in Task 5). Schnell-Check:

Run: `python -X utf8 -m pytest -q tests/test_turn_layout.py -v`
Expected: PASS (turnLayout unverändert, weiter grün — beweist, dass der Block parsebar bleibt)

- [ ] **Step 4: Live-Smoke gegen den echten Server**

Server starten und Dashboard manuell prüfen (Regel 16: 127.0.0.1):

```bash
python analysis/server.py --port 8770
```

Im Browser `http://127.0.0.1:8770` öffnen → Tab **Timeline**. Erwartung: Sessions zeigen Turn-Container („Turn 0 · N Spans · ΣXms"), Balken auf echter Zeitachse positioniert, überlappende Spans gestapelt, Tooltips inkl. `git_branch`/`.ext`. Server mit Ctrl-C stoppen.

- [ ] **Step 5: Volle Suite + Isolation-Snapshot**

```bash
python -c "import hashlib,os; p='data/events.jsonl'; print('BEFORE', os.path.getsize(p))"
python -X utf8 -m pytest -q tests/
python -c "import json; ev=json.loads(open('data/events.jsonl',encoding='utf-8').read().splitlines()[-1]); print('last:', ev.get('tool_name'), ev.get('project'))"
```

Expected: alle Tests grün; ein evtl. Größenwachstum von `events.jsonl` MUSS durch eigene Live-Bash-Calls erklärbar sein (letztes Event = eigener Call), kein Test-Leak.

- [ ] **Step 6: Commit**

```bash
git add analysis/dashboard_template.html
git commit -m "feat(dashboard): Timeline-Tab als Turn-Waterfall (echte Zeitachse, Lanes)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: Docs nachziehen

**Files:**
- Modify: `docs/CAPABILITIES.md`, `HOW-TO-USE.md`

- [ ] **Step 1: CAPABILITIES.md — Auswertungs-Zeile schärfen**

In `docs/CAPABILITIES.md` die Auswertungs-Zeile um den Waterfall ergänzen (an die bestehende „Auswertung:"-Zeile anhängen):

```
- Timeline/Waterfall: der Timeline-Tab gruppiert Spans pro Session in Turns (global-adaptive Gap-Heuristik, median+3*MAD, Klammer 5-120s, Fallback 30s) und stellt sie pro Turn auf einer echten Zeitachse dar (x=Offset ab Turn-Start, Breite=Dauer); gleichzeitige Spans werden vertikal gestapelt.
```

- [ ] **Step 2: HOW-TO-USE.md — Live-Dashboard-Abschnitt aktualisieren**

In `HOW-TO-USE.md` den Timeline-Bullet (im Abschnitt „Live-Dashboard") ersetzen:

```
- **Timeline** (Waterfall): Spans pro Session in **Turns** gruppiert (Pause-Heuristik,
  adaptiver Schwellwert im Kopf angezeigt). Jeder Turn hat eine eigene Zeitachse:
  x-Position = Offset ab Turn-Start, Breite ∝ Dauer; gleichzeitige Spans gestapelt;
  gestrichelt = ungepaart.
```

- [ ] **Step 3: Commit**

```bash
git add docs/CAPABILITIES.md HOW-TO-USE.md
git commit -m "docs: Timeline-Tab als Turn-Waterfall beschreiben (B-1)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Abschluss-Checkliste (nach Task 7)

- [ ] Volle Suite grün (`python -X utf8 -m pytest -q tests/`), Span-Zahl ≥ vorher.
- [ ] Test-Isolation snapshot-bewiesen (kein Schreibzugriff auf `data/events.jsonl` durch Tests).
- [ ] Live-Smoke im Browser bestätigt (Turn-Container + Zeitachse + Lanes + Tooltips).
- [ ] Codex-Verifier-Review anbieten (Agent 1, Default).
- [ ] Push entscheidet der User.
