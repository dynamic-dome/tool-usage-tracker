# Design: Trace-Waterfall pro Turn (B-1)

*Datum: 2026-06-04 · Status: approved · Quelle: Perplexity-Assessment-Backlog B-1*

## Ziel

Den bestehenden Timeline-Tab des Dashboards zu einem **Trace-Waterfall** ausbauen:
Tool-Spans werden pro **Turn** gruppiert und innerhalb jedes Turns auf einer
**echten Zeitachse** dargestellt (x-Position = Offset ab Turn-Start, Breite ∝ Dauer).
So werden sequenzielle Abläufe und Lücken (Denk-/Wartezeit) sichtbar — anders als bei
der heutigen aneinandergereihten Balkenreihe (Breite ∝ Dauer, ohne Zeitachse).

Arbeitet ausschließlich auf **vorhandenen Daten** — kein Hook-Umbau, kein neues
JSONL-Feld.

## Turn-Definition

Die Events tragen **kein** Turn-Feld (nur `session_id`, `ts_utc`, `duration_ms`,
`tool_use_id`). Ein Turn (= ein User-Prompt + die folgenden Tool-Calls bis zur
nächsten User-Eingabe) wird per **Gap-Heuristik** rekonstruiert:

- Innerhalb einer Session: neuer Turn beginnt, wenn die Pause zwischen dem Ende eines
  Spans und dem Start des nächsten einen Schwellwert überschreitet.
- **Schwellwert = global + adaptiv** (eine Schwelle für den ganzen gefilterten View,
  nicht pro Session — stabiler durch mehr Datenpunkte).

## Architektur & Datenfluss

Die gesamte Turn-Logik lebt als **reine Python-Funktionen in `analysis/_load.py`**
(neben `pair_events`/`duration_stats_by`), nicht im JS — passt zum bestehenden Muster
(Python aggregiert, JS rendert nur) und ist damit vollständig unit-testbar.

```
events.jsonl → load_events → pair_events → spans
                                              │
              compute_turn_gap_threshold(spans) → threshold (ms)
                                              │
              assign_turns(spans, threshold)  → spans mit turn_index
                                              │
        server.py / dashboard.py reichen spans (inkl. turn_index)
        + threshold als JSON ans Template durch
                                              │
              renderTimeline(data)  → Session → Turn-Gruppen → Zeitachse
```

### `compute_turn_gap_threshold(spans) -> int` (ms)

1. Alle Inter-Span-Gaps sammeln: für je zwei zeitlich aufeinanderfolgende Spans
   **derselben Session** `gap = ts_start[i+1] − ts_end[i]` (ms, nur ≥ 0).
2. **Fallback 30000ms**, wenn < 8 Gaps insgesamt (zu wenig Daten für stabile Schätzung).
3. Sonst: `threshold = median(gaps) + 3 · MAD(gaps)` (Median Absolute Deviation, robust
   gegen Ausreißer).
4. **Harte Klammer:** `max(5000, min(120000, threshold))`.

Deterministisch (keine Zeit-/Zufallsabhängigkeit).

### `assign_turns(spans, threshold) -> spans` (mit `turn_index`)

- Pro Session chronologisch nach `ts_start`; neuer `turn_index` (0-basiert,
  session-lokal), sobald `gap > threshold`.
- Spans ohne `ts_start` (ungepaarte Pre/Post-Orphans) → ans **Ende** der jeweiligen
  Session (eigener loser Turn / letzter Turn).
- Setzt `turn_index` auf jedem Span; persistiert nichts ins JSONL.

## Rendering (`renderTimeline` im Timeline-Tab)

Hierarchie: **Session → Turn-Gruppen → echte Zeitachse**.

```
Session sid (project)
  ┌─ Turn 0 · Δ 1.2s · 4 Spans ─────────────────────┐
  │  ▰▰▰ Read app.py 320ms                           │   x = (ts_start − turnStart)/turnSpan
  │       ▰ Grep TODO 45ms                           │   w = duration/turnSpan
  │           ▰▰▰▰▰▰▰ Bash pytest 2100ms             │
  └──────────────────────────────────────────────────┘
  ┌─ Turn 1 · Δ 8.5s · 2 Spans ─────────────────────┐ ...
```

- **Skalierung relativ pro Turn** (jeder Turn füllt die volle Breite) — sonst werden
  kurze Turns von langen zerquetscht.
- **Vertikales Stapeln** überlappender/gleichzeitiger Spans (jeder Span eine eigene
  Track-Zeile, wie DevTools-Network) statt Überlagerung.
- **Mindestbreite** je Balken (~3px) für Klickbarkeit.
- Farben/Tooltips aus der bestehenden Logik wiederverwenden (`ok`→accent,
  `fail`→accent2, `open`→gestrichelt). Tooltip zusätzlich `git_branch`/`file_ext`
  (A-5-Felder), wenn vorhanden.
- Ungepaarte Spans (kein `ts_start`/`ts_end`): gestrichelt, am Turn-Ende mit
  Mindestbreite (kein echtes Offset berechenbar).
- CSS: neue Klassen `tl-turn`, `tl-turn-head`, `tl-track` (position:relative), Balken
  `position:absolute`. Dark-Theme/Command-Center-Variablen wiederverwenden.

Eine reine Layout-Helferfunktion (`turnLayout(spans)` → Offsets/Breiten/Stapelzeilen)
wird so geschnitten, dass sie isoliert in Node testbar ist (Brace-Matching-Extraktion,
L4-Muster — nicht den DOM-verdrahtenden Top-Level laden).

## Fehlerbehandlung

- Keine Spans / keine `ts_start` → „Keine Spans"-Hinweis (wie heute).
- Turn mit Nulldauer (`turnSpan = 0`, alle Spans gleichzeitig) → Division-Guard,
  Balken gestapelt mit Mindestbreite.
- `try/catch` um `renderTimeline` (wie die anderen Render-Funktionen) — ein
  Render-Fehler darf die übrigen Charts nicht mitreißen.

## Tests (TDD)

**Python (`tests/test_turns.py`):**
- `compute_turn_gap_threshold`: leer → 30s; < 8 Gaps → 30s; ≥ 8 Gaps → Median+3·MAD;
  Klammer greift bei Ausreißern (min 5s / max 120s); Gaps nur intra-Session.
- `assign_turns`: ein Burst (alle Gaps < Schwelle) → 1 Turn; Pause > Schwelle → Split;
  mehrere Sessions → unabhängige `turn_index`; Spans ohne `ts_start` → ans Ende;
  unsortierter Input robust.
- Determinismus: gleiche Eingabe → gleiche Zuweisung.

**JS (L4-Muster):** `turnLayout` per Brace-Matching extrahieren, in Node testen
(Offsets/Breiten/Stapelzeilen). Kein Browser, kein Chart.js-Stub nötig.

## Abgrenzung (YAGNI — bewusst NICHT in B-1)

- Kein Hook-Umbau, kein neues persistiertes JSONL-Feld.
- Kein konfigurierbarer Schwellwert im UI.
- Kein Cross-Session-Turn-Merge.
- Kein Zoom/Pan auf der Zeitachse.

## Betroffene Dateien

- `analysis/_load.py` — `compute_turn_gap_threshold`, `assign_turns`.
- `analysis/dashboard_template.html` — `renderTimeline` + `turnLayout` + CSS.
- `analysis/server.py` / `dashboard.py` — `turn_index`/`threshold` ans Template
  durchreichen (prüfen, ob nötig — ggf. fällt es schon mit den Spans an).
- `tests/test_turns.py` (neu), ggf. `tests/test_load.py`.
- Docs: `docs/CAPABILITIES.md`, `HOW-TO-USE.md` (Timeline-Beschreibung).
