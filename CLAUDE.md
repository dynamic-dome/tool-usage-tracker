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
