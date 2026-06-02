# TODO — tool-usage-tracker

## Deferred aus Code-Reviews (bewusst außerhalb Iteration-1-Scope)

### Sanitizer: breitere Secret-Formate (aus Task-2-Review, 2026-06-02)
Das aktuelle Redaction-Set ist ein bewusster Starter-Satz. Folgende Formate
schlüpfen aktuell durch und sollten in einer späteren Iteration ergänzt werden:
- AWS Access Keys (`AKIA[0-9A-Z]{16}`)
- JWTs (`eyJ...` — drei base64url-Segmente)
- PEM Private-Key-Blöcke (`-----BEGIN ... PRIVATE KEY-----`)
- Slack-Tokens (`xox[baprs]-...`)
- GitHub `gho_` / `github_pat_` (aktuell nur `ghp_`)
- Generische lange Hex/Base64-Tokens (32+ Zeichen)

**Warum deferred:** Iteration 1 zielt auf den häufigsten Fall (sk-/ghp_/Bearer/
assignments). Breitere Abdeckung = eigener Task mit eigenen Tests.

### Sanitizer-Tests: Negativ-/Komposition-Fälle (aus Task-2-Review)
- `clip` no-op für kurze Strings + strip-Verhalten
- `redact→clip`-Komposition: bleibt ≤120 UND redacted
- Negativ-Fall: benigner String bleibt unangetastet

## Iteration 2 (aus Design-Doc §2 Nicht-Ziele)
- PostToolUse-Hook für Dauer/Erfolg/Fehler (Korrelation via session_id+tool)
- Codex- & andere-Agent-Adapter (schreiben ins selbe JSONL, anderer `agent`-Wert)
- Interaktives Server-Dashboard (Streamlit/Dash)
