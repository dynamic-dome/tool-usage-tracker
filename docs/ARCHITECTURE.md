# ARCHITECTURE
Hot-Path: hook/track_tool_use.py + hook/track_tool_post.py — stdin JSON → sanitize → append JSONL → exit 0.
Cold-Path: analysis/_load.py (Loader: Pairing, Turns, cost_breakdown, comparison) →
  report.py (CLI) / dashboard.py (statisches HTML) / server.py (Live-Dashboard, Analytics/Timeline/Compare).
Optionale Add-ons (nachgelagert, nie im Hot-Path, Kern bleibt stdlib-only):
  - analysis/ingest_otlp.py — Claude-Code-OTLP-Metrics → usage_by_session.json (Kosten pro Session).
  - analysis/sql.py — DuckDB-Ad-hoc-SQL (lazy import; Views events/spans; Exit 3 + Hinweis ohne duckdb).
  - analysis/otlp_export.py — Library-Modul: gepaarte Spans → OTLP/JSON-resourceSpans, optionaler HTTP-Push.
Speicher: data/events.jsonl (append-only). Pfad via lazy _events_path() + Env TOOL_TRACKER_DATA.
Hook-Registrierung: Claude Code über ~/.claude/settings.json; Codex über .codex/hooks.json oder ~/.codex/hooks.json.
Event-Schema + Sanitizer-Regeln: siehe Design-Doc in docs/superpowers/specs/.
