# CHANGELOG
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
