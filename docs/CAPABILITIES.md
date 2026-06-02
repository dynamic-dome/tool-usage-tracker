# CAPABILITIES
- Aufzeichnen: `PreToolUse` + `PostToolUse` als JSONL (`phase:"pre"`/`"post"`), inklusive `ts_utc`, `ts_local`, `agent`, `tool_name`, `session_id`, `tool_use_id`, `cwd`, `project`, `is_git_repo`, `hook_event`, `summary`, `ok`, `error`, `schema_v`.
- Sanitisierung: 120-Zeichen-Limit, Secret-Redaction, Pfad-Kürzung, kein Datei-Inhalt.
- Pairing: `analysis/_load.py` verschmilzt Pre/Post zu Spans mit `duration_ms`, Erfolg und Fehlertext; exakter Match per `tool_use_id`, FIFO-Fallback fuer Altdaten.
- Auswertung: CLI-Report, statisches HTML-Dashboard und Live-Dashboard (`analysis/server.py`) mit Analytics-/Timeline-Ansicht, Filtern und manueller Refresh-Steuerung.
- Codex: projektlokale `.codex/hooks.json` vorhanden; Payload-Erkennung ueber `model` schreibt `agent:"codex"`. Live-Discovery in `codex exec` ist noch nicht voll bestaetigt.
