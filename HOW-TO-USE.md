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
