# Assessment- & Verbesserungs-Prompts — tool-usage-tracker (2026-06-04)

Zweistufiger Ablauf:
1. **Stufe A (Perplexity Computer, Gutachter MIT Repo-Zugriff):** liest/misst das Repo
   selbst, verifiziert den Ist-Stand und liefert einen Report mit priorisierter
   Backlog-Liste.
2. **Stufe B (dual-bridge Schedule-Tasks):** arbeitet die priorisierten Items aus Stufe A
   unter den vollen Disziplin-Regeln ab (Test-Isolation, Ground-Truth, Codex-Review).

---

## STUFE A — Prompt für Perplexity Computer (Bewertung mit Repo-Zugriff)

> Du bist ein erfahrener Software-Gutachter und hast **direkten Zugriff auf das Repository
> `tool-usage-tracker`**. Bewerte NICHT aus einer Zusammenfassung — **lies und miss selbst**.
> Die unten gelisteten Fakten sind nur eine Orientierungs- und VERIFIKATIONS-Checkliste:
> prüfe jeden Punkt gegen den echten Code und **melde jede Abweichung** (die Fakten können
> seit dem 2026-06-04 veraltet sein). Stütze jeden Befund auf eine konkrete Datei/Funktion/
> Zeile — keine Spekulation, keine Allgemeinplätze.
>
> ### Vorgehen (Pflicht-Reihenfolge)
> 1. **Orientieren:** Lies `CLAUDE.md`, `HOW-TO-USE.md`, `docs/PROJECT.md`,
>    `docs/ARCHITECTURE.md`, `docs/CAPABILITIES.md`, `docs/TODO.md`. Verschaffe dir das
>    erklärte Ziel + die selbstauferlegten Constraints.
> 2. **Code lesen:** `hook/track_tool_use.py`, `hook/track_tool_post.py`, `analysis/_load.py`,
>    `analysis/server.py`, `analysis/report.py`, `analysis/dashboard.py`,
>    `analysis/dashboard_template.html`. Verstehe Hot-Path, Sanitizer, Pairing, Auswertung.
> 3. **Daten ansehen:** Inspiziere einige Zeilen `data/events.jsonl` (falls vorhanden) —
>    welche Felder existieren REAL, inkl. der neuen `app`/`intent`/`risk`/`mutating`? Gibt es
>    Schema-Drift (Zeilen mit/ohne neue Felder)? **Achtung Ground-Truth:** die rohe JSONL-Zeile
>    ist die Wahrheit, nicht die Anzeige in einem Grep/einer Windows-Konsole (cp1252/Escaping
>    erzeugt Phantom-„Bugs"). Bei Verdacht die rohe Zeile / `repr()` prüfen, nicht das Rendering.
> 4. **Tests verstehen + laufen lassen** (falls die Umgebung es erlaubt): `python -X utf8 -m
>    pytest -q tests/`. **VOR und NACH dem Lauf** die Zeilenzahl der echten `data/events.jsonl`
>    vergleichen — sie darf durch die Tests NICHT wachsen (Tests müssen in tmp_path/
>    `TOOL_TRACKER_DATA` isoliert schreiben). Wächst sie durch die Tests selbst → das ist ein
>    ernster Isolationsbefund, melde ihn als High-Priority. (Ein Wachstum von 1-2 Zeilen durch
>    den live mitlaufenden Tracker-Hook auf deine eigenen Shell-Aufrufe ist dagegen normal.)
> 5. **Bewerten + Backlog erstellen** (siehe Output unten).
>
> ### Verifikations-Checkliste (Stand 2026-06-04 — bestätigen oder widerlegen)
> - Hot-Path `track_tool_use.py` nie-blockierend (try/except, exit 0, keine permissionDecision)?
> - Event-Pfad eine LAZY Funktion mit Env-Override `TOOL_TRACKER_DATA` (NICHT als Modul-
>   Konstante eingefroren)?
> - Sanitizer: 120-Zeichen-Limit pro Feld + Secret-Redaction (AWS/JWT/PEM/Slack/GitHub-Token)?
>   Wird wirklich nie Datei-Inhalt geloggt? Welche Secret-Muster fehlen evtl.?
> - Stdlib-only im Kern (kein pandas/matplotlib/Flask)? Chart.js gevendort/inline?
> - Pre/Post-Pairing per exaktem `tool_use_id`, FIFO nur Fallback?
> - PostToolUse-Erfolg/Fehler via `tool_response` + `is_error`/`interrupted`/`exit_code`?
> - Codex-Kompatibilität (`.codex/hooks.json`, eigener `agent`-Wert) vorhanden?
> - Neue Felder `app`/`intent`/`risk`/`mutating` werden geSCHRIEBEN, aber im Dashboard noch
>   NICHT ausgewertet? (Erwartete größte offene Lücke — bestätige am Code.)
> - Erwartete LOC-Größenordnung: track_tool_use ~244, _load ~209, übrige Module ~100-130.
> - Tests grün (~93 passed / 1 skipped Playwright)? Stimmt die Zahl noch?
>
> ### Output (genau diese Struktur)
> 1. **Verifikations-Ergebnis:** Checkliste Punkt für Punkt — bestätigt / abweichend (mit
>    Datei:Funktion als Beleg). Zuerst, damit der Rest auf gesichertem Stand steht.
> 2. **Gesamteinschätzung** (3-5 Sätze): Reifegrad, größte Stärke, größtes Risiko.
> 3. **Bewertung je Dimension** (0-10 + je 2-3 Sätze, jeweils mit Code-Beleg):
>    Nützlichkeit/Produktwert · Architektur/Modularität · Robustheit des Hot-Paths ·
>    Datenqualität & Sanitizing/Privacy · Test-Strategie · Observability-Auswertbarkeit
>    (Report+Dashboard) · Erweiterbarkeit (neue Agents/Felder).
> 4. **Konkrete Schwächen & Lücken** (jede mit Datei/Funktion belegt): was fehlt einem
>    ernsthaften Observability-Tool für Agent-Tool-Nutzung? Aggregation über Zeit, Kosten/
>    Token, Fehler-/Retry-Muster, Anomalie-Erkennung, Korrelation Tool→Outcome, Export/
>    Integration, Multi-Session-Sicht, Sampling bei Volumen, Schema-Versionierung der JSONL.
> 5. **Risiken** (belegt): Privacy/Secret-Leak-Restrisiken, Performance bei großer JSONL,
>    Windows-spezifische Fallen, Schema-Drift wenn neue Felder dazukommen.
> 6. **Priorisierte Backlog-Liste** — DAS ist der wichtigste Output. Pro Item:
>    `ID · Titel · Wert (1-5) · Aufwand (S/M/L) · Betroffene Datei(en) · Begründung ·
>    Definition-of-Done (prüfbar)`. Sortiere nach Wert/Aufwand. Markiere die 2-3
>    höchstwertigen als "Sprint 1". Formuliere jede DoD **diff-prüfbar**, sodass ein
>    Coding-Agent sie ohne Rückfrage verifizieren kann (z. B. "Dashboard zeigt `risk`/
>    `mutating` als Facette mit Count-Aggregat; `dashboard_smoke` grün; neuer Test in
>    `tests/test_server.py` deckt die Facette ab").
>
> Sei kritisch und spezifisch. Jeder Befund braucht einen Code-Beleg (Datei/Funktion). Lieber
> eine konkrete, belegte Lücke als fünf Allgemeinplätze.

---

## STUFE B — Übergabe an dual-bridge (Schedule-Tasks)

Perplexitys Backlog-Liste (Abschnitt 5 oben) wird zu Bridge-Seeds/Schedule-Tasks. Jeder
Task läuft unter den **vollen globalen Disziplin-Regeln** — der Bridge-Auftrag pro Item:

> **Auftrag (ein Backlog-Item):** Setze `<ID · Titel>` aus dem Perplexity-Assessment
> (`docs/reviews/2026-06-04-perplexity-assessment.md`) im Repo **tool-usage-tracker** um.
>
> **Pflicht-Gates (nicht verhandelbar):**
> 1. **Test-DB/State-Isolation VOR jedem pytest** (CLAUDE.md §3): keine SQL-DB hier, aber
>    Tests dürfen NIE in die echte `data/events.jsonl` schreiben — eigener tmp_path je Test
>    über `TOOL_TRACKER_DATA`. Snapshot der echten `data/events.jsonl` (Zeilenzahl) VOR und
>    NACH dem Suite-Lauf vergleichen; eine Differenz darf nur aus dem live laufenden Tracker-
>    Hook auf eigene Tool-Calls stammen, NIE aus den Tests.
> 2. **Hot-Path bleibt nicht-blockierend:** `hook/track_tool_use.py`/`track_tool_post.py`
>    weiterhin try/except, exit 0, keine permissionDecision. Jede Änderung am Hook gegen
>    diese Invariante prüfen.
> 3. **Stdlib-only-Constraint** halten (kein pandas/Flask/numpy im Kern); Chart.js bleibt
>    gevendort/inline.
> 4. **Ground-Truth vor Behauptung** (CLAUDE.md §4 / Projekt-Memory): Anzeige-Artefakte
>    (Grep-Escaping, Windows-cp1252) sind KEINE Bugs — erst die Quelle/`repr()` der rohen
>    JSONL-Zeile prüfen, bevor ein "Fehler" gefixt wird. (Zwei Phantom-Bugs in der Historie.)
> 5. **TDD:** Regressionstest zuerst (RED), dann Implementierung (GREEN). Sanitizer-/Secret-
>    Redaction-Pfade brauchen Negativtests.
> 6. **Verifikation:** volle Suite grün (Soll: ≥93 passed), `node --check` bzw. Playwright-
>    Smoke grün bei Dashboard-/eingebettetem-JS-Änderungen (eingebettetes JS bricht still,
>    Byte-Count beweist nichts).
>
> **DoD = die prüfbare Definition-of-Done aus dem Perplexity-Item.** Erst nach erfüllten
> Gates + grüner Verifikation committen (chirurgisch stagen, CLAUDE.md §7).
>
> **Empfohlene Sprint-1-Reihenfolge** (sofern Perplexity nicht stark abweicht): Dashboard-
> Auswertung der neuen `app`/`intent`/`risk`/`mutating`-Felder zuerst — Daten werden bereits
> geschrieben, der Auswerte-Pfad fehlt → höchster Wert/Aufwand.

---

## Übergabe-Notiz
- Perplexity-Output ablegen unter `docs/reviews/2026-06-04-perplexity-assessment.md`.
- Danach Backlog-Items als dual-bridge-Seeds/Schedule-Tasks einspeisen (1 Task = 1 Item,
  diff-prüfbare DoD — vgl. dual-bridge-Lehre: Seeds müssen diff-prüfbar formuliert sein,
  sonst lesen Agenten sie als "schon erledigt").
