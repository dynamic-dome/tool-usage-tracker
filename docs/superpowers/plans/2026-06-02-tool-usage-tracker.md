# Tool-Usage-Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Claude-Code-PreToolUse-Hook, der jede Tool-Anwendung als sanitisierte JSONL-Zeile aufzeichnet, plus CLI-Report und self-contained HTML-Dashboard zur Auswertung.

**Architecture:** Hot-Path (`hook/track_tool_use.py`) liest stdin-JSON, sanitisiert, hängt eine Zeile an `data/events.jsonl` an und beendet IMMER mit exit 0 (nie blockieren). Cold-Path (`analysis/report.py`, `analysis/dashboard.py`) liest dieselbe JSONL und wertet aus. Event-Pfad ist eine lazy Funktion (`TOOL_TRACKER_DATA`-Env override) — Tests schreiben nie in die echte Datei.

**Tech Stack:** Python 3.12 (nur Stdlib: json, os, re, datetime, collections, pathlib), pytest 9, Chart.js (inline eingebettet, kein CDN), Git + gh (privates Repo unter dynamic-dome).

---

## File Structure

| Datei | Verantwortung |
|---|---|
| `hook/track_tool_use.py` | Hot-Path: stdin→sanitize→JSONL append. Enthält `_events_path()`, `derive_project()`, `sanitize_summary()`, `build_event()`, `main()`. |
| `analysis/report.py` | Cold-Path CLI: JSONL laden, Aggregate + ASCII-Report, Filter-Flags. |
| `analysis/dashboard.py` | Cold-Path HTML: JSONL laden, KPI + 4 Charts (Chart.js inline) → `dashboard.html`. |
| `analysis/_load.py` | Geteilter Loader: `load_events(path, agent, project, since)` — von report.py und dashboard.py genutzt (DRY). |
| `tests/test_track_tool_use.py` | Unit-Tests Hot-Path (Sanitizer, Pfad-Kürzung, Robustheit, Schema). |
| `tests/test_load.py` | Unit-Tests Loader (Filter, kaputte Zeilen überspringen). |
| `vendor/chart.umd.min.js` | Chart.js v4 (lokal, wird inline ins HTML gebettet). |
| `CLAUDE.md`, `HOW-TO-USE.md`, `install.md`, `docs/*` | Projekt-Skelett + Doku. |
| `.gitignore` | schließt `data/`, `__pycache__/`, `*.html`-Output aus. |

---

## Task 1: Git-Repo + Projekt-Skelett + .gitignore

**Files:**
- Create: `.gitignore`, `README.md`, `CLAUDE.md`, `HOW-TO-USE.md`
- Create: `docs/PROJECT.md`, `docs/CAPABILITIES.md`, `docs/ARCHITECTURE.md`, `docs/CHANGELOG.md`

- [ ] **Step 1: Git-Identity sicherstellen** (ist global nicht gesetzt)

```bash
cd "C:/Users/domes/AI/Hooks-bau/tool-usage-tracker"
git config --global user.name "dynamic-dome"
git config --global user.email "domeass69@gmail.com"
```

- [ ] **Step 2: `.gitignore` schreiben**

```gitignore
# Tracking-Daten NIE committen (enthalten Tool-Nutzungs-Historie)
data/
*.jsonl

# Generierte Dashboards
analysis/dashboard.html
dashboard.html

# Python
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: `README.md` (Workspace-Sammelindex eine Ebene höher) + projekt-README**

Erstelle `C:/Users/domes/AI/Hooks-bau/README.md`:

```markdown
# Hooks-bau

Sammelordner für selbstgebaute Claude-Code-Hooks. **1 Hook = 1 Unterordner.**

| Hook | Zweck | Status |
|------|-------|--------|
| [tool-usage-tracker](tool-usage-tracker/) | PreToolUse-Tracking aller Tool-Anwendungen + Auswertung | in Entwicklung |
```

- [ ] **Step 4: `CLAUDE.md` (projekt-spezifisch, max ~40 Zeilen)**

```markdown
# CLAUDE.md — tool-usage-tracker

## Projekt
PreToolUse-Hook für Claude Code: zeichnet jede Tool-Anwendung als sanitisierte
JSONL-Zeile auf. Auswertung per CLI-Report + HTML-Dashboard. Privates Git-Repo.
Details: HOW-TO-USE.md + docs/.

## Kern-Regeln
- Hot-Path (`hook/track_tool_use.py`) darf NIE blockieren: alles in try/except,
  immer exit 0, nie permissionDecision.
- Event-Pfad ist eine LAZY Funktion `_events_path()` mit Env-Override
  `TOOL_TRACKER_DATA` — niemals als Modul-Konstante einfrieren.
- Tests schreiben NIE in data/events.jsonl (eigene tmp_path je Test).
- Sanitizer: 120-Zeichen-Limit + Secret-Redaction, kein Datei-Inhalt.
- Nur Python-Stdlib (kein pandas/matplotlib). Chart.js wird inline gebettet.

## Konventionen
- Sprache: Deutsch für Kommunikation, Englisch für Code/Dateinamen.
- Dashboard-Stil: Dark-Theme/Command-Center, JetBrains Mono + Outfit.
```

- [ ] **Step 5: `HOW-TO-USE.md`**

```markdown
# HOW-TO-USE — tool-usage-tracker

## Was ist das?
Hook, der bei jeder Claude-Tool-Anwendung ein Event nach `data/events.jsonl` schreibt.

## Installation
Siehe `install.md` — Snippet in `~/.claude/settings.json` einhängen, Claude neu starten.

## Auswertung
- CLI: `python analysis/report.py` (Flags: --agent --project --since --data)
- HTML: `python analysis/dashboard.py` → öffnet `dashboard.html`

## Architektur / Felder / Sanitisierung
Siehe `docs/ARCHITECTURE.md` und das Design-Doc
`docs/superpowers/specs/2026-06-02-tool-usage-tracker-design.md`.
```

- [ ] **Step 6: `docs/` Stub-Dateien**

`docs/PROJECT.md`:
```markdown
# PROJECT — tool-usage-tracker
**Zweck:** PreToolUse-Tracking aller Claude-Tool-Anwendungen + Auswertung.
**Status:** Iteration 1 (nur Claude Code). Spec: docs/superpowers/specs/2026-06-02-tool-usage-tracker-design.md
**Nicht-Ziele:** kein PostToolUse, kein Blockieren, kein Daemon, kein Server-Dashboard.
```

`docs/CAPABILITIES.md`:
```markdown
# CAPABILITIES
- Aufzeichnen: ts_utc, ts_local, agent, tool_name, session_id, cwd, project, is_git_repo, hook_event, summary, schema_v.
- Sanitisierung: 120-Zeichen-Limit, Secret-Redaction, Pfad-Kürzung, kein Datei-Inhalt.
- Auswertung: CLI-Report (Top-Tools, pro Projekt, pro Tag, pro Stunde) + HTML-Dashboard (KPIs + 4 Charts).
```

`docs/ARCHITECTURE.md`:
```markdown
# ARCHITECTURE
Hot-Path: hook/track_tool_use.py — stdin JSON → sanitize → append JSONL → exit 0.
Cold-Path: analysis/_load.py (Loader) → report.py (CLI) / dashboard.py (HTML).
Speicher: data/events.jsonl (append-only). Pfad via lazy _events_path() + Env TOOL_TRACKER_DATA.
Event-Schema + Sanitizer-Regeln: siehe Design-Doc in docs/superpowers/specs/.
```

`docs/CHANGELOG.md`:
```markdown
# CHANGELOG
## 2026-06-02
- Projekt-Setup, Design-Doc + Plan.
```

- [ ] **Step 7: Repo initialisieren + privates Remote erstellen + ersten Commit pushen**

```bash
cd "C:/Users/domes/AI/Hooks-bau/tool-usage-tracker"
git init
git add .gitignore README.md CLAUDE.md HOW-TO-USE.md docs/
git status --short
git commit -m "chore: project skeleton, docs, gitignore"
gh repo create tool-usage-tracker --private --source=. --remote=origin --push
```
Expected: Repo `dynamic-dome/tool-usage-tracker` (private) angelegt, Branch gepusht.
Verifikation: `gh repo view dynamic-dome/tool-usage-tracker --json visibility,name`

> Hinweis: `README.md` liegt im Tool-Ordner; der Workspace-Index `../README.md`
> liegt außerhalb des Repos und wird NICHT mitgepusht (nur lokal angelegt).

---

## Task 2: Sanitizer — Längenlimit + Secret-Redaction

**Files:**
- Create: `hook/track_tool_use.py`
- Test: `tests/test_track_tool_use.py`

- [ ] **Step 1: Failing Test schreiben**

`tests/test_track_tool_use.py`:
```python
import importlib.util
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hook" / "track_tool_use.py"
_spec = importlib.util.spec_from_file_location("track_tool_use", HOOK)
track = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(track)


def test_sanitize_truncates_to_120_chars():
    long = "echo " + "a" * 500
    out = track.clip(long)
    assert len(out) <= 120
    assert out.endswith("…")


def test_redact_openai_key():
    assert "‹redacted›" in track.redact("key sk-ABCD1234567890efgh")
    assert "sk-ABCD" not in track.redact("key sk-ABCD1234567890efgh")


def test_redact_assignment_secrets():
    assert "‹redacted›" in track.redact("api_key=supersecretvalue123")
    assert "‹redacted›" in track.redact("PASSWORD: hunter2hunter2")
    assert "‹redacted›" in track.redact("Authorization: Bearer abc.def.ghi")


def test_redact_github_token():
    assert "‹redacted›" in track.redact("ghp_0123456789abcdefABCDEF0123")
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/test_track_tool_use.py -v`
Expected: FAIL (Datei/Funktionen existieren nicht).

- [ ] **Step 3: Minimal-Implementierung `clip` + `redact`**

`hook/track_tool_use.py` (Anfang):
```python
"""PreToolUse-Hook: zeichnet jede Tool-Anwendung als JSONL-Zeile auf.
Darf NIE blockieren — alles in try/except, immer exit 0."""
import re

MAX_LEN = 120

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret|auth)\s*[=:]\s*\S+"),
    re.compile(r"(?i)bearer\s+\S+"),
]


def redact(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub("‹redacted›", text)
    return text


def clip(text: str) -> str:
    text = text.strip()
    if len(text) > MAX_LEN:
        return text[: MAX_LEN - 1] + "…"
    return text
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `python -m pytest tests/test_track_tool_use.py -v`
Expected: PASS (4 Tests).

- [ ] **Step 5: Commit**

```bash
git add hook/track_tool_use.py tests/test_track_tool_use.py
git commit -m "feat: sanitizer (clip + secret redaction)"
```

---

## Task 3: Summary-Builder pro Tool-Typ

**Files:**
- Modify: `hook/track_tool_use.py`
- Test: `tests/test_track_tool_use.py`

- [ ] **Step 1: Failing Tests anhängen**

In `tests/test_track_tool_use.py` ergänzen:
```python
def test_summary_bash_redacts_and_clips():
    s = track.build_summary("Bash", {"command": "curl -H 'api_key=secret123abc' x"})
    assert "‹redacted›" in s
    assert len(s) <= 120


def test_summary_edit_shortens_path():
    s = track.build_summary("Edit", {"file_path": r"C:\a\b\c\d\e\file.py"})
    assert s == r"c\d\e\file.py" or s.endswith("file.py")
    assert "C:\\a\\b" not in s


def test_summary_grep_uses_pattern():
    assert track.build_summary("Grep", {"pattern": "TODO"}) == "TODO"


def test_summary_mcp_tool_has_no_input():
    assert track.build_summary("mcp__wiki__wiki_read", {"path": "secret/x.md"}) == ""


def test_summary_unknown_tool_empty():
    assert track.build_summary("SomethingNew", {"weird": "data"}) == ""
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/test_track_tool_use.py -k summary -v`
Expected: FAIL (`build_summary` nicht definiert).

- [ ] **Step 3: `build_summary` implementieren**

In `hook/track_tool_use.py` ergänzen:
```python
def _short_path(p: str, keep: int = 3) -> str:
    p = p.replace("/", "\\")
    parts = [x for x in p.split("\\") if x]
    return "\\".join(parts[-keep:]) if parts else ""


def build_summary(tool_name: str, tool_input: dict) -> str:
    if not isinstance(tool_input, dict):
        return ""
    if tool_name.startswith("mcp__"):
        return ""
    if tool_name == "Bash":
        return clip(redact(str(tool_input.get("command", ""))))
    if tool_name in ("Read", "Write", "Edit", "NotebookEdit"):
        return clip(_short_path(str(tool_input.get("file_path", ""))))
    if tool_name in ("Grep", "Glob"):
        return clip(redact(str(tool_input.get("pattern", ""))))
    if tool_name in ("Task", "Agent"):
        return clip(redact(str(tool_input.get("description", ""))))
    if tool_name == "WebFetch":
        return clip(str(tool_input.get("url", "")))
    if tool_name == "WebSearch":
        return clip(redact(str(tool_input.get("query", ""))))
    return ""
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `python -m pytest tests/test_track_tool_use.py -v`
Expected: PASS (alle, inkl. summary-Tests).

- [ ] **Step 5: Commit**

```bash
git add hook/track_tool_use.py tests/test_track_tool_use.py
git commit -m "feat: per-tool summary builder"
```

---

## Task 4: Projekt-Ableitung + lazy Event-Pfad

**Files:**
- Modify: `hook/track_tool_use.py`
- Test: `tests/test_track_tool_use.py`

- [ ] **Step 1: Failing Tests anhängen**

```python
import os


def test_derive_project_basename():
    assert track.derive_project(r"C:\Users\<user>\AI\Hooks-bau") == "Hooks-bau"


def test_derive_project_fallback_unknown():
    assert track.derive_project("") == "unknown"
    assert track.derive_project(None) == "unknown"


def test_events_path_uses_env_override(tmp_path, monkeypatch):
    target = tmp_path / "ev.jsonl"
    monkeypatch.setenv("TOOL_TRACKER_DATA", str(target))
    assert track._events_path() == target


def test_events_path_is_lazy(tmp_path, monkeypatch):
    monkeypatch.setenv("TOOL_TRACKER_DATA", str(tmp_path / "a.jsonl"))
    first = track._events_path()
    monkeypatch.setenv("TOOL_TRACKER_DATA", str(tmp_path / "b.jsonl"))
    second = track._events_path()
    assert first != second  # frisch gelesen, nicht eingefroren
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/test_track_tool_use.py -k "project or events_path" -v`
Expected: FAIL.

- [ ] **Step 3: Implementieren**

In `hook/track_tool_use.py` ergänzen (oben `import os` und `from pathlib import Path`):
```python
import os
from pathlib import Path


def derive_project(cwd) -> str:
    if not cwd:
        return "unknown"
    name = Path(str(cwd)).name
    return name or "unknown"


def _events_path() -> Path:
    """LAZY: liest Env bei JEDEM Aufruf frisch, nie als Konstante einfrieren."""
    override = os.environ.get("TOOL_TRACKER_DATA")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "data" / "events.jsonl"
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `python -m pytest tests/test_track_tool_use.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hook/track_tool_use.py tests/test_track_tool_use.py
git commit -m "feat: project derivation + lazy event path"
```

---

## Task 5: build_event + main (stdin→JSONL, robustes exit 0)

**Files:**
- Modify: `hook/track_tool_use.py`
- Test: `tests/test_track_tool_use.py`

- [ ] **Step 1: Failing Tests anhängen**

```python
import json
import subprocess
import sys


def test_build_event_has_all_required_fields():
    raw = {"session_id": "s1", "cwd": r"C:\proj\Demo",
           "tool_name": "Bash", "tool_input": {"command": "ls"},
           "hook_event_name": "PreToolUse"}
    ev = track.build_event(raw)
    for k in ("ts_utc", "ts_local", "agent", "tool_name", "session_id",
              "cwd", "project", "is_git_repo", "hook_event", "summary", "schema_v"):
        assert k in ev
    assert ev["agent"] == "claude-code"
    assert ev["tool_name"] == "Bash"
    assert ev["project"] == "Demo"
    assert ev["summary"] == "ls"
    assert ev["schema_v"] == 1


def test_build_event_missing_fields_no_crash():
    ev = track.build_event({})
    assert ev["tool_name"] == "unknown"
    assert ev["project"] == "unknown"
    assert ev["summary"] == ""


def _run_hook(stdin_text, env_extra):
    env = dict(os.environ, **env_extra)
    return subprocess.run([sys.executable, str(HOOK)], input=stdin_text,
                          capture_output=True, text=True, env=env)


def test_main_appends_valid_jsonl(tmp_path):
    target = tmp_path / "ev.jsonl"
    raw = json.dumps({"session_id": "s", "cwd": r"C:\x\Proj",
                      "tool_name": "Read", "tool_input": {"file_path": r"C:\x\Proj\a.py"},
                      "hook_event_name": "PreToolUse"})
    r = _run_hook(raw, {"TOOL_TRACKER_DATA": str(target)})
    assert r.returncode == 0
    line = target.read_text(encoding="utf-8").strip()
    ev = json.loads(line)
    assert ev["tool_name"] == "Read"
    assert ev["project"] == "Proj"


def test_main_broken_stdin_exits_zero(tmp_path):
    target = tmp_path / "ev.jsonl"
    r = _run_hook("this is not json {{{", {"TOOL_TRACKER_DATA": str(target)})
    assert r.returncode == 0  # nie blockieren


def test_main_appends_not_overwrites(tmp_path):
    target = tmp_path / "ev.jsonl"
    raw = json.dumps({"session_id": "s", "cwd": "x", "tool_name": "Glob",
                      "tool_input": {"pattern": "*.py"}, "hook_event_name": "PreToolUse"})
    _run_hook(raw, {"TOOL_TRACKER_DATA": str(target)})
    _run_hook(raw, {"TOOL_TRACKER_DATA": str(target)})
    assert len(target.read_text(encoding="utf-8").strip().splitlines()) == 2
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/test_track_tool_use.py -k "event or main" -v`
Expected: FAIL.

- [ ] **Step 3: `build_event` + `main` implementieren**

In `hook/track_tool_use.py` ergänzen (oben `import json, sys`, `from datetime import datetime, timezone`):
```python
import json
import sys
from datetime import datetime, timezone

AGENT = "claude-code"
SCHEMA_V = 1


def build_event(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    cwd = raw.get("cwd", "")
    tool_name = raw.get("tool_name") or "unknown"
    tool_input = raw.get("tool_input") or {}
    now = datetime.now(timezone.utc)
    is_git = False
    try:
        is_git = bool(cwd) and (Path(str(cwd)) / ".git").exists()
    except Exception:
        is_git = False
    return {
        "ts_utc": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
        "ts_local": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "agent": AGENT,
        "tool_name": tool_name,
        "session_id": raw.get("session_id", ""),
        "cwd": cwd,
        "project": derive_project(cwd),
        "is_git_repo": is_git,
        "hook_event": raw.get("hook_event_name", "PreToolUse"),
        "summary": build_summary(tool_name, tool_input),
        "schema_v": SCHEMA_V,
    }


def main() -> int:
    try:
        data = sys.stdin.read()
        raw = json.loads(data) if data.strip() else {}
        ev = build_event(raw)
        path = _events_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Tracking darf NIE die Arbeit stören
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `python -m pytest tests/test_track_tool_use.py -v`
Expected: PASS (alle).

- [ ] **Step 5: Commit**

```bash
git add hook/track_tool_use.py tests/test_track_tool_use.py
git commit -m "feat: build_event + main (stdin to jsonl, never-block)"
```

---

## Task 6: Geteilter Loader (analysis/_load.py)

**Files:**
- Create: `analysis/_load.py`
- Test: `tests/test_load.py`

- [ ] **Step 1: Failing Test schreiben**

`tests/test_load.py`:
```python
import importlib.util
import json
from pathlib import Path

LOADER = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
_spec = importlib.util.spec_from_file_location("_load", LOADER)
load = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(load)


def _write(tmp_path, rows):
    p = tmp_path / "ev.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def test_load_skips_broken_lines(tmp_path):
    p = tmp_path / "ev.jsonl"
    p.write_text('{"tool_name":"Bash","agent":"claude-code"}\nNOT JSON\n', encoding="utf-8")
    evs = load.load_events(p)
    assert len(evs) == 1


def test_filter_by_agent_and_project(tmp_path):
    p = _write(tmp_path, [
        {"agent": "claude-code", "project": "A", "ts_utc": "2026-06-01T10:00:00.000Z"},
        {"agent": "codex", "project": "A", "ts_utc": "2026-06-01T10:00:00.000Z"},
        {"agent": "claude-code", "project": "B", "ts_utc": "2026-06-01T10:00:00.000Z"},
    ])
    assert len(load.load_events(p, agent="claude-code")) == 2
    assert len(load.load_events(p, project="A")) == 2


def test_filter_since(tmp_path):
    p = _write(tmp_path, [
        {"ts_utc": "2026-05-01T10:00:00.000Z", "agent": "x", "project": "P"},
        {"ts_utc": "2026-06-02T10:00:00.000Z", "agent": "x", "project": "P"},
    ])
    assert len(load.load_events(p, since="2026-06-01")) == 1


def test_missing_file_returns_empty(tmp_path):
    assert load.load_events(tmp_path / "nope.jsonl") == []
```

- [ ] **Step 2: Test laufen lassen, Fehlschlag bestätigen**

Run: `python -m pytest tests/test_load.py -v`
Expected: FAIL.

- [ ] **Step 3: `analysis/_load.py` implementieren**

```python
"""Geteilter JSONL-Loader für report.py und dashboard.py."""
import json
from pathlib import Path


def load_events(path, agent=None, project=None, since=None):
    path = Path(path)
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if agent and ev.get("agent") != agent:
                continue
            if project and ev.get("project") != project:
                continue
            if since and str(ev.get("ts_utc", "")) < since:
                continue
            out.append(ev)
    return out
```

- [ ] **Step 4: Test laufen lassen, Erfolg bestätigen**

Run: `python -m pytest tests/test_load.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/_load.py tests/test_load.py
git commit -m "feat: shared jsonl loader with filters"
```

---

## Task 7: CLI-Report (analysis/report.py)

**Files:**
- Create: `analysis/report.py`

- [ ] **Step 1: Implementieren** (kein Unit-Test — reine Ausgabe; Smoke-Test in Step 2)

```python
"""CLI-Report über Tool-Usage-Events.
Usage: python analysis/report.py [--agent A] [--project P] [--since YYYY-MM-DD] [--data PFAD]"""
import argparse
from collections import Counter
from pathlib import Path

from _load import load_events  # gleiches Verzeichnis

DEFAULT = Path(__file__).resolve().parents[1] / "data" / "events.jsonl"


def _bar(n, maxn, width=30):
    return "█" * (round(width * n / maxn) if maxn else 0)


def _section(title):
    print(f"\n\033[96m── {title} ─────────────────\033[0m")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent")
    ap.add_argument("--project")
    ap.add_argument("--since")
    ap.add_argument("--data", default=str(DEFAULT))
    a = ap.parse_args()

    evs = load_events(a.data, agent=a.agent, project=a.project, since=a.since)
    if not evs:
        print("Keine Events gefunden.")
        return

    ts = sorted(e.get("ts_utc", "") for e in evs)
    print(f"\033[1mTool-Usage Report\033[0m  —  {len(evs)} Events")
    print(f"Zeitraum: {ts[0]}  →  {ts[-1]}")

    _section("Top-Tools")
    tools = Counter(e.get("tool_name", "?") for e in evs)
    mx = max(tools.values())
    for name, n in tools.most_common(15):
        print(f"  {name:<22} {n:>5} {_bar(n, mx)}")

    _section("Events pro Projekt")
    for name, n in Counter(e.get("project", "?") for e in evs).most_common(10):
        print(f"  {name:<22} {n:>5}")

    _section("Events pro Tag (letzte 14)")
    days = Counter(e.get("ts_local", "")[:10] for e in evs)
    for day in sorted(days)[-14:]:
        print(f"  {day}  {days[day]:>5} {_bar(days[day], max(days.values()))}")

    _section("Aktivität pro Stunde")
    hours = Counter(int(e.get("ts_local", " " * 11 + '00')[11:13] or 0)
                    for e in evs if len(e.get("ts_local", "")) >= 13)
    mxh = max(hours.values()) if hours else 0
    for h in range(24):
        print(f"  {h:02d}h {hours.get(h,0):>5} {_bar(hours.get(h,0), mxh)}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke-Test mit Fixture-Daten**

```bash
cd "C:/Users/domes/AI/Hooks-bau/tool-usage-tracker"
python -c "import json,os; os.makedirs('tmp',exist_ok=True); open('tmp/ev.jsonl','w',encoding='utf-8').write('\n'.join(json.dumps({'ts_utc':'2026-06-02T09:0%d:00.000Z'%i,'ts_local':'2026-06-02 09:0%d:00'%i,'agent':'claude-code','tool_name':t,'project':'Demo','summary':'x'}) for i,t in enumerate(['Bash','Read','Edit','Bash','Grep'])))"
python analysis/report.py --data tmp/ev.jsonl
```
Expected: Report mit 5 Events, Top-Tools zeigt Bash=2.

- [ ] **Step 3: tmp aufräumen + Commit**

```bash
rm -rf tmp
git add analysis/report.py
git commit -m "feat: CLI report"
```

---

## Task 8: HTML-Dashboard (analysis/dashboard.py) + vendored Chart.js

**Files:**
- Create: `analysis/dashboard.py`
- Create: `vendor/chart.umd.min.js`

- [ ] **Step 1: Chart.js v4 lokal vendoren**

```bash
cd "C:/Users/domes/AI/Hooks-bau/tool-usage-tracker"
mkdir -p vendor
curl -L -o vendor/chart.umd.min.js https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js
python -c "import pathlib; s=pathlib.Path('vendor/chart.umd.min.js').stat().st_size; print('bytes:',s); assert s>100000, 'Download fehlgeschlagen'"
```
Expected: Datei > 100 KB. (Wird inline ins HTML gebettet → Dashboard offline-fähig.)

- [ ] **Step 2: `analysis/dashboard.py` implementieren**

```python
"""Self-contained HTML-Dashboard über Tool-Usage-Events.
Usage: python analysis/dashboard.py [--data PFAD] [--out PFAD] [--agent A] [--project P] [--since D]"""
import argparse
import json
from collections import Counter
from pathlib import Path

from _load import load_events

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "events.jsonl"
DEFAULT_OUT = ROOT / "dashboard.html"
CHARTJS = ROOT / "vendor" / "chart.umd.min.js"

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _aggregate(evs):
    tools = Counter(e.get("tool_name", "?") for e in evs)
    projects = Counter(e.get("project", "?") for e in evs)
    days = Counter(e.get("ts_local", "")[:10] for e in evs if e.get("ts_local"))
    # Heatmap Stunde x Wochentag
    heat = [[0] * 24 for _ in range(7)]
    for e in evs:
        tl = e.get("ts_local", "")
        if len(tl) >= 13:
            try:
                from datetime import datetime
                d = datetime.strptime(tl[:10], "%Y-%m-%d")
                heat[d.weekday()][int(tl[11:13])] += 1
            except Exception:
                pass
    return tools, projects, days, heat


def build_html(evs):
    tools, projects, days, heat = _aggregate(evs)
    chartjs = CHARTJS.read_text(encoding="utf-8") if CHARTJS.exists() else ""
    day_keys = sorted(days)
    kpis = {
        "total": len(evs),
        "uniq_tools": len(tools),
        "active_days": len(days),
        "top_tool": tools.most_common(1)[0][0] if tools else "—",
    }
    data = {
        "tools": dict(tools.most_common(15)),
        "projects": dict(projects.most_common(10)),
        "days": {k: days[k] for k in day_keys},
        "heat": heat,
        "weekdays": WEEKDAYS,
    }
    return _TEMPLATE.replace("/*CHARTJS*/", chartjs) \
        .replace("/*DATA*/", json.dumps(data)) \
        .replace("/*KPI*/", json.dumps(kpis))


_TEMPLATE = r"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>Tool-Usage Dashboard</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono&family=Outfit:wght@400;600&display=swap');
:root{--bg:#0a0e14;--card:#121821;--fg:#c5d1de;--accent:#39d0d8;--accent2:#f7768e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:'Outfit',sans-serif;padding:24px}
h1{font-family:'JetBrains Mono',monospace;color:var(--accent);letter-spacing:1px}
.kpis{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}
.kpi{background:var(--card);border:1px solid #1e2733;border-radius:10px;padding:16px 24px;min-width:140px}
.kpi .v{font-family:'JetBrains Mono',monospace;font-size:28px;color:var(--accent)}
.kpi .l{font-size:12px;opacity:.7;text-transform:uppercase;letter-spacing:1px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.card{background:var(--card);border:1px solid #1e2733;border-radius:10px;padding:16px}
.card h2{font-family:'JetBrains Mono',monospace;font-size:14px;color:var(--accent2);margin:0 0 12px}
.full{grid-column:1/3}
canvas{max-height:300px}
</style></head><body>
<h1>▮ TOOL-USAGE COMMAND CENTER</h1>
<div class="kpis" id="kpis"></div>
<div class="grid">
  <div class="card"><h2>Top-Tools</h2><canvas id="cTools"></canvas></div>
  <div class="card"><h2>Top-Projekte</h2><canvas id="cProj"></canvas></div>
  <div class="card full"><h2>Aktivität über Zeit</h2><canvas id="cDays"></canvas></div>
  <div class="card full"><h2>Heatmap — Stunde × Wochentag</h2><canvas id="cHeat"></canvas></div>
</div>
<script>/*CHARTJS*/</script>
<script>
const D=/*DATA*/, K=/*KPI*/;
const AC='#39d0d8', AC2='#f7768e', GRID='#1e2733', FG='#c5d1de';
Chart.defaults.color=FG; Chart.defaults.borderColor=GRID;
document.getElementById('kpis').innerHTML=[['Total Events',K.total],['Unique Tools',K.uniq_tools],['Aktive Tage',K.active_days],['Top-Tool',K.top_tool]].map(([l,v])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
new Chart(cTools,{type:'bar',data:{labels:Object.keys(D.tools),datasets:[{data:Object.values(D.tools),backgroundColor:AC}]},options:{indexAxis:'y',plugins:{legend:{display:false}}}});
new Chart(cProj,{type:'bar',data:{labels:Object.keys(D.projects),datasets:[{data:Object.values(D.projects),backgroundColor:AC2}]},options:{indexAxis:'y',plugins:{legend:{display:false}}}});
new Chart(cDays,{type:'line',data:{labels:Object.keys(D.days),datasets:[{data:Object.values(D.days),borderColor:AC,backgroundColor:'rgba(57,208,216,.15)',fill:true,tension:.3}]},options:{plugins:{legend:{display:false}}}});
const pts=[];D.heat.forEach((row,d)=>row.forEach((v,h)=>{if(v)pts.push({x:h,y:d,r:Math.min(4+v*2,20)})}));
new Chart(cHeat,{type:'bubble',data:{datasets:[{data:pts,backgroundColor:'rgba(57,208,216,.5)'}]},options:{plugins:{legend:{display:false}},scales:{x:{min:-.5,max:23.5,title:{display:true,text:'Stunde'}},y:{min:-.5,max:6.5,ticks:{callback:v=>D.weekdays[v]||''}}}}});
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--agent")
    ap.add_argument("--project")
    ap.add_argument("--since")
    a = ap.parse_args()
    evs = load_events(a.data, agent=a.agent, project=a.project, since=a.since)
    Path(a.out).write_text(build_html(evs), encoding="utf-8")
    print(f"Dashboard geschrieben: {a.out}  ({len(evs)} Events)")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Smoke-Test (Dashboard generiert valides HTML mit Daten)**

```bash
cd "C:/Users/domes/AI/Hooks-bau/tool-usage-tracker"
python -c "import json,os; os.makedirs('tmp',exist_ok=True); open('tmp/ev.jsonl','w',encoding='utf-8').write('\n'.join(json.dumps({'ts_utc':'2026-06-02T09:0%d:00.000Z'%i,'ts_local':'2026-06-02 09:0%d:00'%i,'agent':'claude-code','tool_name':t,'project':'Demo','summary':'x'}) for i,t in enumerate(['Bash','Read','Edit','Bash','Grep'])))"
python analysis/dashboard.py --data tmp/ev.jsonl --out tmp/dash.html
python -c "h=open('tmp/dash.html',encoding='utf-8').read(); assert 'Chart' in h and 'COMMAND CENTER' in h and len(h)>100000, 'HTML unvollständig'; print('OK', len(h), 'bytes')"
```
Expected: `OK <bytes>` (Chart.js eingebettet → > 100 KB).

- [ ] **Step 4: tmp aufräumen + Commit**

```bash
rm -rf tmp
git add analysis/dashboard.py vendor/chart.umd.min.js
git commit -m "feat: HTML dashboard with inline Chart.js"
```

---

## Task 9: install.md + echter End-to-End-Smoke-Test

**Files:**
- Create: `install.md`

- [ ] **Step 1: `install.md` schreiben**

```markdown
# Installation — tool-usage-tracker

Hook in `~/.claude/settings.json` (oder settings.local.json) unter `PreToolUse`
einhängen. **Achtung:** Hooks laden erst bei Claude-Code-Neustart.

```json
{
  "PreToolUse": [
    {
      "matcher": "*",
      "hooks": [
        {
          "type": "command",
          "command": "python \"C:\\Users\\domes\\AI\\Hooks-bau\\tool-usage-tracker\\hook\\track_tool_use.py\"",
          "timeout": 10
        }
      ]
    }
  ]
}
```

Danach Claude neu starten. Prüfen mit `/hooks`. Auswertung:
- `python analysis/report.py`
- `python analysis/dashboard.py` → `dashboard.html` öffnen
```

- [ ] **Step 2: End-to-End-Smoke-Test gegen das ECHTE Hook-Skript**

Simuliert, was Claude Code dem Hook via stdin schickt (gegen tmp-Datei, NICHT data/):
```bash
cd "C:/Users/domes/AI/Hooks-bau/tool-usage-tracker"
echo '{"session_id":"smoke","cwd":"C:\\Users\\domes\\AI\\Hooks-bau","tool_name":"Bash","tool_input":{"command":"git status --short api_key=leakme123"},"hook_event_name":"PreToolUse"}' | TOOL_TRACKER_DATA=tmp_e2e.jsonl python hook/track_tool_use.py
python -c "import json; ev=json.loads(open('tmp_e2e.jsonl',encoding='utf-8').readline()); print(ev); assert ev['tool_name']=='Bash'; assert '‹redacted›' in ev['summary']; assert 'leakme' not in ev['summary']; print('E2E OK — secret redacted')"
rm -f tmp_e2e.jsonl
```
Expected: `E2E OK — secret redacted`, exit 0.

> Windows-PowerShell-Variante (falls Bash-Env-Inline nicht greift): Env vorher
> setzen — `$env:TOOL_TRACKER_DATA="tmp_e2e.jsonl"; Get-Content stdin... ` —
> oder den Test über das Bash-Tool laufen lassen (POSIX-Env-Inline funktioniert dort).

- [ ] **Step 3: Volle Test-Suite final laufen lassen**

Run: `python -m pytest -v`
Expected: alle Tests PASS (test_track_tool_use.py + test_load.py).

- [ ] **Step 4: CHANGELOG aktualisieren + Commit + Push**

```bash
cd "C:/Users/domes/AI/Hooks-bau/tool-usage-tracker"
git add install.md docs/CHANGELOG.md
git commit -m "docs: install guide + e2e verified"
git push
```

- [ ] **Step 5: Manuelle Abnahme durch User**

Hook in echte `~/.claude/settings.json` eintragen (Snippet aus install.md),
Claude Code neu starten, ein paar Tools nutzen, dann `python analysis/dashboard.py`
und `dashboard.html` ansehen. (Dieser Schritt erfordert Claude-Neustart und
liegt beim User.)

---

## Verifikation gegen Spec (Self-Review)

- §3 Architektur (3 Einheiten) → Tasks 2-5 (hook), 6 (_load), 7 (report), 8 (dashboard). ✓
- §5 Event-Schema (11 Pflichtfelder + schema_v) → Task 5, `test_build_event_has_all_required_fields`. ✓
- §6 Sanitisierung (120-Limit, Redaction, Pfad-Kürzung, MCP-leer) → Tasks 2-3, Tests. ✓
- §7.1 CLI-Report (Top-Tools/Projekt/Tag/Stunde, Filter) → Task 7. ✓
- §7.2 HTML-Dashboard (KPI + 4 Charts, Chart.js inline, Dark-Theme) → Task 8. ✓
- §8 Tests + Daten-Isolation (lazy _events_path, tmp_path) → Tasks 4-6, alle Tests nutzen TOOL_TRACKER_DATA/tmp_path. ✓
- §9 Installation → Task 9 (install.md). ✓
- Privates Git-Repo + Remote-Push → Task 1 (+ Push in Task 9). ✓
```
