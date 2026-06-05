# PROJECT — tool-usage-tracker
**Zweck:** Tool-Usage-Tracking fuer Claude Code und Codex via PreToolUse/PostToolUse-Hooks.
**Status:** Schema v2 mit Pre/Post-Events, Span-Pairing, CLI-Report, statischem Dashboard und lokalem Live-Server (Analytics-/Timeline-/Compare-Tab). Kontext-Felder `git_branch`/`file_ext` (A-5), Kosten/Token pro Span + OTLP-Metrics-Ingest (A-1), Run-Comparison Claude Code ↔ Codex (B-3), optionales DuckDB-SQL-Add-on (B-6) und OTLP-Trace-Export (Teil C). Suite: 203 passed / 6 skipped (2026-06-05).
**Leitplanken:** Hot-Path blockiert nie, schreibt append-only JSONL, sanitisiert Summaries/Errors und nutzt `TOOL_TRACKER_DATA` als lazy Env-Override.
**Aktueller Integrationsstand:** Hook-Skripte und Codex-Payload-Smokes funktionieren; echter `codex exec`-Smoke fuehrte hier keinen projektlokalen Hook aus. Details: `docs/reports/2026-06-02-hook-integration-and-product-analysis.md`.
