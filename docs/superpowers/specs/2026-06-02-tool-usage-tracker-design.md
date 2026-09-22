# Tool-Usage-Tracker — Design (Spec)

**Datum:** 2026-06-02
**Status:** Approved (Brainstorming abgeschlossen)
**Ort:** `C:\Users\<user>\AI\Hooks-bau\tool-usage-tracker\`

## 1. Zweck

Ein Claude-Code-Hook, der bei **jeder** Tool-Anwendung (PreToolUse) ein Event
aufzeichnet — wer (Agent), wann, welches Tool, wo (Projekt). Die Daten werden
append-only als JSONL gespeichert und können per CLI-Report und per
self-contained HTML-Dashboard grafisch ausgewertet werden.

Erste Iteration: **nur Claude Code**. Das Event-Schema ist aber von Anfang an
agent-agnostisch (`agent`-Feld, `schema_v`), damit Codex & andere Agents später
nur einen Adapter brauchen, der ins selbe JSONL-Format schreibt — ohne
Schema-Bruch.

## 2. Nicht-Ziele (YAGNI)

- **Kein** PostToolUse-Hook in Iteration 1 → keine Dauer/Erfolg/Fehler-Messung.
- **Kein** Blockieren/Validieren von Tools. Der Hook entscheidet nie
  (`permissionDecision`), er beobachtet nur.
- **Kein** Logging-Daemon / Batching. Reines append-on-event.
- **Kein** interaktives Server-Dashboard (Streamlit/Dash) — evtl. Iteration 2.
- **Kein** Datei-*Inhalt* wird je gespeichert, nur Pfade/Befehls-Prefixe.

## 3. Architektur

Drei klar getrennte Einheiten:

| Einheit | Datei(en) | Verantwortung | Pfad |
|---|---|---|---|
| **Hot-Path** | `hook/track_tool_use.py` | stdin lesen → sanitisieren → 1 JSONL-Zeile anhängen → `exit 0` | schreibt |
| **Cold-Path** | `analysis/report.py`, `analysis/dashboard.py` | JSONL lesen → CLI-Report / HTML-Dashboard | liest |
| **Speicher** | `data/events.jsonl` | append-only Event-Log | Daten |

### Ordnerstruktur

```
Hooks-bau\
├── README.md                          # Sammelindex aller Hooks dieses Workspace
└── tool-usage-tracker\
    ├── CLAUDE.md                      # projekt-spez. Konventionen (Regel 13)
    ├── HOW-TO-USE.md                  # Wegweiser User + Agent
    ├── install.md                     # exakter settings.json-Snippet
    ├── docs\
    │   ├── PROJECT.md  CAPABILITIES.md  ARCHITECTURE.md  CHANGELOG.md
    │   └── superpowers\specs\         # dieses Design-Doc
    ├── hook\
    │   └── track_tool_use.py
    ├── analysis\
    │   ├── report.py                  # CLI-Report
    │   └── dashboard.py               # HTML-Dashboard (Dark-Theme)
    ├── data\
    │   └── events.jsonl               # (entsteht zur Laufzeit)
    └── tests\
        └── test_track_tool_use.py
```

## 4. Datenfluss (Hot-Path)

```
Claude Code ──PreToolUse(JSON via stdin)──▶ track_tool_use.py
                                              ├─ stdin lesen + json.loads
                                              ├─ Felder extrahieren
                                              ├─ tool_input → summary (sanitisiert)
                                              ├─ Projektname/Git aus cwd ableiten
                                              ├─ 1 Zeile an events.jsonl anhängen (atomar)
                                              └─ exit 0  (NIE deny, NIE blockieren)
```

Das gesamte Skript läuft in einem `try/except`, das bei **jedem** Fehler still
`exit 0` macht. Leitprinzip: *Tracking darf niemals die Arbeit stören.* Lieber
ein verlorenes Event als ein blockiertes oder verzögertes Tool.

## 5. Event-Schema (eine JSONL-Zeile)

```json
{
  "ts_utc": "2026-06-02T07:57:03.123Z",
  "ts_local": "2026-06-02 09:57:03",
  "agent": "claude-code",
  "tool_name": "Bash",
  "session_id": "abc123",
  "cwd": "C:\\Users\\domes\\AI\\Hooks-bau",
  "project": "Hooks-bau",
  "is_git_repo": false,
  "hook_event": "PreToolUse",
  "summary": "git status --short",
  "schema_v": 1
}
```

**Pflichtfelder** (immer vorhanden, ggf. mit Fallback-Wert): `ts_utc`,
`ts_local`, `agent`, `tool_name`, `session_id`, `cwd`, `project`,
`is_git_repo`, `hook_event`, `summary`, `schema_v`.

- `agent`: fix `"claude-code"` in Iteration 1 (späterer Adapter setzt anderen Wert).
- `project`: letzter Pfad-Bestandteil von `cwd`; Fallback `"unknown"`.
- `is_git_repo`: existiert `<cwd>\.git`? (billiger Check).
- `schema_v`: `1` — erlaubt spätere Migration.

## 6. Sanitisierung `tool_input` → `summary`

Sicherheits-/Privatsphäre-kritisch. Regeln **vor** dem Schreiben:

| Tool | `summary` enthält | Schutz |
|---|---|---|
| Bash | erste ~120 Zeichen von `command` | Secret-Redaction (s.u.) |
| Read/Write/Edit/NotebookEdit | `file_path` | gekürzt auf Dateiname + 2 Parent-Ordner |
| Grep/Glob | `pattern` (gekürzt) | Längenlimit |
| Task/Agent | `description` | Längenlimit |
| WebFetch/WebSearch | `url` / `query` (gekürzt) | Längenlimit |
| MCP-Tools (`mcp__*`) | nur `tool_name`, **kein** input | konservativ |
| Fallback (unbekannt) | `""` | im Zweifel nichts |

**Harte Regeln:**
1. **Längenlimit:** `summary` wird auf max. **120 Zeichen** gekürzt (mit `…`).
2. **Secret-Redaction (Regex, vor dem Kürzen):** Ersetze Treffer durch `‹redacted›`:
   - `sk-[A-Za-z0-9]{10,}` (OpenAI/Anthropic-artige Keys)
   - `ghp_[A-Za-z0-9]{20,}` (GitHub-Tokens)
   - `(api[_-]?key|token|password|secret|auth)\s*[=:]\s*\S+` (case-insensitive)
   - `Bearer\s+\S+`
3. **Kein Datei-Inhalt:** Nur Pfade/Befehle/Patterns, niemals `content`/`new_string`.

## 7. Auswertung (Cold-Path)

### 7.1 `analysis/report.py` (CLI)
Liest `events.jsonl`, gibt im Terminal aus:
- Gesamt-Events + Zeitraum (erstes/letztes Event)
- Top-Tools mit Häufigkeit + ASCII-Balken
- Events pro Projekt
- Events pro Tag (letzte 14 Tage) + Aktivität pro Stunde (0–23h)
- Filter-Flags: `--agent`, `--project`, `--since YYYY-MM-DD`, `--data <pfad>`

### 7.2 `analysis/dashboard.py` (HTML)
Liest dieselbe JSONL, schreibt **self-contained** `dashboard.html`:
- Dark-Theme / Command-Center-Stil, JetBrains Mono + Outfit
- KPI-Kacheln: Total Events, Unique Tools, Aktive Tage, Top-Tool
- Charts (Chart.js **inline eingebettet**, keine CDN-/Internet-Abhängigkeit zur Laufzeit):
  - Tool-Häufigkeit (Bar)
  - Aktivität über Zeit / Timeline (Line)
  - Top-Projekte (Bar)
  - Heatmap Stunde × Wochentag
- Öffnen per Doppelklick, funktioniert offline.

## 8. Tests (TDD, pytest)

Fokus Hot-Path. Jeder Test nutzt eine **eigene tmp_path-Event-Datei** —
schreibt NIE in die echte `data/events.jsonl`.

- Secret-Redaction greift (`sk-…`, `api_key=…`, `Bearer …` → `‹redacted›`)
- Längenlimit (120) eingehalten
- Pfad-Kürzung (Read/Write/Edit) korrekt
- Unbekanntes Tool / fehlende Felder → kein Crash, gültige Zeile
- Kaputtes stdin (kein JSON) → `exit 0`, keine Exception nach außen
- MCP-Tool → kein input im `summary`
- JSONL-Zeile ist valides JSON + enthält alle Pflichtfelder

### Daten-Isolation (globale Regel 3)
Der Event-Pfad ist im Hook eine **lazy Funktion** `_events_path()`, die bei
jedem Aufruf die Env-Var `TOOL_TRACKER_DATA` frisch liest (Fallback:
`<projekt>\data\events.jsonl`). **Kein** Modul-Level-Konstanten-Pfad — so
überlebt die Isolation Reload-Teardowns und Tests können die echte Datei nicht
überschreiben.

## 9. Installation

Eintrag in `~/.claude/settings.json` unter `PreToolUse`, `matcher: "*"`:

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

Wird **nicht** automatisch eingehängt — Snippet in `install.md`, User entscheidet
und startet Claude Code neu (Hooks laden nur bei Session-Start).

## 10. Build-Reihenfolge (für den Plan)

1. Projekt-Skelett (CLAUDE.md, HOW-TO-USE.md, docs/, README.md).
2. TDD: `test_track_tool_use.py` → `track_tool_use.py` (Hot-Path, Sanitizer, lazy Pfad).
3. `analysis/report.py` (CLI).
4. `analysis/dashboard.py` (HTML, Chart.js inline).
5. `install.md` + manueller Smoke-Test (echtes stdin-JSON durchschicken).
