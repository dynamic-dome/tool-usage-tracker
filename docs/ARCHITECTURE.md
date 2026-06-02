# ARCHITECTURE
Hot-Path: hook/track_tool_use.py + hook/track_tool_post.py — stdin JSON → sanitize → append JSONL → exit 0.
Cold-Path: analysis/_load.py (Loader) → report.py (CLI) / dashboard.py (HTML).
Speicher: data/events.jsonl (append-only). Pfad via lazy _events_path() + Env TOOL_TRACKER_DATA.
Hook-Registrierung: Claude Code über ~/.claude/settings.json; Codex über .codex/hooks.json oder ~/.codex/hooks.json.
Event-Schema + Sanitizer-Regeln: siehe Design-Doc in docs/superpowers/specs/.
