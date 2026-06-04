---
title: Agent-Tracking & Auswertung — Erweiterungsvorschläge
date: 2026-06-04
kind: research-dossier
status: eingeordnet, nicht umgesetzt
related:
  - docs/reviews/2026-06-04-perplexity-assessment.md
  - docs/reviews/2026-06-04-assessment-prompt.md
---

# Einordnung (Claude Code, 2026-06-04)

Extern recherchiertes Dossier, das `tool-usage-tracker` gegen den Observability-Markt
2026 (OTel-GenAI, MLflow, Langfuse, Phoenix, Braintrust, DuckDB) verortet. Kernthese,
die wir teilen: **nicht zu OTel migrieren, aber die Feldnamen anschlussfähig machen**
(`gen_ai.usage.*`), damit ein späterer Export trivial bleibt. Quellengestützt, dichter
und ambitionierter als das Perplexity-Assessment (Markt-Niveau statt Lücken-Schließen).

## Überlappung mit dem Perplexity-Backlog (`2026-06-04-perplexity-assessment.md`)
- **A-3 enthält S-01** (Secret-Patterns Google/Stripe/Hex) — das offene dritte Sprint-1-Item.
- **A-1 / B-4** ≈ Perplexity **B-07** (Token/Kosten) + **B-04** (Zeitaggregation), hier mit
  konkreter Datenquelle (Claude Code OTLP-Metrics).
- **A-4 Retry-Detection** ≈ Perplexity **B-05**.
- **B-6 DuckDB** ist neu — respektiert explizit die stdlib-only-Linie (single-binary,
  optionales Add-on, Kern bleibt rein).

## Verifikations-Vorbehalte VOR Umsetzung (Ground-Truth, nicht dem Dossier blind folgen)
Dieses Projekt wurde schon zweimal von einem **angenommenen** Hook-Schema getroffen
(siehe Learnings L1/L2: `tool_response` statt `tool_output`). Daher gilt für die zwei
telemetrie-abhängigen Vorschläge:

1. **A-1 / A-2 hängen an Claude-Code-Telemetrie-Claims** (`CLAUDE_CODE_ENABLE_TELEMETRY`,
   `CLAUDE_CODE_ENHANCED_TELEMETRY_BETA`, OTLP-Metrics mit Token/Cost, Trace-/Span-Felder).
   **Vor jedem Bau:** prüfen, ob diese Env-Flags + Felder real existieren und was sie
   konkret liefern — gegen den echten Output, nicht nur die zitierte Doku.
2. **A-1 „lokaler OTLP-Mini-Endpunkt" ist NICHT trivial stdlib-konform.** OTLP ist
   protobuf/gRPC, nicht einfach JSON über `http.server`. Aufwand real höher als im Dossier
   suggeriert; Kosten/Nutzen vor der Akquise gegenrechnen.

## Niedrig hängende Früchte (hoher Wert, klar im Gates-Rahmen — stdlib, Hot-Path-sicher, TDD)
- **A-3** MCP-/Stack-CLI-Klassifikation — MCP-Calls (Playwright/Wiki/NotebookLM) + DCO/
  dual-bridge sind aktuell blinde Flecken; reine Erweiterung der `classify_bash`-Logik.
- **A-5** `git_branch`/`git_dirty` + Datei-Endung — billig aus dem Hook-Kontext, kein Inhalt.
- **B-1** Trace-Waterfall pro Turn — höchster visueller Gewinn aus Daten, die schon da sind
  (`duration_ms`/`risk`/`ok`), reines Frontend.

---

# Agent-Tracking & Auswertung — Erweiterungsvorschläge für `tool-usage-tracker`

Stand: Juni 2026 · Research-Dossier für DoMe (dynamic-dome)
Bezug: IST-Zustand `tool-usage-tracker` (JSONL-Hooks pre/post → Spans, Bash-Klassifikation app/intent/risk/mutating, CLI-Report + statisches & Live-Dashboard, Secret-Redaction, stdlib-only Kern)

---

## 0. Einordnung: Was du schon hast vs. was der Markt macht

Dein Tracker sitzt bewusst auf der **leichtgewichtigen, file-based, lokalen** Seite. Der „Industrie-Standard" 2026 ist dagegen **OpenTelemetry-natives Tracing** mit Span-Bäumen, Backends wie MLflow, Langfuse, Arize Phoenix und Auswertung per Flame-Graph/Waterfall ([MLflow Top-5 Observability](https://mlflow.org/top-5-agent-observability-tools/), [Braintrust Tracing-Review 2026](https://www.braintrust.dev/articles/best-llm-tracing-tools-2026)).

Wichtig für dich: **Du musst nicht zu OTel migrieren.** Aber das OTel-GenAI-Vokabular ist die Referenz-Ontologie — wenn deine Felder daran anschlussfähig sind, kannst du später optional in jedes Backend exportieren, ohne neu zu instrumentieren. Die folgenden Vorschläge sind nach diesem Prinzip sortiert: **erst die Datenakquise-Lücken füllen, die dein eigenes Schema substanziell aufwerten, dann die Darstellung, die diese neuen Daten sichtbar macht.**

---

## TEIL A — DATENAKQUISE: Was du zusätzlich aufzeichnen solltest

### A-1 ⭐ Token- & Kosten-Daten pro Tool-Call/Span (größter Mehrwert-Hebel)

**Lücke:** Dein Span hat `duration_ms`, aber keine Token-/Kosten-Dimension. Das ist 2026 die zentrale Auswertungsachse jeder Agent-Observability — „cost & token tracking per run/session" taucht in praktisch jedem Tool als Kernfeature auf ([Langfuse Cost-Tracking](https://langfuse.com/docs/observability/features/token-and-cost-tracking), [self-hosted Dashboard, r/LLMDevs](https://www.reddit.com/r/LLMDevs/comments/1rfm876/we_built_a_selfhosted_observability_dashboard_for/)).

**Konkrete Akquise-Quelle für deinen Stack:** Claude Code exportiert nativ Metrics-Counter für **Tokens, Kosten, Sessions, Lines-of-Code und Tool-Decisions** über OpenTelemetry — schaltbar per `CLAUDE_CODE_ENABLE_TELEMETRY=1` plus Exporter ([Claude Code Observability Docs](https://code.claude.com/docs/en/agent-sdk/observability)). Token-Counts liegen pro API-Request vor, sobald die `usage`-Daten zurückkommen.

**Empfehlung (stdlib-konform):** Statt einen OTel-Collector zu betreiben, schreibe Claude Codes OTLP-Metrics auf einen **lokalen Mini-Endpunkt** (stdlib `http.server`), parse die Token/Cost-Counter und merge sie per `session_id`/`tool_use_id` in deine Spans. Damit bekommst du `input_tokens`, `output_tokens`, `cache_read_tokens` und `cost_usd` pro Span — ohne pandas/Flask.

Feldnamen am OTel-GenAI-Standard ausrichten, damit später portabel ([OTel GenAI Agent-Spans](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/)):
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- `gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.cache_creation.input_tokens`

### A-2 ⭐ Trace-/Span-Hierarchie statt flacher Event-Liste

**Lücke:** Deine Events sind eine flache JSONL-Liste, gepaart zu Spans per `tool_use_id`. Was fehlt: die **Parent-Child-Beziehung** zwischen Spans innerhalb eines Agent-Schritts (Trace → Interaction → Tool-Call). Genau das unterscheidet „Tracing" von „Logging": Spans verbinden sich zu einem Baum, der den kompletten Ausführungspfad zeigt ([Braintrust 2026](https://www.braintrust.dev/articles/best-llm-tracing-tools-2026)).

**Konkrete Akquise:** Claude Code emittiert im Enhanced-Telemetry-Beta (`CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1`) **Traces mit Spans für jede Interaction, jeden Model-Request, jeden Tool-Call und Hook** ([Claude Code Observability Docs](https://code.claude.com/docs/en/agent-sdk/observability)). Daraus kannst du `trace_id` und `parent_span_id` ziehen und in deine Events schreiben — minimal-invasiv, da nur zwei Felder.

**Wenn du keine OTel-Traces willst:** Synthetisiere die Hierarchie selbst. Ein „Turn" lässt sich aus `session_id` + Zeitfenster + UserPromptSubmit-Hook ableiten. Arize Phoenix nutzt sieben Span-Typen (CHAIN, RETRIEVER, RERANKER, LLM, EMBEDDING, **TOOL**, AGENT) — deine Bash-Klassifikation deckt faktisch nur den TOOL-Typ ab; eine `span_type`-Spalte würde dich anschlussfähig machen ([Augment Code, 7 Tools 2026](https://www.augmentcode.com/tools/best-ai-agent-observability-tools)).

### A-3 ⭐ Mehr Tool-Familien klassifizieren + MCP-Calls erfassen

**Lücke:** Deine Bash-Klassifikation kennt `git`, `gh`, `wrangler`, `notebooklm`, Python-/Node-Tools. In deinem Stack laufen aber **MCP-Server** (Obsidian-Wiki, NotebookLM, Playwright) — MCP-Tool-Calls sind 2026 eine eigene Tracking-Kategorie, die Datadog & Braintrust explizit als Differenzierungsmerkmal nennen ([Augment Code 2026](https://www.augmentcode.com/tools/best-ai-agent-observability-tools)).

**Empfehlung:** Erweitere die Klassifikation um:
- **MCP-Tool-Calls** (`app:"mcp"`, `operation:"<server>/<tool>"`, z. B. `obsidian/search`, `playwright/navigate`) — diese kommen als eigene Tool-Namen, nicht als Bash.
- Deine eigenen Stack-CLIs: **DCO** (`dco`-Kommandos gegen `todos.db`), **dual-bridge** (Google-Drive-Sync), `claude`/`codex` selbst.
- Fehlende Secret-Patterns (aus deinem eigenen Backlog S-01): Google `AIza`, Stripe `sk_live_`, generisches Hex ≥32. Mit **Negativtest** pro Pattern (TDD-Gate).

### A-4 Outcome-/Qualitäts-Signale (nicht nur „ok/error")

**Lücke:** Dein Span hat `ok` + `error`. Die Auswertungswelt 2026 dreht sich um **trace-aware evaluation**: nicht nur „hat das Tool funktioniert", sondern „war die Tool-**Wahl** richtig, war der Schritt nötig" ([MLflow Agent-Eval](https://mlflow.org/top-5-agent-evaluation-frameworks/), [Confident AI Agent-Metriken](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide)).

**Leichtgewichtige, lokale Annäherung (ohne LLM-Judge):**
- **Retry-Detection:** Gleicher `tool_name` + ähnliche Args < N Sekunden nach einem `ok:false` → markiere `retry_of`. Das misst „Reibung" pro Tool.
- **Redundanz-Heuristik:** identische Read-Calls auf dieselbe Datei im selben Turn → `redundant:true`.
- **Edit→Test-Korrelation:** Folgt auf einen `mutating`-Edit innerhalb desselben Turns ein `intent:"test"`-Call? (Verhältnis = grober TDD-Disziplin-Indikator, passt zu deinen CLAUDE.md-Gates.)

### A-5 Datei-/Repo-Kontext anreichern

**Lücke:** Du hast `cwd`, `project`, `is_git_repo`. Was günstig zu holen ist und stark verdichtet:
- **`git_branch`** + **`git_dirty`** (aus `git rev-parse`/`status --porcelain`, läuft eh im Hook-Kontext) → erlaubt Auswertung „welcher Branch frisst die meisten Tool-Calls".
- **Datei-Endung** bei Read/Edit/Write (`.py`/`.html`/`.md`) → „Sprach-Heatmap" der Aktivität, rein aus Pfad ableitbar, kein Datei-Inhalt.
- **`lines_changed`** bei Edits, falls Claude Code es im Tool-Result liefert (Claude Code zählt Lines-of-Code als nativen Counter, siehe A-1).

### A-6 Hook-Lifecycle vollständig erfassen

Claude Code feuert mehr als Pre/Post-ToolUse: **`UserPromptSubmit`, `SessionStart`, `Stop`, `SubagentStop`** u. a. ([Claude Code Hooks-Reference](https://code.claude.com/docs/en/hooks)). `UserPromptSubmit` + `SessionStart` schreiben sogar in den Kontext, den Claude sieht. Wenn du diese als eigene Event-Phasen mitschreibst, bekommst du **echte Turn-Grenzen** (Voraussetzung für A-2) und kannst „Tool-Calls pro Prompt" auswerten — eine der aussagekräftigsten Produktivitätsmetriken.

---

## TEIL B — DARSTELLUNG: Wie du die Daten auswertest & zeigst

### B-1 ⭐ Trace-Waterfall / Flame-Graph der Spans

**Der Standard 2026:** Jedes ernsthafte Tool zeigt Tool-Calls als **Waterfall oder Flame-Graph auf einer Zeitachse** — Start, Dauer, Verschachtelung, Fehler farblich markiert ([Datadog Trace-View](https://docs.datadoghq.com/tracing/trace_explorer/trace_view/), [Braintrust Timeline-Replay](https://www.braintrust.dev/articles/best-llm-tracing-tools-2026)). Deine Timeline-Ansicht existiert schon — der nächste Schritt ist die **vertikale Span-Liste mit Balken proportional zu `duration_ms`**, eingefärbt nach `risk`/`ok`. Das ist mit deinem inline-Chart.js (oder reinem SVG/Canvas, stdlib-kompatibel im Frontend) machbar, ohne neue Abhängigkeit.

Konkret: pro Turn ein zusammenklappbarer Block (`<details>`), darin die Tool-Calls als horizontale Balken. Lange/teure Calls springen sofort ins Auge — genau der „spot where latency spikes occur"-Use-Case aus dem Braintrust-Review.

### B-2 ⭐ Run-Replay (Schritt-für-Schritt durch eine Session)

Das self-hosted Definable-Dashboard und Braintrust heben **Run-Replay** als Killer-Feature hervor: eine vergangene Session Schritt für Schritt durchklicken ([r/LLMDevs self-hosted Dashboard](https://www.reddit.com/r/LLMDevs/comments/1rfm876/we_built_a_selfhosted_observability_dashboard_for/), [Braintrust 2026](https://www.braintrust.dev/articles/best-llm-tracing-tools-2026)). Da deine Daten zeitlich geordnet sind, ist das ein **Slider/Prev-Next über die Span-Liste einer `session_id`** — reines Frontend, kein neuer Backend-Code. Sehr hoher Erkenntniswert für Self-Improvement-Retrospektiven (passt direkt zu deinem `retrospective`-Skill).

### B-3 ⭐ Run-Comparison (zwei Sessions nebeneinander)

Ebenfalls aus dem self-hosted Dashboard: **zwei Runs side-by-side** vergleichen, um Unterschiede in Tool-Calls/Reibung zu sehen. Für dich konkret: „Codex-Session vs. Claude-Code-Session am selben Task" — welcher Agent braucht weniger Tool-Calls, weniger Retries, weniger High-Risk-Operationen. Das ist genau die Auswertung, die deinen **Dual-Agent-Setup** sichtbar macht und die kein generisches Tool für dich beantwortet.

### B-4 Tool-Analytics-Tabelle (Häufigkeit · Fehlerrate · Ø-Dauer · Kosten)

Standard-Panel überall ([Definable-Dashboard](https://www.reddit.com/r/LLMDevs/comments/1rfm876/we_built_a_selfhosted_observability_dashboard_for/)): pro Tool/`operation` eine Zeile mit **Calls, Error-Rate, p50/p95-Dauer, Σ-Tokens, Σ-Kosten**, sortierbar. Deine Risk-Doughnut (B-01, gerade gebaut) ist der Anfang — die Tabelle ergänzt die „welches Tool kostet mich am meisten Zeit/Geld/Risiko"-Sicht.

### B-5 Heatmaps & Zeitreihen

- **Aktivitäts-Heatmap** (Stunde × Wochentag) — wann arbeitest du mit Agenten, wann passieren Fehler.
- **Token/Cost/Error-Rate über Zeit** in 5min/30min/Stunde/Tag-Buckets ([Definable-Dashboard Timeline-Visuals](https://www.reddit.com/r/LLMDevs/comments/1rfm876/we_built_a_selfhosted_observability_dashboard_for/)).
- **Sektor-Heatmap-Analogie:** Du hast in deinem Darts-Stack (`stats-tracker`) bereits Heatmap-Logik — die rendering-Idee ist übertragbar.

### B-6 SQL-Layer für Ad-hoc-Auswertung (DuckDB, optionales Add-on)

Für tiefe Analysen jenseits fixer Dashboard-Panels: **DuckDB liest NDJSON/JSONL nativ, inferiert das Schema und parallelisiert** — `read_ndjson_auto('events.jsonl')` und du hast SQL über deine Spans, inkl. Window-Functions für p50/p95 ([MotherDuck JSON-Log-Guide](https://motherduck.com/blog/json-log-analysis-duckdb-motherduck/), [Terse Systems SQLite/DuckDB-Loganalyse](https://tersesystems.com/blog/2023/03/04/ad-hoc-structured-log-analysis-with-sqlite-and-duckdb/)). DuckDB ist eine einzelne Binary, keine Server-Infrastruktur — passt zu deiner „zero-infra"-Linie, bleibt aber **optional** (Kern bleibt stdlib-only, DuckDB nur als Analyse-Add-on). Tailpipe zeigt, dass DuckDB+Parquet lokal hunderte Mio. Zeilen verkraftet ([Tailpipe, r/DuckDB](https://www.reddit.com/r/DuckDB/comments/1idv05s/tailpipe_new_open_source_log_analysis_cli_powered/)).

---

## TEIL C — Optionaler Brückenkopf: OTel-Export

Falls du irgendwann ein „echtes" Backend willst, ohne deinen Tracker aufzugeben: schreibe einen **dünnen Exporter**, der deine Spans ins OTLP-Format mappt und an einen lokalen **Jaeger-All-in-One-Container** oder Grafana(LGTM) schickt ([Claude Code: lokaler Collector/Jaeger](https://code.claude.com/docs/en/agent-sdk/observability), [r/ClaudeCode OTel-Metrics + Grafana](https://www.reddit.com/r/ClaudeCode/comments/1pjon1r/til_that_claude_code_has_opentelemetry_metrics/)). Mapping ist dank A-1/A-2 trivial, wenn deine Felder schon `gen_ai.*`-konform heißen. **Bewusst niedrig priorisiert** — die LGTM/Grafana-Stack ist ressourcenhungrig und widerspricht deiner Leichtgewicht-Philosophie; nur sinnvoll, wenn du Multi-Device-Aggregation brauchst.

---

## Vergleichstabelle: Markt-Tools vs. dein Tracker (Einordnung)

| Tool | OSS / Self-host | Datenmodell | Was du übernehmen kannst |
|---|---|---|---|
| **Arize Phoenix** | OSS, single-node ([Augment Code](https://www.augmentcode.com/tools/best-ai-agent-observability-tools)) | 7 Span-Typen, OpenInference+OTel | Span-**Typisierung** (A-2), Trajectory-Mapping |
| **MLflow** | Apache-2.0, self-host ([MLflow](https://mlflow.org/top-5-agent-observability-tools/)) | OTel-nativ, Trace+Eval | Trace-aware **Eval-Konzept** (A-4) |
| **Langfuse** | MIT, Docker self-host ([Braintrust self-host](https://www.braintrust.dev/articles/best-self-hosted-ai-evals-tools-2026)) | OTel-ingest, Cost-Tracking | **Token/Cost pro Generation** (A-1) |
| **Definable (OSS)** | zero-infra, ein Flag ([r/LLMDevs](https://www.reddit.com/r/LLMDevs/comments/1rfm876/we_built_a_selfhosted_observability_dashboard_for/)) | lokales Dashboard, SSE | **Run-Replay, Run-Compare, Tool-Analytics** (B-2/B-3/B-4) — am nächsten an deiner Philosophie |
| **Braintrust** | proprietär, MCP-Server | Timeline-Replay | **Waterfall + Replay**-UX (B-1/B-2) |
| **DuckDB / Tailpipe** | OSS, single-binary ([MotherDuck](https://motherduck.com/blog/json-log-analysis-duckdb-motherduck/)) | SQL über NDJSON/Parquet | **Ad-hoc-SQL-Layer** (B-6) |

---

## Top-5-Empfehlung — „das würde ich als Nächstes evaluieren"

Sortiert nach Nutzen-für-deinen-Stack ÷ Aufwand, alle innerhalb deiner Gates (stdlib-Kern, Hot-Path-sicher, TDD):

1. **A-1 · Token & Kosten pro Span** — größter Auswertungshebel, Datenquelle (Claude Code OTLP-Metrics) existiert nativ. Feldnamen `gen_ai.usage.*`-konform. Schaltet B-4/B-5 frei.
2. **A-3 · MCP- + Stack-CLI-Klassifikation** — deine MCP-Server (Obsidian/NotebookLM/Playwright) und DCO/dual-bridge sind aktuell blinde Flecken. Reine Erweiterung deiner bestehenden `classify_bash`-Logik, klein und testbar. Inkl. S-01-Secret-Patterns mit Negativtests.
3. **B-1 · Trace-Waterfall pro Turn** — höchster visueller Erkenntnisgewinn aus Daten, die du schon hast (`duration_ms`, `risk`, `ok`). Reines Frontend, inline-Chart.js/SVG, keine neue Abhängigkeit.
4. **B-3 · Run-Comparison (Claude vs. Codex)** — beantwortet eine Frage, die für deinen Dual-Agent-Setup spezifisch ist und die kein Fremdtool für dich löst. Baut auf A-2-Turn-Grenzen auf.
5. **B-6 · DuckDB-Ad-hoc-SQL-Layer (optional)** — entkoppelt tiefe Analysen vom Dashboard, single-binary, kein Infra-Overhead. Hält den Kern stdlib-only, gibt dir aber p95/Window-Functions on demand.

**Reihenfolge-Logik:** A-1 + A-3 erweitern die Datenakquise (sonst hast du nichts Neues zum Zeigen) → B-1 macht das Vorhandene + Neue sichtbar → B-3 nutzt die Turn-Struktur → B-6 als analytisches Schwergewicht obendrauf. C (OTel-Export) erst, wenn du echte Multi-Device-Aggregation brauchst.
