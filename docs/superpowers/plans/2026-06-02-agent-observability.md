# Agent Observability (Iteration 2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Erweitere den tool-usage-tracker von reinem PreToolUse-Logging um Erfolg/Fehler + Dauer pro Tool-Call und ein interaktives Live-Server-Dashboard.

**Architecture:** Ein zweiter never-block-Hook (`track_tool_post.py`) schreibt eine `phase:"post"`-Zeile ins selbe JSONL. Der Cold-Path (`_load.py`) paart Pre+Post heuristisch (session_id + tool_name + FIFO) zu „Spans" mit Dauer/Erfolg und berechnet Aggregate. Drei Konsumenten teilen diese Datenschicht: CLI-Report (existiert), statischer Generator (existiert), und ein neuer Stdlib-`http.server` (Tab A Analytics-Grid + Tab B Timeline).

**Tech Stack:** Python-Stdlib only (re, json, http.server, datetime, pathlib). Inline-Chart.js (bereits vendored). Kein Flask/pandas/Selenium.

**Ground-Truth-Korrektur ggü. Spec (P006-Recherche 2026-06-02):**
- Das PostToolUse-Payload-Feld heißt `tool_output` (nicht `tool_response`).
- Claude Code routet Erfolg/Fehler in ZWEI Events: `PostToolUse` (Erfolg) vs. `PostToolUseFailure` (Fehler, mit `tool_error`-Objekt). `ok` ergibt sich also aus `hook_event_name` — keine Per-Tool-Heuristik nötig. Fallback: `tool_output.exit_code` falls vorhanden.
- Keine Tool-Call-ID im Payload → FIFO-Paarung (wie Spec) ist korrekt.

---

## File Structure

- **Create** `hook/track_tool_post.py` — PostToolUse/-Failure-Hook. Schreibt `phase:"post"`-Zeile. Wiederverwendet `redact`/`clip`/`_events_path` aus `track_tool_use.py` (Import per importlib, da Geschwister-Datei).
- **Modify** `hook/track_tool_use.py` — `schema_v` → 2, `phase:"pre"` ins Pre-Event. `redact`/`clip`/`_events_path` bleiben die kanonische Quelle.
- **Modify** `analysis/_load.py` — neue `pair_events()` + Aggregat-Helfer (`success_rate_by`, `duration_stats_by`, `path_activity`). Rückwärtskompatibilität: fehlendes `phase` = `"pre"`.
- **Create** `analysis/server.py` — Stdlib-`http.server` an `127.0.0.1`. Routen `/` (HTML-Shell) + `/api/spans`. Keine Aggregationslogik, nur HTTP + Delegation an `_load.py`.
- **Create** `tests/test_pair_events.py` — Unit-Tests für Paarung + Aggregate.
- **Create** `tests/test_server.py` — Routen-Tests gegen den Handler (kein Browser).
- **Modify** `tests/test_track_tool_use.py` — schema_v:2 + phase:"pre" Assertions.
- **Create** `tests/test_track_tool_post.py` — Post-Hook-Tests (subprocess-E2E + Unit).

---

## Task 1: Pre-Hook auf schema_v:2 + phase heben

**Files:**
- Modify: `hook/track_tool_use.py` (`SCHEMA_V`, `build_event`)
- Test: `tests/test_track_tool_use.py`

- [ ] **Step 1: Failing Tests anpassen**

In `tests/test_track_tool_use.py`, `test_build_event_has_all_required_fields` erweitern und einen neuen Test ergänzen:

```python
def test_build_event_has_phase_pre_and_schema_2():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Bash", "tool_input": {"command": "ls"},
                            "hook_event_name": "PreToolUse"})
    assert ev["schema_v"] == 2
    assert ev["phase"] == "pre"
```

Und in `test_build_event_has_all_required_fields` die Zeile `assert ev["schema_v"] == 1` ändern zu `assert ev["schema_v"] == 2` und `"phase"` in die Feldliste aufnehmen.

- [ ] **Step 2: Run, verify FAIL**

Run: `python -m pytest tests/test_track_tool_use.py -k "phase_pre or all_required_fields" -v`
Expected: FAIL (`schema_v` ist 1, `phase` fehlt)

- [ ] **Step 3: Implementierung**

In `hook/track_tool_use.py`: `SCHEMA_V = 1` → `SCHEMA_V = 2`. In `build_event` den Return-Dict um `"phase": "pre",` ergänzen (z.B. direkt vor `"schema_v"`).

- [ ] **Step 4: Run, verify PASS**

Run: `python -m pytest tests/test_track_tool_use.py -v`
Expected: PASS (alle, inkl. der bestehenden)

- [ ] **Step 5: Commit**

```bash
git add hook/track_tool_use.py tests/test_track_tool_use.py
git commit -m "feat(hook): pre-event auf schema_v:2 + phase:pre"
```

---

## Task 2: PostToolUse-Hook (`track_tool_post.py`)

**Files:**
- Create: `hook/track_tool_post.py`
- Test: `tests/test_track_tool_post.py`

- [ ] **Step 1: Failing Test schreiben**

`tests/test_track_tool_post.py`:

```python
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hook" / "track_tool_post.py"
_spec = importlib.util.spec_from_file_location("track_tool_post", HOOK)
post = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(post)


def test_build_post_event_success():
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUse",
           "tool_output": {"exit_code": 0, "stdout": "ok", "stderr": ""}}
    ev = post.build_post_event(raw)
    assert ev["phase"] == "post"
    assert ev["schema_v"] == 2
    assert ev["tool_name"] == "Bash"
    assert ev["session_id"] == "s1"
    assert ev["ok"] is True
    assert ev["error"] == ""


def test_build_post_event_failure_event_name():
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUseFailure",
           "tool_error": {"type": "exit_code", "exit_code": 127,
                          "stderr": "command not found: pytetst"}}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False
    assert "command not found" in ev["error"]


def test_build_post_event_failure_via_exit_code_fallback():
    # Fallback: kein Failure-Eventname, aber non-zero exit_code im tool_output
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUse",
           "tool_output": {"exit_code": 2, "stdout": "", "stderr": "boom"}}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False
    assert "boom" in ev["error"]


def test_build_post_event_redacts_error():
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUseFailure",
           "tool_error": {"stderr": "api_key=supersecret123 failed"}}
    ev = post.build_post_event(raw)
    assert "‹redacted›" in ev["error"]
    assert "supersecret123" not in ev["error"]


def test_build_post_event_clips_long_error():
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUseFailure",
           "tool_error": {"stderr": "x" * 500}}
    ev = post.build_post_event(raw)
    assert len(ev["error"]) <= 120


def test_build_post_event_missing_fields_no_crash():
    ev = post.build_post_event({})
    assert ev["tool_name"] == "unknown"
    assert ev["phase"] == "post"
    assert ev["ok"] is True  # default: kein Fehlersignal => Erfolg


def _run_hook(stdin_text, env_extra):
    env = dict(os.environ, **env_extra)
    return subprocess.run([sys.executable, str(HOOK)], input=stdin_text,
                          capture_output=True, text=True, env=env)


def test_main_appends_post_line(tmp_path):
    target = tmp_path / "ev.jsonl"
    raw = json.dumps({"session_id": "s", "tool_name": "Read",
                      "hook_event_name": "PostToolUse",
                      "tool_output": {"exit_code": 0}})
    r = _run_hook(raw, {"TOOL_TRACKER_DATA": str(target)})
    assert r.returncode == 0
    ev = json.loads(target.read_text(encoding="utf-8").strip())
    assert ev["phase"] == "post"
    assert ev["ok"] is True


def test_main_broken_stdin_exits_zero(tmp_path):
    target = tmp_path / "ev.jsonl"
    r = _run_hook("not json {{{", {"TOOL_TRACKER_DATA": str(target)})
    assert r.returncode == 0  # never-block
```

- [ ] **Step 2: Run, verify FAIL**

Run: `python -m pytest tests/test_track_tool_post.py -v`
Expected: FAIL (`track_tool_post.py` existiert nicht / `build_post_event` undefined)

- [ ] **Step 3: Implementierung**

`hook/track_tool_post.py`:

```python
"""PostToolUse/-Failure-Hook: zeichnet Erfolg/Fehler je Tool-Call auf.
Darf NIE blockieren — alles in try/except, immer exit 0.
Wiederverwendet redact/clip/_events_path aus track_tool_use.py."""
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Schwester-Modul laden (kanonische Quelle für redact/clip/_events_path)
_PRE = Path(__file__).resolve().parent / "track_tool_use.py"
_spec = importlib.util.spec_from_file_location("track_tool_use", _PRE)
_pre = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pre)

AGENT = "claude-code"
SCHEMA_V = 2


def _derive_ok_and_error(raw: dict):
    """Erfolg primär aus hook_event_name, Fallback auf exit_code.
    Gegen reales Payload verifizieren (P006) — Schema ist undokumentiert."""
    event = str(raw.get("hook_event_name", "PostToolUse"))
    out = raw.get("tool_output") or {}
    err_obj = raw.get("tool_error") or {}
    exit_code = None
    if isinstance(out, dict):
        exit_code = out.get("exit_code")
    if exit_code is None and isinstance(err_obj, dict):
        exit_code = err_obj.get("exit_code")

    is_fail = event.endswith("Failure") or (isinstance(exit_code, int) and exit_code != 0)
    if not is_fail:
        return True, ""

    # Fehlertext sammeln: tool_error.stderr > tool_output.stderr > generisch
    raw_err = ""
    if isinstance(err_obj, dict):
        raw_err = str(err_obj.get("stderr") or err_obj.get("type") or "")
    if not raw_err and isinstance(out, dict):
        raw_err = str(out.get("stderr") or "")
    if not raw_err:
        raw_err = f"exit_code={exit_code}" if exit_code is not None else "error"
    return False, _pre.clip(_pre.redact(raw_err.splitlines()[0] if raw_err else raw_err))


def build_post_event(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    now = datetime.now(timezone.utc)
    now_local = now.astimezone()
    ok, error = _derive_ok_and_error(raw)
    return {
        "ts_utc": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
        "ts_local": now_local.strftime("%Y-%m-%d %H:%M:%S"),
        "agent": AGENT,
        "schema_v": SCHEMA_V,
        "phase": "post",
        "tool_name": raw.get("tool_name") or "unknown",
        "session_id": raw.get("session_id", ""),
        "ok": ok,
        "error": error,
    }


def main() -> int:
    try:
        data = sys.stdin.read()
        raw = json.loads(data) if data.strip() else {}
        ev = build_post_event(raw)
        path = _pre._events_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Tracking darf NIE die Arbeit stören
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run, verify PASS**

Run: `python -m pytest tests/test_track_tool_post.py -v`
Expected: PASS (alle 8)

- [ ] **Step 5: Gegen reales Payload verifizieren (P006)**

Manuell ein echtes PostToolUse-Payload prüfen: temporär den matcher in einer Test-`settings.json` setzen, EINEN harmlosen Bash-Call auslösen, die geschriebene Zeile inspizieren. Bestätigen: `ok`/`error` korrekt. Falls das reale Feld abweicht (z.B. `tool_response` statt `tool_output`), `_derive_ok_and_error` anpassen + Test ergänzen. NICHT überspringen.

- [ ] **Step 6: Commit**

```bash
git add hook/track_tool_post.py tests/test_track_tool_post.py
git commit -m "feat(hook): PostToolUse/-Failure-Hook (ok/error, never-block)"
```

---

## Task 3: `pair_events()` im Cold-Path

**Files:**
- Modify: `analysis/_load.py`
- Test: `tests/test_pair_events.py`

- [ ] **Step 1: Failing Test schreiben**

`tests/test_pair_events.py`:

```python
import importlib.util
from pathlib import Path

LOADER = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
_spec = importlib.util.spec_from_file_location("_load", LOADER)
load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(load)


def _pre(sid, tool, t, **kw):
    d = {"phase": "pre", "session_id": sid, "tool_name": tool, "ts_utc": t,
         "project": "P", "summary": "s", "cwd": "c", "agent": "claude-code"}
    d.update(kw)
    return d


def _post(sid, tool, t, ok=True, error=""):
    return {"phase": "post", "session_id": sid, "tool_name": tool, "ts_utc": t,
            "ok": ok, "error": error, "agent": "claude-code"}


def test_pairs_pre_and_post_into_span():
    evs = [_pre("s1", "Bash", "2026-06-02T10:00:00.000Z"),
           _post("s1", "Bash", "2026-06-02T10:00:00.340Z")]
    spans = load.pair_events(evs)
    assert len(spans) == 1
    s = spans[0]
    assert s["paired"] is True
    assert s["duration_ms"] == 340
    assert s["ok"] is True
    assert s["tool_name"] == "Bash"
    assert s["project"] == "P"  # aus dem Pre-Event übernommen


def test_fifo_same_tool_twice():
    evs = [_pre("s1", "Bash", "2026-06-02T10:00:00.000Z", summary="first"),
           _pre("s1", "Bash", "2026-06-02T10:00:01.000Z", summary="second"),
           _post("s1", "Bash", "2026-06-02T10:00:00.500Z"),
           _post("s1", "Bash", "2026-06-02T10:00:02.000Z")]
    spans = load.pair_events(evs)
    paired = [s for s in spans if s["paired"]]
    assert len(paired) == 2
    # FIFO: erstes Post paart mit erstem Pre (summary "first")
    assert paired[0]["summary"] == "first"
    assert paired[0]["duration_ms"] == 500


def test_unpaired_pre_is_kept_but_marked():
    evs = [_pre("s1", "Read", "2026-06-02T10:00:00.000Z")]
    spans = load.pair_events(evs)
    assert len(spans) == 1
    assert spans[0]["paired"] is False
    assert spans[0]["duration_ms"] is None
    assert spans[0]["ok"] is None


def test_schema_v1_event_without_phase_treated_as_pre():
    # Altdaten ohne phase-Feld
    evs = [{"session_id": "s1", "tool_name": "Glob",
            "ts_utc": "2026-06-02T10:00:00.000Z", "agent": "claude-code"}]
    spans = load.pair_events(evs)
    assert len(spans) == 1
    assert spans[0]["paired"] is False  # kein Post -> ungepaart, aber da


def test_post_only_session_does_not_cross_sessions():
    evs = [_pre("s1", "Bash", "2026-06-02T10:00:00.000Z"),
           _post("s2", "Bash", "2026-06-02T10:00:00.500Z")]
    spans = load.pair_events(evs)
    # Pre s1 ungepaart, Post s2 verwaist -> beide da, beide unpaired
    assert all(s["paired"] is False for s in spans)
```

- [ ] **Step 2: Run, verify FAIL**

Run: `python -m pytest tests/test_pair_events.py -v`
Expected: FAIL (`pair_events` undefined)

- [ ] **Step 3: Implementierung**

In `analysis/_load.py` ans Ende anhängen:

```python
def _phase(ev):
    # Schema-v1-Events haben kein phase-Feld -> als "pre" behandeln
    return ev.get("phase", "pre")


def _duration_ms(start_ts, end_ts):
    from datetime import datetime
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
    try:
        a = datetime.strptime(start_ts, fmt)
        b = datetime.strptime(end_ts, fmt)
        return int((b - a).total_seconds() * 1000)
    except Exception:
        return None


def pair_events(events):
    """Verschmilzt pre+post zu Spans (session_id + tool_name + FIFO).
    Ungepaarte Events bleiben erhalten (paired=False), zählen nicht in Aggregate."""
    spans = []
    # offene Pres je (session_id, tool_name) als FIFO-Queue
    open_pre = {}
    used_pre = set()
    # erst alle Events in Reihenfolge; Post paart mit ältestem offenen Pre
    ordered = sorted(events, key=lambda e: str(e.get("ts_utc", "")))
    # Index der Pres pro Key
    for ev in ordered:
        if _phase(ev) == "pre":
            key = (ev.get("session_id"), ev.get("tool_name"))
            open_pre.setdefault(key, []).append(ev)
    for ev in ordered:
        if _phase(ev) != "post":
            continue
        key = (ev.get("session_id"), ev.get("tool_name"))
        queue = open_pre.get(key, [])
        match = None
        for pre in queue:
            if id(pre) not in used_pre:
                match = pre
                used_pre.add(id(pre))
                break
        if match is not None:
            spans.append({
                "tool_name": match.get("tool_name"), "agent": match.get("agent"),
                "session_id": match.get("session_id"), "project": match.get("project"),
                "summary": match.get("summary"), "cwd": match.get("cwd"),
                "ts_start": match.get("ts_utc"), "ts_end": ev.get("ts_utc"),
                "duration_ms": _duration_ms(match.get("ts_utc", ""), ev.get("ts_utc", "")),
                "ok": ev.get("ok"), "error": ev.get("error", ""), "paired": True,
            })
        else:
            # verwaistes Post
            spans.append({
                "tool_name": ev.get("tool_name"), "agent": ev.get("agent"),
                "session_id": ev.get("session_id"), "project": None,
                "summary": None, "cwd": None,
                "ts_start": None, "ts_end": ev.get("ts_utc"),
                "duration_ms": None, "ok": None, "error": ev.get("error", ""),
                "paired": False,
            })
    # ungepaarte Pres
    for queue in open_pre.values():
        for pre in queue:
            if id(pre) not in used_pre:
                spans.append({
                    "tool_name": pre.get("tool_name"), "agent": pre.get("agent"),
                    "session_id": pre.get("session_id"), "project": pre.get("project"),
                    "summary": pre.get("summary"), "cwd": pre.get("cwd"),
                    "ts_start": pre.get("ts_utc"), "ts_end": None,
                    "duration_ms": None, "ok": None, "error": "", "paired": False,
                })
    return spans
```

- [ ] **Step 4: Run, verify PASS**

Run: `python -m pytest tests/test_pair_events.py -v`
Expected: PASS (alle 5)

- [ ] **Step 5: Commit**

```bash
git add analysis/_load.py tests/test_pair_events.py
git commit -m "feat(load): pair_events() — pre+post zu Spans, FIFO, ungepaart erhalten"
```

---

## Task 4: Aggregat-Helfer

**Files:**
- Modify: `analysis/_load.py`
- Test: `tests/test_pair_events.py` (anhängen)

- [ ] **Step 1: Failing Test schreiben**

In `tests/test_pair_events.py` anhängen:

```python
def _span(tool, ok, dur, project="P", agent="claude-code", cwd="c"):
    return {"tool_name": tool, "ok": ok, "duration_ms": dur, "project": project,
            "agent": agent, "cwd": cwd, "paired": dur is not None}


def test_success_rate_by_tool():
    spans = [_span("Bash", True, 100), _span("Bash", False, 200),
             _span("Read", True, 50)]
    rates = load.success_rate_by(spans, "tool_name")
    assert rates["Bash"] == 0.5
    assert rates["Read"] == 1.0


def test_success_rate_ignores_unpaired():
    spans = [_span("Bash", True, 100), {"tool_name": "Bash", "ok": None,
             "duration_ms": None, "paired": False}]
    rates = load.success_rate_by(spans, "tool_name")
    assert rates["Bash"] == 1.0  # das ungepaarte zählt nicht


def test_duration_stats_by_tool():
    spans = [_span("Bash", True, 100), _span("Bash", True, 300)]
    stats = load.duration_stats_by(spans, "tool_name")
    assert stats["Bash"]["avg"] == 200
    assert stats["Bash"]["median"] == 200
    assert stats["Bash"]["p95"] >= 300 - 1  # p95 nahe Max bei 2 Werten


def test_path_activity_counts_by_cwd():
    spans = [_span("Bash", True, 100, cwd="C:/a/dual-bridge"),
             _span("Read", True, 50, cwd="C:/a/dual-bridge"),
             _span("Edit", True, 70, cwd="C:/a/Hooks-bau")]
    act = load.path_activity(spans)
    assert act["C:/a/dual-bridge"] == 2
    assert act["C:/a/Hooks-bau"] == 1
```

- [ ] **Step 2: Run, verify FAIL**

Run: `python -m pytest tests/test_pair_events.py -k "rate or duration or path_activity" -v`
Expected: FAIL (Funktionen undefined)

- [ ] **Step 3: Implementierung**

In `analysis/_load.py` anhängen:

```python
def _paired_with_ok(spans):
    return [s for s in spans if s.get("paired") and s.get("ok") is not None]


def success_rate_by(spans, key):
    from collections import defaultdict
    agg = defaultdict(lambda: [0, 0])  # [ok, total]
    for s in _paired_with_ok(spans):
        k = s.get(key)
        agg[k][1] += 1
        if s.get("ok"):
            agg[k][0] += 1
    return {k: (ok / total if total else 0.0) for k, (ok, total) in agg.items()}


def duration_stats_by(spans, key):
    from collections import defaultdict
    buckets = defaultdict(list)
    for s in spans:
        if s.get("paired") and isinstance(s.get("duration_ms"), int):
            buckets[s.get(key)].append(s["duration_ms"])
    out = {}
    for k, vals in buckets.items():
        vals = sorted(vals)
        n = len(vals)
        avg = sum(vals) / n
        median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
        p95 = vals[min(n - 1, int(round(0.95 * (n - 1))))]
        out[k] = {"avg": avg, "median": median, "p95": p95, "count": n}
    return out


def path_activity(spans):
    from collections import Counter
    return dict(Counter(s.get("cwd") for s in spans if s.get("cwd")))
```

- [ ] **Step 4: Run, verify PASS**

Run: `python -m pytest tests/test_pair_events.py -v`
Expected: PASS (alle 9)

- [ ] **Step 5: Commit**

```bash
git add analysis/_load.py tests/test_pair_events.py
git commit -m "feat(load): Aggregate (success_rate_by, duration_stats_by, path_activity)"
```

---

## Task 5: Live-Server (`analysis/server.py`) — /api/spans

**Files:**
- Create: `analysis/server.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Failing Test schreiben**

`tests/test_server.py`:

```python
import importlib.util
import json
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "analysis" / "server.py"
_spec = importlib.util.spec_from_file_location("server", SERVER)
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)


def _write(tmp_path, rows):
    p = tmp_path / "ev.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def test_spans_json_pairs_events(tmp_path):
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "P", "cwd": "c",
         "summary": "x", "agent": "claude-code"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.200Z", "ok": True, "error": "",
         "agent": "claude-code"},
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["count"] == 1
    assert payload["spans"][0]["duration_ms"] == 200
    assert "success_by_tool" in payload
    assert payload["success_by_tool"]["Bash"] == 1.0


def test_spans_json_respects_exclude_self(tmp_path):
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "tool-usage-tracker",
         "cwd": "c", "summary": "x", "agent": "claude-code"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.200Z", "ok": True, "agent": "claude-code"},
    ])
    payload = srv.spans_payload(str(p), {"exclude_self": "1"})
    assert payload["count"] == 0  # self-Projekt rausgefiltert vor Paarung


def test_parse_query_flags():
    params = srv.parse_query("agent=codex&exclude_self=1&since=2026-06-01")
    assert params["agent"] == "codex"
    assert params["exclude_self"] == "1"
    assert params["since"] == "2026-06-01"
```

- [ ] **Step 2: Run, verify FAIL**

Run: `python -m pytest tests/test_server.py -v`
Expected: FAIL (`server.py` / Funktionen undefined)

- [ ] **Step 3: Implementierung**

`analysis/server.py`:

```python
"""Live-Dashboard-Server (Stdlib http.server, an 127.0.0.1 gebunden — Regel 16).
Enthält KEINE Aggregationslogik — nur HTTP + Delegation an _load.py.
Usage: python analysis/server.py [--data PFAD] [--port N]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from _load import (load_events, pair_events, success_rate_by,
                   duration_stats_by, path_activity)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "events.jsonl"


def parse_query(query_string):
    raw = parse_qs(query_string)
    return {k: v[0] for k, v in raw.items()}


def spans_payload(data_path, params):
    evs = load_events(data_path,
                      agent=params.get("agent"),
                      project=params.get("project"),
                      since=params.get("since"),
                      exclude_self=params.get("exclude_self") in ("1", "true", "True"))
    spans = pair_events(evs)
    return {
        "count": len([s for s in spans if s.get("paired")]),
        "total_events": len(evs),
        "spans": spans,
        "success_by_tool": success_rate_by(spans, "tool_name"),
        "success_by_project": success_rate_by(spans, "project"),
        "duration_by_tool": duration_stats_by(spans, "tool_name"),
        "path_activity": path_activity(spans),
    }


def make_handler(data_path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass  # keine Konsolen-Spam

        def _send(self, code, body, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/spans":
                params = parse_query(parsed.query)
                self._send(200, json.dumps(spans_payload(data_path, params)))
            elif parsed.path == "/":
                self._send(200, _INDEX_HTML, "text/html")
            else:
                self._send(404, json.dumps({"error": "not found"}))
    return Handler


_INDEX_HTML = "<!-- platzhalter, in Task 6 ersetzt -->"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args()
    httpd = HTTPServer(("127.0.0.1", a.port), make_handler(a.data))
    print(f"Dashboard-Server: http://127.0.0.1:{a.port}  (Ctrl-C zum Stoppen)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run, verify PASS**

Run: `python -m pytest tests/test_server.py -v`
Expected: PASS (alle 3)

- [ ] **Step 5: Commit**

```bash
git add analysis/server.py tests/test_server.py
git commit -m "feat(server): Stdlib http.server, /api/spans (127.0.0.1, kein State)"
```

---

## Task 6: Tab A — Analytics-Grid (HTML/JS) + Treemap→Heat-Baum

**Files:**
- Modify: `analysis/server.py` (`_INDEX_HTML`)

- [ ] **Step 1: HTML-Shell mit Tab A schreiben**

In `analysis/server.py` `_INDEX_HTML` ersetzen durch ein vollständiges HTML-Dokument (Dark-Theme `#0a0e14`/`#121821`, Akzente `#39d0d8`/`#f7768e`, JetBrains Mono + Outfit). Inline-Chart.js aus `vendor/chart.umd.min.js` einlesen und einbetten (analog `dashboard.py`: `CHARTJS = ROOT/"vendor"/"chart.umd.min.js"; chartjs = CHARTJS.read_text(...)`; `_INDEX_HTML` zur Funktion `index_html()` machen, die das einbettet). Struktur:

- Tab-Leiste: `[Analytics] [Timeline]` + Refresh-Button + Filter-Inputs (agent, project, since, exclude_self-Checkbox).
- **Tab A (default sichtbar):** KPI-Reihe (Total-Calls, Erfolgsquote, Ø-Dauer, p95) · Canvas Top-Tools (bar) · Canvas Aktivität/Zeit (line) · Canvas Fehlerrate pro Tool (bar) · **Treemap** (HTML-Divs, Fläche≈Call-Count aus `path_activity`, via flexbox-Gewichtung) · darunter ausklappbarer **Heat-Baum** (Div-Liste, eingerückt nach cwd-Segmenten, Heat-Badge = Count).
- JS: `async function refresh()` ruft `/api/spans?<filter>` und re-rendert alle Charts + Treemap + Baum. Refresh-Button und initialer `refresh()`-Call beim Laden. KEIN Auto-Poll.
- Treemap-Kachel `onclick` → expandiert den Heat-Baum für diesen Pfad (Client-seitig filtern, kein Server-Roundtrip nötig).

Wichtig (Lehre docs/TODO.md): nach dem Schreiben den eingebetteten Script-Block mit `node --check` validieren, nicht nur Byte-Größe prüfen.

- [ ] **Step 2: Smoke-Test — Server starten, Seite + API prüfen**

```bash
python analysis/server.py --data data/events.jsonl --port 8771 &
sleep 2
curl -s http://127.0.0.1:8771/api/spans | python -c "import sys,json; d=json.load(sys.stdin); print('count', d['count'])"
curl -s http://127.0.0.1:8771/ | grep -c "Analytics"
```
Expected: API liefert JSON mit `count`; `/` enthält "Analytics". Server danach stoppen (Job kill).

- [ ] **Step 3: JS-Syntax validieren**

Script-Block aus der gerenderten Seite extrahieren und `node --check` (oder per Playwright laden + Console-Errors prüfen). Expected: keine Syntax-Fehler.

- [ ] **Step 4: Commit**

```bash
git add analysis/server.py
git commit -m "feat(server): Tab A Analytics-Grid + Treemap→Heat-Baum-Drilldown"
```

---

## Task 7: Tab B — Timeline/Flow

**Files:**
- Modify: `analysis/server.py` (`index_html()` JS)

- [ ] **Step 1: Tab B rendern**

Im JS von `index_html()` Tab B ergänzen: pro `session_id` eine Zeile, darin die Spans dieser Session chronologisch als horizontale Balken. Balken-Breite ∝ `duration_ms` (ungepaarte: feste Mindestbreite, gestrichelter Rand). Farbe: `ok===true` → `#39d0d8`, `ok===false` → `#f7768e`, `ok===null` (ungepaart) → transparent mit gestricheltem Rand. Tooltip/Label: `tool_name` + `summary` + Dauer. Tab-Umschaltung blendet Tab A aus, Tab B ein (CSS display). Beide teilen die `refresh()`-Daten (ein Fetch, beide Tabs rendern daraus).

- [ ] **Step 2: Smoke-Test**

```bash
python analysis/server.py --data data/events.jsonl --port 8772 &
sleep 2
curl -s http://127.0.0.1:8772/ | grep -c "Timeline"
```
Expected: `/` enthält "Timeline". Server stoppen.

- [ ] **Step 3: JS-Syntax validieren** (`node --check` wie Task 6 Step 3). Expected: keine Fehler.

- [ ] **Step 4: Commit**

```bash
git add analysis/server.py
git commit -m "feat(server): Tab B Timeline/Flow (Spans als Balken, ungepaart sichtbar)"
```

---

## Task 8: Doku + Abschluss

**Files:**
- Modify: `tool-usage-tracker/HOW-TO-USE.md`, `tool-usage-tracker/docs/CHANGELOG.md`, `install.md`

- [ ] **Step 1: HOW-TO-USE.md + install.md ergänzen**

PostToolUse/-Failure-Hook-Eintrag für `~/.claude/settings.json` dokumentieren (matcher analog Pre-Hook, ruft `hook/track_tool_post.py`). Server-Nutzung dokumentieren: `python analysis/server.py [--port N]`, Browser auf `http://127.0.0.1:<port>` (Regel 16 — explizit 127.0.0.1, nicht localhost). exclude_self-Filter erwähnen.

- [ ] **Step 2: CHANGELOG.md — Iteration 2 Eintrag**

- [ ] **Step 3: Volle Suite + Commit**

```bash
python -m pytest tests/ -v
```
Expected: alle grün (Iteration-1 + neue Tasks). Dann:

```bash
git add HOW-TO-USE.md docs/CHANGELOG.md install.md
git commit -m "docs: Iteration-2 (PostToolUse-Hook + Live-Server) dokumentiert"
```

---

## Nicht-Ziele (NICHT in diesem Plan — spätere Iterationen)

- Token-Tracking (eigener Transcript-Parser, Hooks sehen keine Tokens)
- Codex-Adapter (Schema agent-agnostisch vorbereitet)
- Retry-/Korrektur-Muster-Erkennung
- Auto-Poll / SSE-Streaming (manueller Refresh reicht)
