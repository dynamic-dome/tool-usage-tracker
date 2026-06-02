# Hook Integration and Product Analysis - 2026-06-02

## Scope

Ziel dieser Runde war:

- Projekt erkunden und Funktionsweise verstehen.
- Codex-/Claude-Hook-Integration praktisch testen.
- Dashboard, weitere Hook-Anwendungen und Produkt-/Architekturentwicklung kritisch analysieren.
- Subagent-Perspektiven zusammenfuehren und als Projektdokumentation festhalten.

## Projektmodell

`tool-usage-tracker` ist ein append-only Observability-Tool fuer Agent-Toolnutzung.

- Hot-Path:
  - `hook/track_tool_use.py` verarbeitet `PreToolUse`.
  - `hook/track_tool_post.py` verarbeitet `PostToolUse` / Failure-Signale.
  - Beide schreiben JSONL und muessen immer `exit 0` liefern.
- Speicher:
  - Default `data/events.jsonl`.
  - Tests/Smokes per lazy Env-Override `TOOL_TRACKER_DATA`.
- Cold-Path:
  - `analysis/_load.py` laedt, filtert, paart Pre/Post zu Spans und berechnet Aggregate.
  - `analysis/report.py` ist aktuell noch rohere Event-Statistik.
  - `analysis/dashboard.py` erzeugt ein statisches Event-Dashboard.
  - `analysis/server.py` liefert das Live-Dashboard mit Span-Pairing, Fehler-/Dauerwerten und Timeline.

Wichtig: Das Produkt sollte langfristig primaer in "Spans" denken. Pre/Post-Events sind Rohmaterial.

## Lokale Verifikation

Durchgefuehrt:

- `tests/conftest.py` gesucht: existiert nicht.
- Test-Isolation geprueft: Tests nutzen `tmp_path` und/oder `TOOL_TRACKER_DATA`; keine DB im Projekt.
- Destruktiv-Sweep in `tests hook analysis`: keine Treffer fuer `DELETE FROM`, `DROP TABLE`, `TRUNCATE`, produktive `data/events.jsonl`-Writes.
- `.codex/hooks.json` per `python -m json.tool` validiert.
- Windows-Hook-Command geprueft: `py -3` verfuegbar (`Python 3.14.5`).
- Test-Suite: `python -X utf8 -m pytest -q` -> `78 passed`.
- Isolierter Codex-Payload-Smoke:
  - Pre und Post mit `model:"gpt-5.5"` wurden als `agent:"codex"` geschrieben.
  - `tool_use_id` blieb konsistent.
  - Secret in Bash-Command wurde zu `‹redacted›`.
  - Post schrieb `ok:true`.

## Echte Codex-Exec-Integration

Ein verschachtelter Lauf wurde mit temporarem `TOOL_TRACKER_DATA` gestartet:

```powershell
codex exec --ephemeral --dangerously-bypass-hook-trust -C . --json "Run exactly one harmless shell command..."
```

Beobachtung:

- Codex CLI 0.136.0 startete.
- Der Shell-Command `Get-Location` wurde erfolgreich ausgefuehrt.
- Es entstand keine temporare Hook-Eventdatei.

Interpretation:

- Die Hook-Skripte selbst funktionieren.
- Die projektlokale `.codex/hooks.json` wurde in diesem `codex exec`-Lauf nicht ausgefuehrt.
- Das ist ein Integrationsrisiko: "Config vorhanden" ist nicht gleich "Codex feuert Hooks live".

Plausible Ursachen:

- `codex exec` laedt projektlokale Hook-Dateien anders oder gar nicht.
- Pre/PostToolUse-Coverage ist in Codex noch nicht fuer alle Toolpfade gleich.
- Project-/user-level Hook-Discovery hat bekannte Kanten; in der lokalen `~/.codex/config.toml` war kein Trust-State fuer `C:\Users\domes\AI\Hooks-bau\tool-usage-tracker\.codex\hooks.json` sichtbar.

Externe Primaerquellen, die diese Risikoklasse stuetzen:

- openai/codex Issue #24211: user-level `PostToolUse` wird teils nicht registriert.
- openai/codex Issue #20204: ungleichmaessige `PreToolUse`-Coverage.
- openai/codex Issue #17794 / #16732: Toolhandler feuern Hook-Events nicht konsistent.

## Dashboard-Befund

Aktueller Stand:

- Static Dashboard (`analysis/dashboard.py`) zaehlt Events.
- Live Dashboard (`analysis/server.py`) arbeitet mit Spans.
- Live-Dashboard hat Analytics- und Timeline-Tab, Filter fuer agent/project/since/exclude_self, Top-Tools, Fehlerrate, Aktivitaet, Pfad-Treemap und Heat-Baum.

Kritischer Punkt:

- Datenvertrauen ist nicht sichtbar genug. Bei vielen Legacy-/unpaired Events koennen Erfolgsrate und Dauerwerte schnell zu sicher wirken.

Priorisierte Verbesserungen:

1. Pairing-Vertrauen oben anzeigen:
   - Total Events
   - Spans
   - Paired
   - Unpaired
   - Pairing-Rate
2. Pairing-Metadaten im Loader:
   - `pairing_method: "tool_use_id" | "fifo" | "orphan"`
   - `orphan_kind: "pre_without_post" | "post_without_pre"`
3. Fehlerrate sortieren und mit Sample-Size zeigen:
   - z.B. `Bash - 3/42`.
4. Timeline begrenzen und bedienbarer machen:
   - newest-first
   - last 20 sessions
   - Filter "nur Fehler/offen"
   - Detailpanel bei Klick
5. Filter-Ergonomie:
   - Enter/change triggert Refresh.
   - Reset-Button.
   - Presets: Heute / 7 Tage / 30 Tage.
   - sichtbare Filter-Chips.
6. Status-/Diagnostikzeile:
   - last refreshed
   - Datenpfad
   - gelesene Zeilen
   - valide Events
   - uebersprungene JSON-Zeilen
   - aktive Query

## Hook-Ideen Nach Anwendung

Empfohlene Reihenfolge: zuerst abgeleitete Klassifizierung, nicht neue riskante Hot-Path-Logik.

### P1: Bash-/CLI-Klassifizierung

Viele Tools sind schon als Bash-Kommandos sichtbar. Daraus sollten optionale Felder abgeleitet werden:

- `app`: `git`, `github`, `cloudflare`, `notebooklm`, `python`, `node`, `local-cli`
- `operation`: semantisches Subcommand, z.B. `pr view`, `wrangler deploy`
- `intent`: `read`, `write`, `deploy`, `test`, `auth`, `unknown`
- `risk`: `low`, `medium`, `high`
- `mutating`: bool

Matcher-Beispiele:

- `git status|diff|show|log|add|commit|push|pull`
- `gh pr|issue|api|workflow|run|release`
- `wrangler deploy|pages deploy|dev|tail|secret|d1|kv|r2`
- `notebooklm create|add|list|use|delete|status`
- `python|pytest|ruff|mypy|uv|pip|pnpm|npm|node`

### P1: Browser/Playwright

Nutzen: Frontend-Debugging und UI-Verifikation.

Sichere Felder:

- `browser_action`: `navigate`, `click`, `fill`, `screenshot`, `evaluate`
- `url_host`: Host only
- `url_kind`: `localhost`, `external`, `file`
- `selector_hash`: optional, kein Rohselector
- `screenshot`: bool
- `eval_kind`: ohne Script-Inhalt

### P2: GitHub/GH

Nuetzlich fuer PR-/CI-/Issue-Arbeit.

- `resource_type`: `pr`, `issue`, `workflow`, `run`, `api`
- `resource_id`: Nummer oder Hash, kein Body
- `method`: bei `gh api`
- `mutating`: true bei `create`, `comment`, `review`, `merge`, `POST/PATCH/DELETE`

### P2: Cloudflare/Wrangler

Wichtig wegen Deploy- und Secret-Risiko.

- `cloudflare_product`: `workers`, `pages`, `d1`, `kv`, `r2`, `secrets`
- `environment`: aus `--env`
- `mutating`: true bei deploy/secret/write
- SQL und Secret-Werte nicht loggen.

### P2: NotebookLM

Nur Metadaten, keine Quelleninhalte.

- `notebook_id_hash`
- `source_kind`: `url`, `text`, `file`
- `source_host`: nur URL-Host
- `operation`
- `mutating`

### P3: Gmail/Drive

Nur opt-in und maximal anonymisiert.

- Keine Betreffzeilen.
- Keine Queries.
- Keine Mail-/Doc-Inhalte.
- Nur `operation`, `resource_kind`, `resource_id_hash`, `mutating`, `privacy_level:"restricted"`.

## Architektur-/Produkt-Backlog

P0:

1. `analysis/report.py` auf Span-Modell erweitern.
   - Default: Calls/Spans, Erfolgsrate, avg/median/p95 je Tool.
   - Flag `--raw-events` fuer alte Sicht.
   - Section `Unpaired`.
   - Section `Failures`.
2. Post-Events optional mit direktem Kontext anreichern, wenn Payload ihn bereits liefert:
   - `cwd`, `project`, `summary`, `hook_event`.
   - Keine extra FS-Checks im Post-Hot-Path.

P1:

3. `analysis/server.py` Template auslagern nach z.B. `analysis/dashboard_template.html`.
4. JS-/Browser-Smoke einbauen:
   - Script extrahieren und `node --check`.
   - Optional Playwright-Load gegen `/` und Console-Errors pruefen.
5. Fehleranalyse:
   - Top Errors.
   - Failure by tool/project/session.
   - Error-Prefix-Clustering, aber raw sanitized first line erhalten.

P2:

6. Speicherstrategie:
   - Rotation/Archiv/Compaction.
   - Optional Index-Cache.
   - Pairing ueber Dateigrenzen beachten.
7. Optionales Auto-Refresh im Live-Dashboard:
   - default aus.
   - klarer Status, kein unkontrolliertes Polling.
8. Agent-Adapter als Normalisierungsschicht erst nach mehr realen Payloads.

## Dokumentationsdrift

Gefunden:

- `docs/PROJECT.md` und `docs/CAPABILITIES.md` sind knapper/veralteter als `HOW-TO-USE.md` und `docs/CHANGELOG.md`.
- `docs/TODO.md` enthaelt bereits den richtigen P1: Template aus `server.py` auslagern.
- `AGENTS.md` hat im Projekttext "Codex und Codex" statt "Claude Code und Codex"; die Datei ist aktuell untracked und war schon vor dieser Runde Worktree-Drift.

## Empfohlene Naechste Schritte

Stand nach Folgeiteration:

- Span-Report, Pairing-Metadaten und Dashboard-Pairing-KPIs wurden umgesetzt.
- Offen bleiben insbesondere interaktive Codex-Hook-Discovery und die Template-Auslagerung.

1. Projekt-Hook-Discovery fuer Codex klaeren:
   - neue interaktive Codex-Session im Projekt starten
   - `/hooks` oeffnen
   - projektlokale `.codex/hooks.json` trusten
   - echten Shell-Call ausloesen
   - pruefen, ob `TOOL_TRACKER_DATA` oder `data/events.jsonl` Pre/Post enthaelt
2. Vor groesserer UI-Arbeit:
   - `server.py` Template auslagern
   - JS-Check-Test einfuehren
