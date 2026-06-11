# HOW-TO-USE — tool-usage-tracker

## Was ist das?
Hooks, die bei jeder Claude-Code- oder Codex-Tool-Anwendung Events nach
`data/events.jsonl` schreiben:
- **PreToolUse** (`hook/track_tool_use.py`) — eine `phase:"pre"`-Zeile pro Tool-Start
  (was, wo, sanitisiertes Summary).
- **PostToolUse/-Failure** (`hook/track_tool_post.py`) — eine `phase:"post"`-Zeile pro
  Tool-Abschluss: `ok` (true/false) + sanitisierter `error`-Text. Über `session_id`+
  `tool_name` werden Pre und Post zu Spans gepaart → Dauer (`duration_ms`) und Erfolg.

## Installation
Siehe `install.md`.
- Codex: projektlokale `.codex/hooks.json` reviewen/trusten (`/hooks`).
- Claude Code: Snippet in `~/.claude/settings.json` einhängen, Claude neu starten.

## Auswertung
- CLI: `python analysis/report.py` (Flags: --agent --project --since --exclude-self --data)
- HTML (statisch): `python analysis/dashboard.py` → öffnet `dashboard.html` (auch --exclude-self)
- Live-Server (interaktiv): `python analysis/server.py` (Flags: --data, --port; Default-Port 8770)
- Quality-Signal (C5-Kopplung agentic-os): `python -X utf8 analysis/quality_signal.py
  [--project P] [--since D] [--limit N] [--top N] [--out DATEI]` — Tool-Fehlerrate pro
  Session als JSON-Vertrag (schema_v 1: `overall` + `sessions` mit tool_calls/failures/
  success_rate/top_failing_tools/mutating_failures; Zählbasis nur gepaarte Spans mit
  bekanntem ok). Konsument: agentic-os `quality-gate` ruft das Skript auf und wertet
  success_rate/failures der jüngsten Session(s) als Quality-Signal.
  VORAUSSETZUNG: der `PostToolUseFailure`-Hook in settings.json (seit 2026-06-11) —
  PostToolUse feuert nur bei Erfolg; ohne den Failure-Hook ist die Rate konstant 1.0.

## Live-Dashboard
`python analysis/server.py` starten, dann im Browser `http://127.0.0.1:8770` öffnen
(127.0.0.1, **nicht** localhost — Regel 16). Stdlib-`http.server`, an 127.0.0.1 gebunden.
- Drei Tabs:
  - **Analytics** (Default; Top-Tools, Fehlerrate, Aktivität/Zeit, Pfad-Treemap +
    Heat-Baum). Sind Kosten-/Token-Daten vorhanden (siehe unten), erscheinen zusätzlich
    Σ-Kosten/Σ-Tokens-KPIs und ein **Kosten-pro-Tool**-Panel — sonst bleiben sie ausgeblendet.
  - **Timeline** (Waterfall): Spans pro Session in **Turns** gruppiert (Pause-Heuristik,
    adaptiver Schwellwert im Kopf angezeigt). Jeder Turn hat eine eigene Zeitachse:
    x-Position = Offset ab Turn-Start, Breite ∝ Dauer; gleichzeitige Spans gestapelt;
    gestrichelt = ungepaart.
  - **Compare** (B-3): Vergleichstabelle **pro Agent** oder **pro Session** (umschaltbar) —
    Tool-Calls, Fehlversuche, Erfolgsrate, Gesamtdauer, Risk-Verteilung, mutierende Aktionen,
    Gesamtkosten. Bester Wert je Metrik grün, schlechtester rot markiert.
- **Refresh** ist manuell (Button) — kein Auto-Polling.
- Filter im Header: `agent`, `project`, `since` (YYYY-MM-DD) und Checkbox `exclude_self`
  (blendet die eigenen Tracker-/Report-Aufrufe aus). Ctrl-C im Terminal stoppt den Server.

## Optionale Add-ons (stdlib-only-Kern bleibt unberührt)
Diese Module sind nachgelagert; sie laufen NIE im Hot-Path und der Kern braucht weiter
nur die Stdlib.

- **Kosten/Token pro Span (A-1):** Der Loader liest optionale Felder `input_tokens`,
  `output_tokens`, `cache_read_tokens` und `cost_usd` aus den Events, falls vorhanden, und
  speist daraus die Kosten-KPIs + das Compare-Tab. Fehlen die Felder, ist alles ausgeblendet.
- **OTLP-Metrics einlesen (A-1):** `python analysis/ingest_otlp.py <otlp-metrics.jsonl> [out.json]`
  parst Claude-Code-OTLP-Metrics (console- + OTLP/JSON-Format) zu `usage_by_session.json`
  (Default-Output). Wichtig: OTLP-Metrics tragen nur `session.id`, **keine** `tool_use_id` —
  Kosten sind daher nur **pro Session** zuordenbar, nicht pro Tool-Call.
- **Token im Abo-Modell einlesen (ccusage):** `python analysis/ingest_ccusage.py [out.json]`
  liest Claude Codes lokale Session-JSONL aus `~/.claude/projects/<hash>/*.jsonl` (Env
  `CLAUDE_PROJECTS_DIR` überschreibt den Pfad) und schreibt `data/tokens_by_request.json`
  (Default). **Kein API-Key, keine Telemetrie-Aktivierung nötig** — dieselbe Quelle wie das
  Tool `ccusage`. Token werden **pro Turn (`requestId`)** erfasst; eine Offline-Preistabelle
  liefert den **rechnerischen USD-Gegenwert** (im Abo zahlt man die Flatrate, nicht diese Summe).
  Sobald die Datei existiert, reichert der Live-Server (`server.py`) die Spans automatisch an
  (Env `TOOL_TRACKER_TOKENS` überschreibt den Pfad) und das Kosten-/Token-Panel erscheint.
  Workflow: `python analysis/ingest_ccusage.py` → `python analysis/server.py --port 8770`.
- **Ad-hoc-SQL via DuckDB (B-6):** `python analysis/sql.py "<SQL>" [data.jsonl]` — beliebiges
  SQL gegen zwei Views: `events` (rohe Zeilen) und `spans` (in SQL gepaart). Window-Functions
  (p50/p95 …) inklusive. Optionales Add-on: `pip install duckdb`; ohne DuckDB endet die CLI
  sauber mit Exit 3 + Installationshinweis (kein Crash, Kern-Suite bleibt grün).
- **OTLP-Trace-Export (Teil C):** `analysis/otlp_export.py` ist ein Library-Modul:
  `build_resource_spans(spans)` mappt gepaarte Spans auf OTLP/JSON (gen_ai.*-konform, Trace =
  Session, Span = Tool-Call, deterministische IDs); `export(spans, endpoint=…)` POSTet optional
  an einen lokalen Collector (Default `http://127.0.0.1:4318/v1/traces`, z.B. Jaeger / Grafana
  LGTM / OTel-Collector). Nicht erreichbarer Collector → `False`, kein Crash.

## Architektur / Felder / Sanitisierung
Siehe `docs/ARCHITECTURE.md` und das Design-Doc
`docs/superpowers/specs/2026-06-02-tool-usage-tracker-design.md`.
