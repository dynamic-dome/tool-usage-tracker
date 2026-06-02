# PROJECT — tool-usage-tracker
**Zweck:** Tool-Usage-Tracking fuer Claude Code und Codex via PreToolUse/PostToolUse-Hooks.
**Status:** Schema v2 mit Pre/Post-Events, Span-Pairing, CLI-Report, statischem Dashboard und lokalem Live-Server.
**Leitplanken:** Hot-Path blockiert nie, schreibt append-only JSONL, sanitisiert Summaries/Errors und nutzt `TOOL_TRACKER_DATA` als lazy Env-Override.
**Aktueller Integrationsstand:** Hook-Skripte und Codex-Payload-Smokes funktionieren; echter `codex exec`-Smoke fuehrte hier keinen projektlokalen Hook aus. Details: `docs/reports/2026-06-02-hook-integration-and-product-analysis.md`.
