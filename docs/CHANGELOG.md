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
