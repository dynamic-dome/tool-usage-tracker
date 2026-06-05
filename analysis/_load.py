"""Geteilter JSONL-Loader für report.py und dashboard.py."""
import json
from pathlib import Path

# Eigenes Projekt + die Auswertungs-Skripte: erzeugen Beobachter-Rauschen, wenn
# man den Tracker betrachtet (Feedback-Schleife). Per --exclude-self filterbar.
_SELF_PROJECT = "tool-usage-tracker"
_SELF_SUMMARY_MARKERS = ("analysis/report.py", "analysis\\report.py",
                         "analysis/dashboard.py", "analysis\\dashboard.py")


def _is_self_event(ev):
    if ev.get("project") == _SELF_PROJECT:
        return True
    summary = str(ev.get("summary", ""))
    return any(m in summary for m in _SELF_SUMMARY_MARKERS)


def _rotated_part_files(path):
    """Rotierte Teil-Dateien events.N.<suffix> neben `path`, nach N sortiert.
    Diese entstehen durch die Hot-Path-Rotation (events.jsonl ->
    events.1.jsonl, events.2.jsonl, ...). Aelteste (kleinstes N) zuerst, damit
    sie chronologisch VOR der aktiven Datei gelesen werden."""
    stem = path.stem            # "events"
    suffix = path.suffix        # ".jsonl"
    parts = []
    for cand in path.parent.glob(f"{stem}.*{suffix}"):
        mid = cand.name[len(stem) + 1: -len(suffix)] if suffix else cand.name
        if mid.isdigit():
            parts.append((int(mid), cand))
    return [c for _, c in sorted(parts)]


def _iter_event_files(path):
    """Alle Event-Dateien in Lesereihenfolge: rotierte Teile (aelteste zuerst),
    dann die aktive Datei."""
    files = _rotated_part_files(path)
    if path.exists():
        files.append(path)
    return files


def load_events(path, agent=None, project=None, since=None,
                exclude_self=False, tail=None):
    path = Path(path)
    out = []
    for fpath in _iter_event_files(path):
        with fpath.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except Exception:
                    continue
                if agent and ev.get("agent") != agent:
                    continue
                if project and ev.get("project") != project:
                    continue
                if since and str(ev.get("ts_utc", "")) < since:
                    continue
                if exclude_self and _is_self_event(ev):
                    continue
                out.append(ev)
    if tail is not None and tail >= 0:
        return out[-tail:] if tail else []
    return out


def _phase(ev):
    # Schema-v1-Events haben kein phase-Feld -> als "pre" behandeln
    return ev.get("phase", "pre")


def _duration_ms(start_ts, end_ts):
    from datetime import datetime
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
    try:
        a = datetime.strptime(start_ts, fmt)
        b = datetime.strptime(end_ts, fmt)
        return int((b - a).total_seconds() * 1000)
    except Exception:
        return None


def _ts_to_ms(ts):
    """ISO-Zeitstempel ('%Y-%m-%dT%H:%M:%S.%fZ') -> Millisekunden (float, ab
    Epoch). None bei unparsebarer/leerer Eingabe."""
    from datetime import datetime, timezone
    if not ts:
        return None
    try:
        dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        return dt.timestamp() * 1000.0
    except Exception:
        return None


def _intra_session_gaps(spans):
    """Alle Inter-Span-Gaps (ms) innerhalb je einer Session. Ein Gap ist die
    Pause zwischen ts_end eines Spans und ts_start des chronologisch naechsten
    DERSELBEN Session. Nur Spans mit gueltigem ts_start; negative Gaps (Ueber-
    lappung) werden auf 0 geklammert. Spans ohne session_id (None) werden
    uebersprungen und nicht zu einem Pseudo-Bucket gepoolt."""
    from collections import defaultdict
    by_sid = defaultdict(list)
    for s in spans:
        start = _ts_to_ms(s.get("ts_start"))
        if start is None:
            continue
        sid = s.get("session_id")
        if sid is None:
            continue
        end = _ts_to_ms(s.get("ts_end"))
        by_sid[sid].append((start, end if end is not None else start))
    gaps = []
    for items in by_sid.values():
        items.sort(key=lambda t: t[0])
        for (s_prev, e_prev), (s_next, _e) in zip(items, items[1:]):
            gaps.append(max(0.0, s_next - e_prev))
    return gaps


def compute_turn_gap_threshold(spans):
    """Global-adaptive Turn-Gap-Schwelle (ms) ueber den ganzen View. Schwelle =
    median + 3*MAD aller Intra-Session-Gaps, hart geklammert auf [5000, 120000].
    Fallback 30000, wenn < 8 Gaps (zu wenig Daten fuer stabile Schaetzung).
    Deterministisch."""
    gaps = _intra_session_gaps(spans)
    if len(gaps) < 8:
        return 30000
    gaps.sort()
    n = len(gaps)
    median = gaps[n // 2] if n % 2 else (gaps[n // 2 - 1] + gaps[n // 2]) / 2.0
    devs = sorted(abs(g - median) for g in gaps)
    mad = devs[n // 2] if n % 2 else (devs[n // 2 - 1] + devs[n // 2]) / 2.0
    threshold = median + 3.0 * mad
    return int(max(5000, min(120000, threshold)))


def _classification(ev):
    """Bash-Klassifizierungsfelder aus einem Pre-Event mit definierten Defaults.
    Nicht-Bash-Events/Altdaten ohne diese Felder bekommen leere/neutrale Werte
    statt zu fehlen (verhindert KeyError im Auswerte-Pfad, vermeidet Schema-Drift)."""
    return {
        "app": ev.get("app", ""),
        "operation": ev.get("operation", ""),
        "intent": ev.get("intent", ""),
        "risk": ev.get("risk", "unknown"),
        "mutating": bool(ev.get("mutating", False)),
    }


def _cost(ev):
    """Optionale Token-/Kosten-Felder aus einem Event (A-1). Claude Code liefert
    Usage NICHT im Tool-Result, sondern ueber OTLP-Metrics; ein separater Ingest-
    Schritt kann diese Felder ins Post-Event mergen. Fehlen sie (Normalfall),
    bleibt der Wert None — abwaertskompatibel, kein Schema-Zwang."""
    def _num(key):
        v = ev.get(key)
        return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    return {
        "input_tokens": _num("input_tokens"),
        "output_tokens": _num("output_tokens"),
        "cache_read_tokens": _num("cache_read_tokens"),
        "cost_usd": _num("cost_usd"),
    }


def enrich_spans_with_tokens(spans, by_req):
    """Reichert Spans mit Token-/Kosten-Daten aus dem ccusage-Ingest an
    (analysis/ingest_ccusage.py -> data/tokens_by_request.json).

    `by_req` ist {request_id: {input_tokens, output_tokens, cache_read_tokens,
    cache_creation_tokens, cost_usd, tool_use_ids, ...}}. Der Join laeuft ueber
    span.tool_use_id -> requestId. Da eine assistant-Message (= ein Turn) nur EINE
    usage-Summe traegt, erben ALLE Tool-Calls desselben Turns dieselben Werte;
    das wird mit `turn_tokens=True` ehrlich markiert (es sind Turn-, keine
    Pro-Call-Zahlen). Spans ohne passende ID bleiben unveraendert (Token None).

    Nicht-mutierend: liefert NEUE Span-Dicts, faesst die Eingabe nicht an.
    """
    # Index tool_use_id -> (request_id, record), einmal aufbauen.
    by_tuid = {}
    for req, rec in (by_req or {}).items():
        for tuid in rec.get("tool_use_ids", []):
            by_tuid[tuid] = (req, rec)

    out = []
    for span in spans:
        new = dict(span)
        tuid = span.get("tool_use_id")
        hit = by_tuid.get(tuid) if tuid else None
        if hit:
            req, rec = hit
            new["request_id"] = req
            new["input_tokens"] = rec.get("input_tokens")
            new["output_tokens"] = rec.get("output_tokens")
            new["cache_read_tokens"] = rec.get("cache_read_tokens")
            new["cache_creation_tokens"] = rec.get("cache_creation_tokens")
            if "cost_usd" in rec:
                new["cost_usd"] = rec["cost_usd"]
            new["turn_tokens"] = True
        else:
            # Keine Zuordnung -> Felder explizit auf None, damit der Auswerte-Pfad
            # einheitliche Keys sieht (kein KeyError), aber turn_tokens nicht True.
            new.setdefault("input_tokens", None)
            new.setdefault("output_tokens", None)
            new.setdefault("cache_read_tokens", None)
            new.setdefault("cache_creation_tokens", None)
        out.append(new)
    return out


def _paired_span(pre, post, method):
    span = {
        "tool_name": pre.get("tool_name"), "agent": pre.get("agent"),
        "session_id": pre.get("session_id"), "project": pre.get("project"),
        "summary": pre.get("summary"), "cwd": pre.get("cwd"),
        "ts_start": pre.get("ts_utc"), "ts_end": post.get("ts_utc"),
        "duration_ms": _duration_ms(pre.get("ts_utc", ""), post.get("ts_utc", "")),
        "ok": post.get("ok"), "error": post.get("error", ""), "paired": True,
        "pairing_method": method,
        "pairing_confidence": "exact" if method == "tool_use_id" else "fallback",
        "orphan_kind": "",
        "git_branch": pre.get("git_branch", ""),
        "file_ext": pre.get("file_ext", ""),
        # tool_use_id im Span behalten: Bruecke zum ccusage-Token-Ingest, der
        # Turn-Token ueber (tool_use_id -> requestId) joint (enrich_spans_with_tokens).
        "tool_use_id": pre.get("tool_use_id", ""),
    }
    span.update(_classification(pre))
    # Token-/Kosten-Usage gehoert zum Tool-RESULT -> aus dem Post-Event lesen.
    span.update(_cost(post))
    return span


def _orphan_post_span(ev):
    span = {
        "tool_name": ev.get("tool_name"), "agent": ev.get("agent"),
        "session_id": ev.get("session_id"), "project": None,
        "summary": None, "cwd": None,
        "ts_start": None, "ts_end": ev.get("ts_utc"),
        "duration_ms": None, "ok": None, "error": ev.get("error", ""),
        "paired": False, "pairing_method": "orphan",
        "pairing_confidence": "none", "orphan_kind": "post_without_pre",
    }
    # Post-Events tragen keine Klassifizierung -> neutrale Defaults.
    span.update(_classification(ev))
    span.update(_cost(ev))
    return span


def _unpaired_pre_span(pre):
    span = {
        "tool_name": pre.get("tool_name"), "agent": pre.get("agent"),
        "session_id": pre.get("session_id"), "project": pre.get("project"),
        "summary": pre.get("summary"), "cwd": pre.get("cwd"),
        "ts_start": pre.get("ts_utc"), "ts_end": None,
        "duration_ms": None, "ok": None, "error": "", "paired": False,
        "pairing_method": "orphan", "pairing_confidence": "none",
        "orphan_kind": "pre_without_post",
        "git_branch": pre.get("git_branch", ""),
        "file_ext": pre.get("file_ext", ""),
    }
    span.update(_classification(pre))
    # Unpaired-Pre hat (noch) kein Result -> Kosten unbekannt (None).
    span.update(_cost(pre))
    return span


def pair_events(events):
    """Verschmilzt pre+post zu Spans. Bevorzugt exakten Match per
    (session_id, tool_use_id); fällt auf (session_id, tool_name)-FIFO zurück,
    wenn keine tool_use_id vorhanden ist (Schema v1/v2 ohne ID, Altdaten).
    Ungepaarte Events bleiben erhalten (paired=False), zählen nicht in Aggregate."""
    spans = []
    ordered = sorted(events, key=lambda e: str(e.get("ts_utc", "")))

    # --- Pass 1: exakter Match per (session_id, tool_use_id) ---
    # Pres MIT nicht-leerer tool_use_id indexieren (session-scoped Key).
    pre_by_id = {}
    consumed = set()  # id() der bereits verbrauchten pre/post-Events
    for ev in ordered:
        if _phase(ev) != "pre":
            continue
        tuid = ev.get("tool_use_id")
        if tuid:
            pre_by_id.setdefault((ev.get("session_id"), tuid), []).append(ev)

    for ev in ordered:
        if _phase(ev) != "post":
            continue
        tuid = ev.get("tool_use_id")
        if not tuid:
            continue
        queue = pre_by_id.get((ev.get("session_id"), tuid), [])
        match = next((p for p in queue if id(p) not in consumed), None)
        if match is not None:
            consumed.add(id(match))
            consumed.add(id(ev))
            spans.append(_paired_span(match, ev, "tool_use_id"))
        # kein id-Pre gefunden -> Post bleibt für FIFO/Orphan-Pass übrig

    # --- Pass 2: FIFO über die noch nicht verbrauchten Events ---
    open_pre = {}
    used_pre = set()
    for ev in ordered:
        if _phase(ev) == "pre" and id(ev) not in consumed:
            key = (ev.get("session_id"), ev.get("tool_name"))
            open_pre.setdefault(key, []).append(ev)
    for ev in ordered:
        if _phase(ev) != "post" or id(ev) in consumed:
            continue
        key = (ev.get("session_id"), ev.get("tool_name"))
        queue = open_pre.get(key, [])
        match = next((p for p in queue if id(p) not in used_pre), None)
        if match is not None:
            used_pre.add(id(match))
            spans.append(_paired_span(match, ev, "fifo"))
        else:
            spans.append(_orphan_post_span(ev))

    # ungepaarte Pres (aus dem FIFO-Pool; id-gepaarte sind schon consumed)
    for queue in open_pre.values():
        for pre in queue:
            if id(pre) not in used_pre:
                spans.append(_unpaired_pre_span(pre))
    return spans


def pairing_summary(spans):
    from collections import Counter
    total = len(spans)
    paired = len([s for s in spans if s.get("paired")])
    methods = Counter(s.get("pairing_method", "unknown") for s in spans)
    orphans = Counter(s.get("orphan_kind") for s in spans if s.get("orphan_kind"))
    return {
        "spans": total,
        "paired": paired,
        "unpaired": total - paired,
        "pairing_rate": paired / total if total else 0.0,
        "by_method": dict(methods),
        "orphans": dict(orphans),
    }


def _paired_with_ok(spans):
    return [s for s in spans if s.get("paired") and s.get("ok") is not None]


def success_rate_by(spans, key):
    from collections import defaultdict
    agg = defaultdict(lambda: [0, 0])  # [ok, total]
    for s in _paired_with_ok(spans):
        k = s.get(key)
        agg[k][1] += 1
        if s.get("ok"):
            agg[k][0] += 1
    return {k: (ok / total if total else 0.0) for k, (ok, total) in agg.items()}


def duration_stats_by(spans, key):
    from collections import defaultdict
    buckets = defaultdict(list)
    for s in spans:
        if s.get("paired") and isinstance(s.get("duration_ms"), int):
            buckets[s.get(key)].append(s["duration_ms"])
    out = {}
    for k, vals in buckets.items():
        vals = sorted(vals)
        n = len(vals)
        avg = sum(vals) / n
        median = float(vals[n // 2]) if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
        p95 = vals[min(n - 1, int(round(0.95 * (n - 1))))]
        out[k] = {"avg": avg, "median": median, "p95": p95, "count": n}
    return out


def path_activity(spans):
    from collections import Counter
    return dict(Counter(s.get("cwd") for s in spans if s.get("cwd")))


def assign_turns(spans, threshold):
    """Setzt auf jedem Span ein session-lokales `turn_index` (0-basiert). Neuer
    Turn, sobald der Gap zum vorherigen Span derselben Session > threshold (ms).
    Spans ohne ts_start (Orphans) landen im LETZTEN Turn ihrer Session (bzw.
    Turn 0, wenn die Session keinen datierten Span hat). Mutiert die Spans in
    place und gibt die Liste zurueck."""
    from collections import defaultdict
    by_sid = defaultdict(list)
    orphans = defaultdict(list)
    for s in spans:
        if _ts_to_ms(s.get("ts_start")) is None:
            orphans[s.get("session_id")].append(s)
        else:
            by_sid[s.get("session_id")].append(s)
    for sid, items in by_sid.items():
        items.sort(key=lambda s: _ts_to_ms(s.get("ts_start")))
        turn = 0
        prev_end = None
        for s in items:
            start = _ts_to_ms(s.get("ts_start"))
            end = _ts_to_ms(s.get("ts_end"))
            if prev_end is not None and (start - prev_end) > threshold:
                turn += 1
            s["turn_index"] = turn
            prev_end = end if end is not None else start
    for sid, items in orphans.items():
        last_turn = by_sid[sid][-1]["turn_index"] if by_sid.get(sid) else 0
        for s in items:
            s["turn_index"] = last_turn
    return spans


def classification_breakdown(spans):
    """Aggregiert die Bash-Klassifizierung (app/intent/risk/mutating) ueber alle
    Spans (gepaart wie ungepaart). Liefert Counts pro risk-Stufe, pro app, pro
    intent und die Anzahl mutierender Aktionen — die Datengrundlage fuer die
    Risk-Facette + Mutating-KPI im Dashboard (B-01)."""
    from collections import Counter
    risk = Counter(s.get("risk", "unknown") or "unknown" for s in spans)
    by_app = Counter(a for s in spans if (a := s.get("app")))
    by_intent = Counter(i for s in spans if (i := s.get("intent")))
    mutating_count = sum(1 for s in spans if s.get("mutating"))
    return {
        "risk": dict(risk),
        "by_app": dict(by_app),
        "by_intent": dict(by_intent),
        "mutating_count": mutating_count,
    }


def _num_field(s, key):
    v = s.get(key)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def cost_breakdown(spans):
    """Aggregiert Token-/Kosten-Daten ueber alle Spans. None-Werte (fehlende
    Usage) zaehlen nicht in die Summen. `has_cost_data` ist True, sobald MINDESTENS
    ein Span echte Kostendaten traegt — das Dashboard blendet das Panel sonst aus,
    statt irrefuehrende Nullen zu zeigen. Kosten pro Tool/Agent fuer die Panels.

    TURN-DEDUP (ccusage-Ingest): Token gelten PRO TURN (ein requestId traegt EINE
    usage-Summe), aber jeder Tool-Call des Turns hat sie geerbt (turn_tokens=True).
    Die Sigma-KPIs duerfen einen Turn daher nur EINMAL zaehlen — sonst inflationiert
    ein Turn mit N Calls die Gesamtsumme um Faktor N. Wir deduplizieren die
    Sigma-Summen ueber `request_id`. Die Pro-Tool-/Pro-Agent-Aufschluesselung
    bleibt bewusst je Call (zeigt, an welchem Tool die Turn-Token haengen).
    Spans OHNE request_id (OTLP-Pfad/Altdaten) zaehlen wie bisher pro Span."""
    from collections import defaultdict

    cost_by_tool = defaultdict(float)
    cost_by_agent = defaultdict(float)
    has = False
    _FIELDS = ("input_tokens", "output_tokens", "cache_read_tokens", "cost_usd")

    # Sigma-Summen mit Turn-Dedup. Pro-Tool/Agent-Kosten zaehlen je Call; die
    # Sigma-Summen zaehlen jeden Turn (request_id) nur EINMAL. Wichtig: NICHT den
    # ersten Span eines Turns als "gesehen" markieren (der koennte tokenlos sein),
    # sondern die Turn-Werte separat sammeln und erst am Ende summieren — so ist
    # die Zaehlung reihenfolge-unabhaengig (Verifier-MAJOR 2026-06-05).
    sigma = defaultdict(float)        # nur fuer Spans OHNE request_id (pro Span)
    per_req = {}                      # request_id -> {feld: wert} (einmal pro Turn)
    for s in spans:
        c = _num_field(s, "cost_usd")
        if c is not None:
            has = True
            cost_by_tool[s.get("tool_name")] += c
            cost_by_agent[s.get("agent")] += c
        req = s.get("request_id")
        if req:
            rec = per_req.setdefault(req, {})
            for key in _FIELDS:
                if key not in rec:  # ersten getragenen Wert je Feld/Turn nehmen
                    v = _num_field(s, key)
                    if v is not None:
                        rec[key] = v
        else:
            for key in _FIELDS:
                v = _num_field(s, key)
                if v is not None:
                    sigma[key] += v

    # Turn-Werte (dedupliziert) auf die Sigma-Summen addieren.
    for rec in per_req.values():
        for key, v in rec.items():
            sigma[key] += v

    if not has:
        has = any(_num_field(s, k) is not None for s in spans
                  for k in ("input_tokens", "output_tokens", "cache_read_tokens"))
    return {
        "total_input_tokens": sigma["input_tokens"],
        "total_output_tokens": sigma["output_tokens"],
        "total_cache_read_tokens": sigma["cache_read_tokens"],
        "total_cost_usd": sigma["cost_usd"],
        "cost_by_tool": dict(cost_by_tool),
        "cost_by_agent": dict(cost_by_agent),
        "has_cost_data": has,
    }


def comparison(spans, key="agent"):
    """Run-Comparison (B-3): aggregiert Spans pro Gruppe (`key`, i.d.R. "agent"
    oder "session_id"), um zwei Runs nebeneinander zu vergleichen — speziell den
    Dual-Agent-Setup (Claude Code vs. Codex am selben Task). Pro Gruppe:

      tool_calls        Anzahl Spans gesamt (gepaart + ungepaart)
      paired            davon gepaart
      failures          gepaarte Spans mit ok is False
      retries           == failures (ehrlich: das Schema hat KEIN explizites
                        retry-Feld; ein fehlgeschlagener Call ist der beste
                        verfuegbare Retry-Proxy)
      success_rate      ok / (ok+fail) ueber gepaarte Spans mit bekanntem ok
      total_duration_ms Summe duration_ms ueber gepaarte Spans
      risk              {high,medium,low,unknown} Counts
      mutating_count    Anzahl mutierender Spans
      total_cost_usd    Summe cost_usd (None ignoriert)

    None-/fehlende Werte zaehlen nicht in Summen. Reine Anzeige-Aggregation,
    keine Mutation der Spans.
    """
    from collections import defaultdict

    def _blank():
        return {
            "tool_calls": 0, "paired": 0, "failures": 0, "retries": 0,
            "ok": 0, "total_duration_ms": 0,
            "risk": {"high": 0, "medium": 0, "low": 0, "unknown": 0},
            "mutating_count": 0, "total_cost_usd": 0.0,
        }

    groups = defaultdict(_blank)
    for s in spans:
        g = groups[s.get(key)]
        g["tool_calls"] += 1
        r = s.get("risk") or "unknown"
        if r not in g["risk"]:
            g["risk"][r] = 0
        g["risk"][r] += 1
        if s.get("mutating"):
            g["mutating_count"] += 1
        c = s.get("cost_usd")
        if isinstance(c, (int, float)) and not isinstance(c, bool):
            g["total_cost_usd"] += c
        if s.get("paired"):
            g["paired"] += 1
            d = s.get("duration_ms")
            if isinstance(d, int):
                g["total_duration_ms"] += d
            ok = s.get("ok")
            if ok is True:
                g["ok"] += 1
            elif ok is False:
                g["failures"] += 1
                g["retries"] += 1

    out = {}
    for k, g in groups.items():
        known = g["ok"] + g["failures"]
        out[k] = {
            "tool_calls": g["tool_calls"],
            "paired": g["paired"],
            "failures": g["failures"],
            "retries": g["retries"],
            "success_rate": (g["ok"] / known) if known else None,
            "total_duration_ms": g["total_duration_ms"],
            "risk": g["risk"],
            "mutating_count": g["mutating_count"],
            "total_cost_usd": round(g["total_cost_usd"], 6),
        }
    return out
