# ARCHITECTURE
Hot-Path: hook/track_tool_use.py — stdin JSON → sanitize → append JSONL → exit 0.
Cold-Path: analysis/_load.py (Loader) → report.py (CLI) / dashboard.py (HTML).
Speicher: data/events.jsonl (append-only). Pfad via lazy _events_path() + Env TOOL_TRACKER_DATA.
Event-Schema + Sanitizer-Regeln: siehe Design-Doc in docs/superpowers/specs/.
