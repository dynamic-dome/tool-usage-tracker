# Design — tool-usage-tracker Iteration 2: Agent Observability

*Datum: 2026-06-02*
*Status: Spec (brainstormed, User-approved je Sektion)*
*Projekt: tool-usage-tracker (`~/AI/Hooks-bau/tool-usage-tracker`, Repo `dynamic-dome/tool-usage-tracker`)*

## 1. Ziel & Motivation

Iteration 1 lieferte reines **PreToolUse-Logging**: was ein Agent tut (Tool + Pfad +
Projekt), wann, in welchem Repo. Iteration 2 erweitert das zur **Observability der
Agent-Bewegungen**: zusätzlich *wie lange* ein Tool-Call dauert, *ob er gelang oder
scheiterte*, und eine grafisch ansprechende Aufbereitung — besonders der Ordnerpfade,
in denen sich die Agenten bewegen.

Leitfragen des Users: nachvollziehbar machen WAS Agenten tun, WIE, WANN, WIE LANGE
sie brauchen, WIE GUT — plus schöne visuelle Darstellung von Pfaden, Tools, Aktivität.

## 2. Scope

### Drin
1. **PostToolUse-Hook** (`hook/track_tool_post.py`): zweite JSONL-Zeile pro Tool-Call
   mit Erfolg/Fehler + eigenem Timestamp. Gleiche never-block-Garantie wie der Pre-Hook.
2. **Cold-Path-Paarung** (`_load.py`): `pair_events()` verschmilzt Pre+Post zu „Spans"
   mit Dauer + Erfolg; ungepaarte Events bleiben erhalten, aber markiert.
3. **Live-Server-Dashboard** (`analysis/server.py`): Stdlib-`http.server`, an `127.0.0.1`
   gebunden (Regel 16), liest `events.jsonl`, liefert gefilterte Spans als JSON an ein
   Frontend mit zwei Tabs (Analytics-Grid + Timeline) und manuellem Refresh-Button.
4. **Statischer Generator bleibt** (`analysis/dashboard.py`): als teilbarer Offline-
   Snapshot/Export, auf derselben Datenschicht `_load.py`.

### Ausdrückliche Nicht-Ziele (spätere Iterationen)
- **Token-Tracking** — Hooks sehen keine Token-Zahlen; das braucht einen eigenen
  Parser der Claude-Code-Transcripts (`~/.claude/projects/<hash>/*.jsonl`, `usage`-Felder).
  Eigene Spec, korreliert später per `session_id`.
- **Codex-Adapter** — das Schema ist agent-agnostisch (`agent`, `schema_v`); die Tür
  bleibt offen. Codex hat kein Pre/PostToolUse-System; der Adapter wird ein eigener
  Konverter, sobald geklärt ist, welche Telemetrie Codex real ausgibt.
- **Retry-/Korrektur-Muster-Erkennung** — Heuristik „gleiches Tool+Input mehrfach kurz
  hintereinander = Nachbessern". Wertvoll, aber eigene Iteration.
- **Auto-Poll / SSE-Streaming** — Live-Aktualisierung jenseits des manuellen Buttons.
  Bewusst offen gehalten als möglicher späterer Ausbau.

## 3. Datenmodell

### Schema-Version 2

Das `events.jsonl` bekommt ein neues Feld `phase` (`"pre"` | `"post"`). Bestehende
`schema_v: 1`-Events haben kein `phase` — der Loader behandelt deren Fehlen als
`"pre"`, sodass Altdaten verlustfrei lesbar bleiben (kein Bruch, keine Migration nötig).

**Pre-Event** (`phase: "pre"`, sonst unverändert ggü. v1):
```json
{
  "ts_utc": "2026-06-02T10:02:11.034Z", "ts_local": "2026-06-02 12:02:11",
  "agent": "claude-code", "schema_v": 2, "phase": "pre",
  "tool_name": "Bash", "session_id": "abc123", "cwd": "C:\\...\\dual-bridge",
  "project": "dual-bridge", "is_git_repo": true, "hook_event": "PreToolUse",
  "summary": "pytest scripts/"
}
```

**Post-Event** (`phase: "post"`, neu):
```json
{
  "ts_utc": "2026-06-02T10:02:11.374Z", "ts_local": "2026-06-02 12:02:11",
  "agent": "claude-code", "schema_v": 2, "phase": "post",
  "tool_name": "Bash", "session_id": "abc123",
  "ok": false,
  "error": "command not found: pytetst"
}
```

- `ok` (bool): aus `tool_response` abgeleitet. Heuristik pro Tool-Typ (analog
  `build_summary`), bewusst konservativ: kein Error-Flag/keine Exception → `true`;
  Bash non-zero exit, Tool-Error, Read/Edit-Fehler → `false`.
- `error` (str): erste Zeile / erste ~120 Zeichen der Fehlerursache, durch denselben
  `redact()` + `clip()`-Sanitizer wie alle anderen Felder. `""` bei Erfolg. Genug,
  um den Fehlertyp zu erkennen, ohne Secret-/Pfad-Leak oder Riesenzeilen.

### Kein State im Hot-Path

Die **Dauer entsteht nicht im Hook**. Der Post-Hook trägt nur seinen eigenen
Timestamp. Beide Hooks bleiben zustandslos (kein Sidecar, keine tmp-Datei) — die
Verschmelzung passiert ausschließlich im Cold-Path. Das hält die never-block-Garantie
trivial und vermeidet verwaiste State-Einträge / Concurrency-Probleme.

## 4. Cold-Path: Paarung & Aggregation (`_load.py`)

### `pair_events(events) -> list[span]`

Verschmilzt Pre+Post zu Spans:
```json
{
  "tool_name": "Bash", "agent": "claude-code", "session_id": "abc123",
  "project": "dual-bridge", "summary": "pytest scripts/", "cwd": "C:\\...",
  "ts_start": "2026-06-02T10:02:11.034Z", "ts_end": "2026-06-02T10:02:11.374Z",
  "duration_ms": 340, "ok": false, "error": "command not found: pytetst",
  "paired": true
}
```

**Paarungs-Heuristik (bewusste Näherung, hier dokumentiert):**
Claude Code liefert Hooks **keine eindeutige Call-ID**. Daher:
- Gruppiere Events nach `session_id`.
- Pro `tool_name` FIFO: das nächste `post` paart mit dem ältesten noch offenen `pre`
  desselben Tools in derselben Session.
- Korrekt in praktisch allen Fällen, weil Tool-Calls innerhalb eines Turns
  sequenziell-ish verarbeitet werden. Bei dichter Parallelität desselben Tools kann
  die Zuordnung theoretisch verrutschen — die *aggregierten* Dauer-Statistiken bleiben
  davon unberührt (gleiche Menge an Start/End-Paaren).

**Ungepaarte Events (sauberer Umgang, kein Datenverlust):**
- **Pre ohne Post** (Crash, abgebrochener/laufender Call): `paired: false`,
  `duration_ms: null`, `ok: null`. Bleibt sichtbar (z.B. als offener Balken in der
  Timeline), zählt aber NICHT in Dauer-/Erfolgs-Aggregate.
- **Verwaistes Post** (theoretisch): ebenso `paired: false`, robust ignoriert in
  den Aggregaten.

### Aggregat-Helfer (für alle drei Konsumenten)

Rein lesend, setzen auf die vorhandenen Filter (`agent`/`project`/`since`/`exclude_self`)
auf, die VOR der Paarung greifen:
- Erfolgsquote pro Tool / Projekt / Agent / Tag (nur gepaarte Spans).
- Dauer-Verteilung Ø / Median / p95 pro Tool (nur gepaarte Spans).
- Pfad-Aktivität: Call-Count je Pfad-Präfix (`cwd` + `summary`-Pfad), für Treemap
  + Heat-Baum.

## 5. Komponenten & Dashboards

### Gemeinsame Datenschicht — keine Logik-Duplikation

```
events.jsonl
    │
    ▼
_load.py ── load_events() ──► pair_events() ──► aggregate helpers
    │                                                    │
    ├──────────────┬──────────────────┬─────────────────┤
    ▼              ▼                  ▼
report.py     dashboard.py        server.py  (NEU)
(CLI, da)     (statisch, da)      (live, Stdlib http.server)
```

### `analysis/server.py` (NEU)

- Reiner Stdlib-`http.server`, gebunden an **`127.0.0.1`** (Regel 16), Port wählbar.
- Enthält **keine** Aggregationslogik — nur HTTP-Routing + Delegation an `_load.py`.
  Hält die Datei klein und ohne Browser testbar.
- Routen:
  - `GET /` → HTML-Shell mit zwei Tabs + manuellem Refresh-Button.
  - `GET /api/spans?agent=&project=&since=&exclude_self=` → JSON aus `pair_events`.
- Inline-Chart.js (wie statischer Generator), kein Netz-Abruf.
- Manueller Refresh: ein Button lädt `/api/spans` neu und re-rendert. Kein Auto-Poll.

### Tab A — Analytics-Grid (Default)

KPI-Reihe (Calls, Erfolgsquote, Ø/p95-Dauer) · Top-Tools · Aktivität über Zeit ·
Fehlerrate-Trend · **Pfad-Treemap** (Fläche = Call-Count pro Pfad). Klick auf eine
Treemap-Kachel öffnet den **Heat-Baum** als Drill-down (aufklappbarer Datei-Baum mit
Heat-Badges, präzise Pfade bis zur Datei).

### Tab B — Timeline / Flow

Spans als horizontale Balken pro Session, chronologisch: Länge = `duration_ms`,
Farbe = `ok` (grün/rot). Ungepaarte Spans als offene/schraffierte Balken (sichtbar,
aber als „unvollständig" erkennbar). Erzählt den Arbeitsfluss eines Agenten.

### Visuelle Konvention

Bestehendes Dark/Command-Center-Theme (JetBrains Mono + Outfit, Akzente `#39d0d8` /
`#f7768e`). Statischer Generator und Server teilen den Tab-A-Chart-Baustein, wo
möglich, damit die Optik nicht auseinanderdriftet.

## 6. Fehlerbehandlung & Sicherheit

- **Never-block:** Beide Hooks fangen alle Exceptions, exit 0 immer. Tracking darf
  die Arbeit nie stören.
- **Sanitizer:** `error`-Feld läuft durch `redact()` + `clip()` — kein Secret-/Pfad-
  Leak, max. `MAX_LEN`.
- **Daten-Isolation:** Beide Hooks nutzen den lazy `_events_path()` mit
  `TOOL_TRACKER_DATA`-Override. Tests schreiben NIE in `data/events.jsonl`.
- **Server:** nur `127.0.0.1`, kein externer Zugriff; read-only auf `events.jsonl`.

## 7. Teststrategie (TDD)

- **PostToolUse-Hook:** subprocess-E2E gegen das echte Skript (wie Pre-Hook); `ok`-
  Ableitung pro Tool-Typ als Unit-Tests; Sanitizer auf `error` mitgetestet;
  never-block bei kaputtem stdin.
- **`pair_events` + Aggregate:** reine Unit-Tests mit synthetischen Event-Listen —
  korrekte Paarung, Dauer-Berechnung, ungepaarte Pre/Post, FIFO bei
  gleichem-Tool-mehrfach, Schema-v1-Rückwärtskompatibilität (kein `phase`).
- **`server.py`:** Routen liefern korrektes JSON / HTTP-Status ohne echten Browser
  (Test-Client gegen `http.server`-Handler).
- Alles Stdlib, kein Selenium/Playwright nötig. (Embedded-JS-Syntax beim statischen
  Generator weiterhin per `node --check`, vgl. docs/TODO.md.)

## 8. Offene Entscheidungen für die Plan-Phase

- Genaue Tool-für-Tool-Heuristik der `ok`-Ableitung (welche `tool_response`-Felder pro
  Tool-Typ): in der Implementierung gegen reale PostToolUse-Payloads verifizieren
  (Ground-Truth, nicht raten — Regel P006).
- Reihenfolge der Tasks: Hook → Paarung/Aggregate → Server → Tab A → Tab B.
