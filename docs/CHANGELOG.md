# CHANGELOG
## 2026-06-04
- **A-5 — Kontext-Felder im PreToolUse-Event** (`5942166`+`a4527bf`, TDD):
  - `git_branch` aus `.git/HEAD` (reiner Dateiread, **kein** subprocess → Hot-Path-sicher;
    bounded `read_bytes(256)`, strikter `refs/heads/`-Check, Worktree-`.git`-Datei via
    gitdir-Pointer aufgelöst, Detached HEAD → 7-Zeichen-Hash).
  - `file_ext` (lowercase Endung) für Datei-Tools (`Read`/`Write`/`Edit`/`NotebookEdit`).
  - Codex-Verifier fand 3 reale Edge-Cases (unbounded read, refs/tags|remotes, Worktree) →
    alle per TDD gefixt.
- **B-1 — Trace-Waterfall pro Turn** (`13aa10b` Spec, `7dc1b16` Plan, `b13beb8..e83a9c0`):
  - Timeline-Tab als Turn-Waterfall: Turn-Erkennung via global-adaptiver Gap-Heuristik
    (`compute_turn_gap_threshold`/`assign_turns` in `_load.py`, median+3·MAD, Klammer 5–120s,
    Fallback 30s); Server reicht `turn_index`+`turn_gap_ms` durch; `renderTimeline` mit echter
    Zeitachse pro Turn + vertikalem Lane-Stapeln (`turnLayout` Node-getestet).
  - Holistic-Review-Funde gefixt: Seam-Bug (git_branch/file_ext erreichten den Span nie wg.
    Loader-Whitelist → in `_paired_span`/`_unpaired_pre_span` durchgereicht) + `esc()`-Quote-XSS
    (Double-Quotes wurden nicht escaped → `title=`-Attribut-Ausbruch geschlossen).
- **A-1 — Token/Kosten pro Span** (`5dfb28f`):
  - `_load.py` `_cost()` liest optionale `input/output/cache_read_tokens` + `cost_usd`
    (None-Defaults, bool-reject), durchgereicht in gepaarte/orphan/unpaired Spans; neue
    `cost_breakdown(spans)` → Summen + `cost_by_tool`/`cost_by_agent` + `has_cost_data`.
  - `server.py`: `cost`-Block im `spans_payload`. Dashboard: konditionale Σ-Kosten/Σ-Tokens-KPIs
    + Kosten-pro-Tool-Panel (nur bei `has_cost_data`).
  - `analysis/ingest_otlp.py` (NEU, stdlib-only): parst Claude-Code-OTLP-Metrics (console +
    OTLP/JSON) → `usage_by_session.json`. Kosten nur **pro Session** (Metrics tragen keine
    `tool_use_id`). Hot-Path/Hooks unberührt.
- **B-3 — Run-Comparison Claude Code ↔ Codex** (`162436b`):
  - `_load.py` `comparison(spans, key='agent'|'session_id')` aggregiert tool_calls, paired,
    failures, retries, success_rate, total_duration_ms, Risk-Verteilung, mutating_count,
    total_cost_usd. `server.py`: `comparison`-Block (by_agent + by_session).
  - Dashboard: neuer Compare-Tab (umschaltbar Agent/Session), best/worst-Markierung pro Metrik;
    reine Tabelle (kein Chart nötig), Re-Render ohne Refetch via `lastData`.
- **B-6 — DuckDB-Ad-hoc-SQL-Layer** (`ce2890b`):
  - `analysis/sql.py`: `query(sql, data_path)` (View `events`) + `query_spans(sql, data_path)`
    (zusätzliche View `spans`, pre/post in SQL gepaart). DuckDB **lazy** importiert → Modul
    crasht nie beim Import; fehlt duckdb, `is_available()`→False und CLI endet mit Exit 3 +
    Installationshinweis. Pfad inline eingebettet aber SQL-escaped (`_sql_str`, Quote-Verdopplung
    gegen Injection). Kern bleibt stdlib-only.
- **Teil C — OTLP-Trace-Exporter** (`1d81831`):
  - `analysis/otlp_export.py` (Library-Modul, stdlib-only): `build_resource_spans(spans)` mappt
    gepaarte Spans → OTLP/JSON `resourceSpans` (gen_ai.*-konform, Trace = Session, Span =
    Tool-Call, deterministische 32-/16-hex IDs, ok→UNSET / ok=False→ERROR); `export(spans,
    endpoint=…)` POSTet optional an einen lokalen Collector (Default `:4318/v1/traces`),
    Graceful-Fallback bei nicht erreichbarem Collector. Hot-Path unberührt.
- **S-01 — Secret-Redaction erweitert** (`6e3190a`, TDD): Stripe-**Test**-Keys (`[sr]k_test_…`),
  GitLab PAT (`glpat-…`), Google OAuth2 (`ya29.…`, auf `ya29.` verankert gegen Teilwort-FP);
  rein additive Patterns im Hot-Path, exit-0-Garantie unangetastet.
- **Verifikation (2026-06-05):** Suite selbst gefahren → **203 passed / 6 skipped**.
  Test-Isolation snapshot-bewiesen (`data/events.jsonl`-Wachstum stammt nur vom live laufenden
  Tracker-Hook auf eigene Tool-Calls, nicht aus Tests). Nur S-01 fasst den Hot-Path an
  (additiv), die vier Feature-Commits sind durchgehend Cold-Path (`analysis/`).

## 2026-06-02
- Projekt-Setup, Design-Doc + Plan.
- Iteration 1 komplett: PreToolUse-Hook (`hook/track_tool_use.py`) mit Sanitizer
  (clip + Secret-Redaction inkl. sk-proj/quoted secrets), per-Tool Summary-Builder,
  lazy Event-Pfad (`TOOL_TRACKER_DATA`), build_event + never-block main.
- Auswertung: geteilter Loader (`analysis/_load.py`), CLI-Report (`analysis/report.py`),
  HTML-Dashboard (`analysis/dashboard.py`) mit inline Chart.js (offline-fähig).
- 24 Tests grün. End-to-End gegen echtes Hook-Skript verifiziert (Secret redacted, exit 0).
- install.md mit Settings-Snippet + Auswertungs-/Test-Anleitung.
- Fix: fehlendes `}` in cHeat-Chart-Config (`_TEMPLATE`) brach das gesamte
  Dashboard-JS ab (leere KPIs/Charts trotz korrekter Daten). Dashboard jetzt
  browser-verifiziert (Playwright: 0 Console-Errors, alle 4 Charts + KPIs rendern).
- Iteration-1-Backlog: breitere Secret-Formate (AWS `AKIA/ASIA`, JWT `eyJ…`, PEM,
  Slack `xox[baprs]-`, GitHub `gho_/ghu_/ghs_/ghr_`+`github_pat_`), Sanitizer-Negativ-/
  Komposition-Tests, `--exclude-self`-Filter (report+dashboard), `report.py`
  cp1252-stdout-Fix.
- Iteration 2 komplett:
  - Schema auf `schema_v:2` + neues Feld `phase` (`"pre"`/`"post"`) — Pre- und
    Post-Zeilen lassen sich eindeutig trennen.
  - **PostToolUse/-Failure-Hook** (`hook/track_tool_post.py`): zeichnet `ok` +
    sanitisierten `error` pro Tool-Abschluss auf. Erfolg primär aus `hook_event_name`,
    Fallback `exit_code`. Wiederverwendet `redact`/`clip`/`_events_path` aus dem
    Pre-Hook. Never-block, exit 0.
  - **`pair_events()` + Aggregate** in `analysis/_load.py`: paart Pre+Post über
    `session_id`+`tool_name` zu Spans (`duration_ms`, `ok`, `error`); plus
    `success_rate_by`, `duration_stats_by`, `path_activity`.
  - **Live-Server** (`analysis/server.py`, Stdlib `http.server`, an 127.0.0.1
    gebunden, Default-Port 8770): zwei Tabs (Analytics-Grid + Timeline), manueller
    Refresh, Filter agent/project/since/exclude_self. Chart.js inline aus `vendor/`.
  - 59 Tests grün. Live-End-to-End des Post-Hooks ist an die Install-Zeit verlagert
    (siehe install.md — echter Tool-Call → Pre+Post-Zeile in `events.jsonl` prüfen).
- Codex-Portierung:
  - Projektlokale `.codex/hooks.json` für Codex `PreToolUse`/`PostToolUse`.
  - Hooks erkennen Codex-Payloads über `model` und schreiben `agent:"codex"`.
  - `apply_patch` bekommt eine sanitisierte Summary; Claude-Code-Verhalten bleibt
    unverändert. 78 Tests grün.
- Analyse-/Produktbericht ergänzt:
  - `docs/reports/2026-06-02-hook-integration-and-product-analysis.md` dokumentiert
    Projektmodell, lokale Verifikation, echten `codex exec`-Smoke, Dashboard-Kritik,
    Hook-Ideen nach Anwendung und priorisierten Architektur-Backlog.
  - `docs/PROJECT.md` und `docs/CAPABILITIES.md` auf Schema-v2/PostToolUse/Live-Server
    aktualisiert.
- P0 aus Analysebericht teilweise umgesetzt:
  - `pair_events()` liefert Pairing-Metadaten (`pairing_method`,
    `pairing_confidence`, `orphan_kind`) plus `pairing_summary()`.
  - `/api/spans` liefert Pairing-Diagnostics; Live-Dashboard zeigt Total Events,
    Spans, Paired, Unpaired und Pairing-Rate.
  - `analysis/report.py` nutzt standardmäßig Spans mit Pairing-/Dauer-/Erfolg-/
    Failure-Sektionen; `--raw-events` behält die alte Roh-Event-Sicht.
- Codex-Hook-Discovery-Smoke dokumentiert:
  - `docs/reports/2026-06-02-codex-hook-discovery-smoke.md` haelt fest, dass
    `codex exec --dangerously-bypass-hook-trust` den Shell-Toolcall ausfuehrt,
    aber in diesem Modus keine projektlokale Hook-Eventdatei erzeugt.
  - Simulierte Codex-Payloads bleiben funktionsfaehig; der interaktive `/hooks`-
    Trust-Smoke bleibt als separater manueller Check offen.
- Live-Dashboard-Template ausgelagert:
  - `analysis/dashboard_template.html` enthaelt jetzt HTML/CSS/JS.
  - `analysis/server.py` bleibt auf HTTP/API + Template-Laden fokussiert.
  - Server-Tests pruefen, dass das Template als externes Asset existiert.
- Dashboard-Smokes automatisiert:
  - `analysis/dashboard_smoke.py` extrahiert Script-Bloecke, prueft sie mit
    `node --check` und kann bei vorhandenen Node-Playwright-Abhaengigkeiten einen
    Browser-Smoke gegen das Live-Dashboard ausfuehren.
  - `tests/test_dashboard_smoke.py` prueft Template-Scripts und skippt Browser-
    Checks sauber, wenn Playwright lokal nicht verfuegbar ist.
- Bash/CLI-App-Klassifizierung ergänzt:
  - `hook/track_tool_use.py` leitet fuer Bash-Kommandos optionale Felder
    `app`, `operation`, `intent`, `risk`, `mutating` ab.
  - Abgedeckt sind u.a. `git`, `gh`, `wrangler`, `notebooklm`, Python-/Node-Tools
    und ein konservativer `local-cli`-Fallback.
  - Tests sichern Claude-Code-/Codex-unabhaengige Event-Erweiterung und verhindern,
    dass Secret-Argumente in Klassifizierungsfelder geraten.
- Node-Playwright fuer Browser-Smokes als Dev-Dependency ergaenzt:
  - `package.json`/`package-lock.json` erfassen `playwright` fuer lokale Smoke-Tests.
  - `node_modules/` ist gitignored; die Python-App und Hooks bleiben stdlib-only.
  - `npm test` fuehrt die Python-Test-Suite aus; `npm run test:dashboard` prueft den
    Dashboard-Smoke inklusive Browser-Load, wenn Playwright verfuegbar ist.
