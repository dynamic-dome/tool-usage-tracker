# TODO — tool-usage-tracker

## Erledigt (2026-06-02, Iteration-1-Backlog abgeräumt)

- ✅ **Breitere Secret-Formate** — AWS (`AKIA/ASIA`), JWT (`eyJ…`), PEM-Private-Key-
  Header, Slack (`xox[baprs]-`), GitHub `gho_/ghu_/ghs_/ghr_` + `github_pat_`.
  Patterns spezifisch-vor-generisch geordnet. 6 neue Tests.
- ✅ **Sanitizer-Negativ-/Komposition-Tests** — `clip` no-op + strip, exakt-am-Limit,
  `redact→clip`-Komposition (≤MAX_LEN UND redacted), Boundary-Leak-Schutz, benigner
  String unangetastet. 5 neue Tests.
- ✅ **`--exclude-self`-Filter** — beim Lesen im geteilten `_load.py` (Rohdaten bleiben
  voll): blendet `project=="tool-usage-tracker"` + `report.py`/`dashboard.py`-Aufrufe
  aus. Flag in report + dashboard. Default off. 3 neue Tests.
- ✅ **report.py cp1252-Crash gefixt** — stdout auf UTF-8 reconfigured (Regel 10);
  `→`/`█` crashten zuvor die Windows-Konsole.

## Deferred aus Code-Reviews (bewusst außerhalb Iteration-1-Scope)

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
- ✅ **PostToolUse/-Failure-Hook** für Dauer/Erfolg/Fehler (`hook/track_tool_post.py`,
  Korrelation via session_id+tool, `pair_events()` in `_load.py`).
- ✅ **Interaktives Server-Dashboard** (`analysis/server.py`, Stdlib `http.server`,
  Analytics- + Timeline-Tab). Statt Streamlit/Dash bewusst Stdlib-only gehalten.
- Codex- & andere-Agent-Adapter (schreiben ins selbe JSONL, anderer `agent`-Wert) —
  noch offen.

## Erledigt (2026-06-02, Folgeiteration)

### Inline-HTML/JS-Template aus server.py auslagern
Erledigt: `analysis/server.py` liest das Live-Dashboard jetzt aus
`analysis/dashboard_template.html`; Chart.js wird weiterhin zur Laufzeit aus `vendor/`
inline ersetzt. Tests prüfen, dass das Template extern liegt.
