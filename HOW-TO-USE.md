# HOW-TO-USE — tool-usage-tracker

## Was ist das?
Hooks, die bei jeder Claude-Tool-Anwendung Events nach `data/events.jsonl` schreiben:
- **PreToolUse** (`hook/track_tool_use.py`) — eine `phase:"pre"`-Zeile pro Tool-Start
  (was, wo, sanitisiertes Summary).
- **PostToolUse/-Failure** (`hook/track_tool_post.py`) — eine `phase:"post"`-Zeile pro
  Tool-Abschluss: `ok` (true/false) + sanitisierter `error`-Text. Über `session_id`+
  `tool_name` werden Pre und Post zu Spans gepaart → Dauer (`duration_ms`) und Erfolg.

## Installation
Siehe `install.md` — Snippet in `~/.claude/settings.json` einhängen, Claude neu starten.

## Auswertung
- CLI: `python analysis/report.py` (Flags: --agent --project --since --exclude-self --data)
- HTML (statisch): `python analysis/dashboard.py` → öffnet `dashboard.html` (auch --exclude-self)
- Live-Server (interaktiv): `python analysis/server.py` (Flags: --data, --port; Default-Port 8770)

## Live-Dashboard
`python analysis/server.py` starten, dann im Browser `http://127.0.0.1:8770` öffnen
(127.0.0.1, **nicht** localhost — Regel 16). Stdlib-`http.server`, an 127.0.0.1 gebunden.
- Zwei Tabs: **Analytics** (Default; Top-Tools, Fehlerrate, Aktivität/Zeit, Pfad-Treemap +
  Heat-Baum) und **Timeline** (Span-Flow pro Session, Balkenbreite ∝ Dauer, gestrichelt =
  ungepaart).
- **Refresh** ist manuell (Button) — kein Auto-Polling.
- Filter im Header: `agent`, `project`, `since` (YYYY-MM-DD) und Checkbox `exclude_self`
  (blendet die eigenen Tracker-/Report-Aufrufe aus). Ctrl-C im Terminal stoppt den Server.

## Architektur / Felder / Sanitisierung
Siehe `docs/ARCHITECTURE.md` und das Design-Doc
`docs/superpowers/specs/2026-06-02-tool-usage-tracker-design.md`.
