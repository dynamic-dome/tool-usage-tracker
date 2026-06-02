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

### Self-Tracking filtern (aus Live-Installation, 2026-06-02)
Der Hook trackt aktuell auch die eigenen Auswertungs-Aufrufe (`report.py`,
`dashboard.py`) sowie generell Tool-Nutzung *im* tool-usage-tracker-Projekt
selbst. Das verrauscht die Statistik leicht.

Optionen:
- Im Hook: Events überspringen, deren `summary`/`command` `report.py` oder
  `dashboard.py` enthält, ODER deren `project == "tool-usage-tracker"`.
- Alternativ erst beim Lesen (Loader/Report) filtern, damit die Rohdaten
  vollständig bleiben — sauberer, da der Hot-Path simpel bleibt.

**Empfehlung:** beim Lesen filtern (optionales `--exclude-self`-Flag in report/
dashboard), Rohdaten unangetastet lassen.

### Lehre: eingebettetes JS browser-/node-prüfen (Bug 2026-06-02)
Das HTML-Dashboard renderte zunächst leer (KPIs + Charts), obwohl die Daten
korrekt eingebettet waren — ein fehlendes `}` in der cHeat-Chart-Config (`_TEMPLATE`)
brach das gesamte JavaScript ab (`Unexpected token ')'`). Der Smoke-Test prüfte
nur Byte-Größe + Platzhalter-Ersetzung, NICHT die JS-Syntax.

**How to apply:** Beim Generieren von HTML mit eingebettetem JS den Script-Block
extrahieren und mit `node --check` validieren (oder per Playwright laden +
Console-Errors prüfen). Byte-Count beweist nur, dass Chart.js drin ist, nicht
dass das Script läuft. → Idee: Smoke-Test in dashboard.py-Workflow um node-check
ergänzen.

## Iteration 2 (aus Design-Doc §2 Nicht-Ziele)
- PostToolUse-Hook für Dauer/Erfolg/Fehler (Korrelation via session_id+tool)
- Codex- & andere-Agent-Adapter (schreiben ins selbe JSONL, anderer `agent`-Wert)
- Interaktives Server-Dashboard (Streamlit/Dash)
