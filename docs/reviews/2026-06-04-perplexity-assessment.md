# Perplexity-Assessment — tool-usage-tracker

**Stichtag:** 2026-06-04 · **Reviewer:** Perplexity (Code-Gutachten, am echten Code gemessen)
**Commit:** `00fd9b8` (2026-06-03) · **Methode:** Repo lokal geklont, jede Datei gelesen,
Suite isoliert ausgeführt (`python -X utf8 -m pytest -q tests/`), Hooks live mit Payloads
gefüttert, Datei-Isolation per SHA256/Zeilenzahl vor/nach verifiziert.

> Hinweis zur Umgebung: Die Verifikation lief auf **Linux** (Sandbox), das Produkt zielt auf
> **Windows 11**. Ein Befund (`derive_project`) ist dadurch plattformabhängig — siehe C-01.

---

## 1. Verifikations-Ergebnis (Checkliste, Punkt für Punkt)

| # | Behauptung (Stand 2026-06-04) | Ergebnis | Beleg |
|---|---|---|---|
| 1 | Hot-Path `track_tool_use.py` nie-blockierend (try/except, exit 0, keine permissionDecision) | **BESTÄTIGT** | `main()` Z.229–240: alles in `try/except: pass`, `return 0`. Live getestet: leerer + Müll-stdin → exit 0. Kein `permissionDecision` im Code. |
| 2 | Event-Pfad LAZY mit Env-Override `TOOL_TRACKER_DATA`, nicht als Modul-Konstante | **BESTÄTIGT** | `_events_path()` Z.175–180: liest `os.environ.get("TOOL_TRACKER_DATA")` bei jedem Aufruf; Fallback relativ zu `__file__`. Post-Hook reused dieselbe Funktion (`_pre._events_path()`). |
| 3 | Sanitizer: 120-Zeichen-Limit + Secret-Redaction (AWS/JWT/PEM/Slack/GitHub) | **BESTÄTIGT, mit Lücken** | `MAX_LEN=120` Z.10; `clip()` Z.41–45; `_SECRET_PATTERNS` Z.15–32 deckt PEM, OpenAI `sk-`, GitHub `gh[opusr]_`/`github_pat_`, AWS `AKIA/ASIA`, Slack `xox[baprs]-`, JWT `eyJ…`, generisch key=value + bearer. Live verifiziert. **Fehlend:** Google API-Key (`AIza…`), Stripe (`sk_live_`/`rk_live_`), generische Hex/Base64-Hochentropie, `.env`-Inline-Dumps → siehe S-01. |
| 4 | Stdlib-only im Kern, Chart.js gevendort/inline | **BESTÄTIGT** | Kein `import pandas/matplotlib/flask/numpy` in `hook/` oder `analysis/`. `server.py` nutzt `http.server`. Chart.js aus `vendor/chart.umd.min.js`, inline ersetzt via `/*CHARTJS*/` (server.py Z.99–101, dashboard.py Z.41). |
| 5 | Pre/Post-Pairing per exaktem `tool_use_id`, FIFO nur Fallback | **BESTÄTIGT** | `pair_events()` `_load.py` Z.99–156: Pass 1 Key `(session_id, tool_use_id)` → `method="tool_use_id"`/`confidence="exact"`; Pass 2 FIFO `(session_id, tool_name)` → `method="fifo"`. Reihenfolge korrekt. |
| 6 | PostToolUse Erfolg/Fehler via `tool_response` + `is_error`/`interrupted`/`exit_code` | **BESTÄTIGT** | `_derive_ok_and_error()` `track_tool_post.py` Z.19–62: `tool_response` primär, Fallback `tool_output`/`tool_error`; `is_fail` aus `Failure`-Event ∨ `is_error` ∨ `interrupted` ∨ `exit_code != 0`. `bool`-Guard gegen `exit_code=True/False`-Falle (Z.45). |
| 7 | Codex-Kompatibilität (`.codex/hooks.json`, eigener agent-Wert) | **BESTÄTIGT** | `.codex/hooks.json` mit `commandWindows`/`command` für Pre+Post. `derive_agent()` Z.187–191: `raw.get("model")` → `"codex"`, sonst `"claude-code"`. **Caveat (Doku):** echter `codex exec`-Smoke erzeugte keine projektlokale Hook-Datei (PROJECT.md / report 2026-06-02). |
| 8 | Neue Felder `app/intent/risk/mutating` werden geSCHRIEBEN, aber im Dashboard NICHT ausgewertet | **BESTÄTIGT — größte Lücke** | Geschrieben: `build_event()` Z.224–225 ruft `classify_bash_command()` (live verifiziert: `git push` → `risk:high, mutating:true`). NICHT ausgewertet: `_paired_span()` (`_load.py` Z.61–72) trägt die Felder nicht in den Span; `spans_payload()` (server.py Z.52–63) gibt sie nicht aus; `dashboard_template.html` referenziert sie nirgends; `report.py` hat keine Sektion dafür. → Backlog **B-01 (Sprint 1)**. |
| 9 | LOC-Größenordnung: track_tool_use ~244, _load ~209, übrige ~100–130 | **BESTÄTIGT (exakt)** | `track_tool_use.py`=244, `_load.py`=209, `dashboard.py`=117, `report.py`=129, `server.py`=118, `track_tool_post.py`=100, `dashboard_smoke.py`=111, `dashboard_template.html`=381. |
| 10 | Tests grün (~93 passed / 1 skipped Playwright) | **ABWEICHEND (plattformbedingt)** | 94 Test-Funktionen gesamt. Auf **Linux**: **90 passed, 3 failed, 1 skipped**. Die 3 Failures sind ausschließlich `derive_project`-Tests mit Windows-Pfad-Fixtures (`Path(r"C:\x\Proj").name` liefert auf POSIX den vollen String statt `Proj`). Auf Windows wären es die erwarteten **93 passed / 1 skipped**. → Portabilitäts-Befund **C-01**. |

**Zusätzlicher Isolations-Befund (Pflicht-Gate):** Sentinel-`data/events.jsonl` (2 Zeilen, SHA256
`c6718927…`) war **vor und nach** dem Suite-Lauf byte-identisch. Tests schreiben sauber in
`tmp_path` via `TOOL_TRACKER_DATA`. **Keine Isolationsverletzung.** ✓

---

## 2. Gesamteinschätzung

Reifegrad **produktionsnah für den Single-User-Windows-Einsatz**: Der Hot-Path ist diszipliniert
nie-blockierend, der Sanitizer greift nachweislich, das Pre/Post-Pairing ist zweistufig mit
ehrlichen Confidence-/Orphan-Metadaten, und der Auswerte-Pfad (CLI + statisches HTML + Live-Server)
ist stdlib-only und offlinefähig. **Größte Stärke:** Datenqualität & defensive Robustheit — jeder
Eingabepfad ist gegen Crashes und Secret-Leaks gehärtet, Tests decken Sanitizer-Negativfälle und
Pairing-Kanten ab. **Größtes Risiko:** Die `app/intent/risk/mutating`-Klassifizierung wird
geschrieben, aber **nirgends ausgewertet** — der teuerste Teil (Risiko-/Mutations-Sicht auf
Agent-Aktionen) liegt brach. Sekundär ist `derive_project` nicht plattformportabel, was auf
Linux-CI/Codex 3 Tests rot färbt und falsche `project`-Werte erzeugt.

---

## 3. Bewertung je Dimension (0–10)

### Nützlichkeit / Produktwert — **7/10**
Beantwortet real „welches Tool, wie oft, wie lange, mit welcher Erfolgsrate, in welchem Projekt"
(`report.py` `_span_report` Z.60–100, Timeline im Template Z.267–328). Das fehlende Risk/Mutating-
Reporting (Beleg #8) lässt aber genau die sicherheitsrelevante Frage „welche mutierenden Aktionen
liefen wo" unbeantwortet — der differenzierende Mehrwert fehlt noch.

### Architektur / Modularität — **8/10**
Saubere Hot-/Cold-Path-Trennung; `_load.py` ist die einzige Aggregations-Quelle, `server.py`
delegiert vollständig (Z.2 „enthält KEINE Aggregationslogik"). Post-Hook reused `redact/clip/
_events_path` per `importlib` (track_tool_post.py Z.12–16) statt zu duplizieren. Abzug: `dashboard.py`
(statisch) und `server.py` (live) aggregieren parallel & inkonsistent (statisch ohne Spans/`ok`).

### Robustheit des Hot-Paths — **9/10**
`main()` beider Hooks: `try/except: pass`, `exit 0`, `mkdir(parents, exist_ok)` vor Append
(track_tool_use Z.235). `derive_agent`/`build_event` tolerieren Nicht-Dicts (Z.195–196). Live mit
leerem + Müll-stdin getestet → exit 0. Abzug nur, weil `is_git_repo` einen Filesystem-Stat im
Hot-Path macht (Z.205–208) — zwar in try/except, aber synchroner I/O pro Tool-Call.

### Datenqualität & Sanitizing / Privacy — **8/10**
120-Zeichen-Clip + breite Secret-Patterns, „spezifisch-vor-generisch" geordnet (Kommentar Z.12–14,
verhindert dass key=value die Token zerstückelt). Kein Datei-Inhalt geloggt (nur Pfade/Patterns/
Commands, `build_summary` Z.54–73). Abzug: Provider-Lücken (Google `AIza`, Stripe `sk_live`),
keine Hochentropie-Heuristik → S-01.

### Test-Strategie — **7/10**
94 Tests, Negativ-/Kompositions-Tests für den Sanitizer, Pairing-Kanten (`test_pair_events.py`,
12 Tests), Server-Fehlerpfad (`test_spans_payload_error_does_not_crash_handler`). Isolation
vorbildlich (tmp_path/`TOOL_TRACKER_DATA`, byte-identische Sentinel-Datei). Abzug: 3 Tests sind
nicht plattformportabel (C-01); kein einziger Test deckt die geschriebene Bash-Klassifizierung
im **Auswerte**-Pfad ab (nur im Hook).

### Observability-Auswertbarkeit (Report + Dashboard) — **6/10**
Pairing-Diagnostics, Dauer-Perzentile (`duration_stats_by` p95 Z.190–204), Erfolgsraten, Treemap +
Heat-Baum, Timeline. Aber: kein Risk/Mutating-Cut (#8), keine Zeitaggregation über Tage/Wochen im
Live-Server, keine Kosten/Token, statisches Dashboard zeigt nicht mal `ok`/Spans (dashboard.py
`_aggregate` Z.21–36 ist rein Pre-Event-basiert).

### Erweiterbarkeit (neue Agents / Felder) — **7/10**
Neuer Agent = neuer `derive_agent`-Zweig + Hook-Registrierung; Schema versioniert (`schema_v:2`,
`_phase()` Fallback für v1, _load.py Z.45–47). Aber: ein neues Event-Feld muss heute durch **vier**
Stellen propagiert werden (Hook → `_paired_span` → `spans_payload` → Template-JS), ohne dass ein
Schema-/Whitelist-Mechanismus das erzwingt — genau die Bruchstelle, an der `app/intent/risk/mutating`
hängengeblieben ist.

---

## 4. Konkrete Schwächen & Lücken (jede belegt)

- **L-01 Risk/Mutating brach (Auswerte-Pfad):** `_paired_span()` (_load.py Z.61–72) kopiert nur
  `tool_name/agent/session_id/project/summary/cwd/ts/ok/error` — **nicht** `app/intent/risk/
  mutating`. Daher tauchen sie nirgends im Dashboard/Report auf. → **B-01**.
- **L-02 Keine Zeitaggregation im Live-Server:** `spans_payload` liefert rohe Span-Liste; Tages-/
  Wochen-Trends entstehen nur clientseitig in `renderDays` (Template Z.172–188) aus `ts_start`.
  Keine serverseitige Aggregation über Zeitfenster, kein „letzte N Tage"-Rollup. → B-04.
- **L-03 Keine Kosten/Token:** Kein Feld erfasst Tokenverbrauch/Kosten; Post-Event hat nur `ok/error`
  (track_tool_post Z.71–82). Für ein „ernsthaftes" Observability-Tool fehlt die Kostenachse. → B-07.
- **L-04 Fehler-/Retry-Muster fehlen:** `report.py` listet Failures flach (Z.95–100), aber keine
  Gruppierung „selber Fehler N×", keine Retry-Erkennung (gleicher tool+summary in Folge). → B-05.
- **L-05 Keine Anomalie-/Outlier-Sicht:** `duration_stats_by` liefert p95, aber nichts markiert
  Ausreißer-Spans. → B-08 (niedrig).
- **L-06 Korrelation Tool→Outcome dünn:** Erfolgsrate pro Tool existiert (`success_rate_by`), aber
  keine Kreuzung Risk×Erfolg oder Projekt×Mutating. Wird durch B-01 teils adressiert.
- **L-07 Kein Export/Integration:** Report nur Konsole, Dashboard nur Browser. Kein CSV/JSON-Export
  des aggregierten Stands. → B-06.
- **L-08 Multi-Session-Sicht begrenzt:** Timeline gruppiert pro `session_id` (Template Z.280–286),
  aber keine Session-übergreifende Vergleichs-/Verlaufssicht. → B-04 verwandt.
- **L-09 Kein Sampling bei Volumen:** `load_events` liest die ganze JSONL Zeile für Zeile in den
  Speicher (_load.py Z.19–42); bei großen Dateien O(n) ohne Tail-/Sampling-Option. → B-09.
- **L-10 Keine harte Schema-Versionierung beim Lesen:** `schema_v` wird geschrieben, aber beim Laden
  nie geprüft/migriert; nur `_phase` hat einen v1-Fallback. → B-10.

---

## 5. Risiken (belegt)

- **R-01 Privacy/Secret-Restrisiko (mittel):** Patterns sind Allowlist-basiert; unbekannte Token-
  Formate (Google `AIza`, Stripe, generische 32+-Hex-Secrets) entgehen `redact()` (Z.15–32).
  Da `build_summary` für `Bash` den ganzen Command clippt (Z.60), kann ein Secret in
  unüblichem Format in die ersten 120 Zeichen geraten.
- **R-02 Performance bei großer JSONL (mittel):** `load_events` + `pair_events` sind voll
  in-memory; `pair_events` baut mehrere Dict-Indizes + `sorted()` über alle Events (Z.105).
  Bei 10⁵+ Zeilen merklich. Kein Limit/Sampling (L-09).
- **R-03 Windows-spezifische Falle / Portabilität (hoch für CI):** `derive_project` nutzt
  `Path(...).name` statt `PureWindowsPath` → auf POSIX falsche `project`-Werte und 3 rote Tests
  (Beleg #10, C-01). Trifft jeden Linux-CI- oder Linux-Codex-Lauf.
- **R-04 Schema-Drift (mittel):** Neue Felder (wie `app/intent/risk/mutating`) erzeugen JSONL-Zeilen
  mit/ohne diese Keys nebeneinander; der Auswerte-Pfad hat keine zentrale Whitelist/Defaulting,
  daher „verschwinden" neue Felder still (genau das Symptom von L-01). → B-10.
- **R-05 cp1252-Anzeigeartefakte (niedrig, dokumentiert):** `→/█/…` crashten früher die Windows-
  Konsole; `report.py` reconfiguriert stdout auf UTF-8 (Z.24–29). Roh-JSONL bleibt Ground-Truth —
  Grep-Escaping ist kein Bug.

---

## 6. Priorisierte Backlog-Liste

Sortiert nach Wert/Aufwand. **Sprint 1** = höchster Hebel, sofort umsetzbar.

| ID | Titel | Wert | Aufwand | Dateien | Begründung | Definition-of-Done (diff-prüfbar) |
|---|---|---|---|---|---|---|
| **B-01** ⭐Sprint 1 | Risk/Mutating/App/Intent im Live-Dashboard auswerten | 5 | M | `analysis/_load.py`, `analysis/server.py`, `analysis/dashboard_template.html`, `tests/test_server.py`, `tests/test_pair_events.py` | Geschriebene, aber ungenutzte Klassifizierung (#8). Höchster Wert: macht mutierende/risikoreiche Aktionen sichtbar. | `_paired_span` trägt `app/intent/risk/mutating` in den Span (neuer Test in `test_pair_events.py`); `spans_payload` liefert `risk_breakdown` + `mutating_count` (neuer Test in `test_server.py`); `dashboard_template.html` zeigt eine Facette „Risk" mit Count-Aggregat + KPI „Mutating Spans"; `node --check` über alle Script-Blöcke grün; volle Suite ≥93 passed (Linux: ≥90 + C-01). |
| **C-01** ⭐Sprint 1 | `derive_project` plattformportabel machen | 4 | S | `hook/track_tool_use.py`, `tests/test_track_tool_use.py` | 3 rote Tests auf Linux/CI + falsche `project`-Werte bei Linux-Codex (R-03). | `derive_project` zerlegt sowohl `/`- als auch `\`-Pfade korrekt (z.B. via `PureWindowsPath`-Fallback oder Split auf `[\\/]`); die 3 bestehenden Tests grün **auf Linux**; neuer Parametrize-Test deckt POSIX- + Windows-Pfad ab; Hot-Path bleibt try/except + exit 0. |
| **S-01** Sprint 1 | Secret-Patterns erweitern (Google/Stripe/Hex) | 4 | S | `hook/track_tool_use.py`, `tests/test_track_tool_use.py` | Provider-Lücken (R-01) sind Privacy-Risiko, billig zu schließen. | Neue Patterns für Google `AIza[0-9A-Za-z_-]{35}`, Stripe `sk_live_`/`rk_live_`, generisches 32+-Hex hinter `secret/key/token`; je ein Negativtest (redacted) + ein Benign-Test (unangetastet); Reihenfolge spezifisch-vor-generisch erhalten; Suite grün. |
| B-04 | Serverseitige Zeitaggregation (Tag/Woche/Session) | 4 | M | `analysis/_load.py`, `analysis/server.py`, `tests/test_load.py`, `tests/test_server.py` | L-02/L-08: Trends statt Rohliste. | Neue `activity_by_period(spans, period)`-Funktion in `_load.py` (day/week) mit Test; `spans_payload` liefert `activity_by_day`; Template rendert daraus statt nur clientseitig; Suite grün. |
| B-05 | Fehler-/Retry-Mustererkennung im Report | 3 | M | `analysis/_load.py`, `analysis/report.py`, `tests/test_report.py` | L-04: gruppierte Fehler + Retries statt flacher Liste. | `report.py` Sektion „Top-Fehler" gruppiert nach (tool, error) mit Count; Retry-Heuristik (≥2 gleiche tool+summary in Folge pro Session) zählt „Retries"; Test deckt Gruppierung ab; Suite grün. |
| B-06 | Aggregat-Export (JSON/CSV) | 3 | S | `analysis/report.py`, `tests/test_report.py` | L-07: Integration in andere Tools. | `report.py --export json|csv` schreibt aggregierten Stand (Tools, Erfolgsraten, Dauer) in Datei; Test prüft gültiges JSON/CSV-Header; stdlib `csv`/`json` only; Suite grün. |
| B-07 | Token/Kosten-Feld erfassen (falls Payload liefert) | 3 | M | `hook/track_tool_post.py`, `analysis/_load.py`, Tests | L-03: Kostenachse. | Post-Hook liest `usage`/`tokens` aus `tool_response` defensiv (try/except), schreibt `tokens`-Feld; `_load.py` aggregiert `tokens_by_tool`; Tests mit/ohne Feld; Hot-Path-Invariante geprüft. |
| B-09 | `--tail N` / Sampling für große JSONL | 2 | S | `analysis/_load.py`, `analysis/report.py`, Tests | R-02/L-09: Performance. | `load_events(..., tail=N)` liest nur letzte N Zeilen (deque); Flag in report+dashboard; Test prüft Tail-Korrektheit; Default unverändert (alle). |
| B-10 | Schema-Versions-Check + Defaulting beim Laden | 2 | S | `analysis/_load.py`, `tests/test_load.py` | R-04/L-10: Drift-Schutz. | `load_events` defaultet fehlende neue Felder (app/intent/risk/mutating) auf definierte Werte; warnt bei `schema_v > bekannt`; Test mit gemischten v1/v2-Zeilen; Suite grün. |
| B-08 | Outlier-Markierung (Dauer-Ausreißer) | 2 | S | `analysis/_load.py`, `analysis/dashboard_template.html` | L-05. | Spans mit `duration_ms > p95` bekommen `is_outlier=true`; Timeline hebt sie hervor; Test prüft Flag; `node --check` grün. |

**Sprint 1 (höchster Wert/Aufwand): B-01, C-01, S-01.** Begründung: B-01 hebt den brachliegenden,
teuersten Datenpfad (Wert 5, schreibt bereits), C-01 + S-01 sind je S-Aufwand mit hohem Wert
(grüne CI bzw. Privacy) und entschärfen R-03/R-01 sofort.
