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


def load_events(path, agent=None, project=None, since=None, exclude_self=False):
    path = Path(path)
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
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


def _paired_span(pre, post, method):
    return {
        "tool_name": pre.get("tool_name"), "agent": pre.get("agent"),
        "session_id": pre.get("session_id"), "project": pre.get("project"),
        "summary": pre.get("summary"), "cwd": pre.get("cwd"),
        "ts_start": pre.get("ts_utc"), "ts_end": post.get("ts_utc"),
        "duration_ms": _duration_ms(pre.get("ts_utc", ""), post.get("ts_utc", "")),
        "ok": post.get("ok"), "error": post.get("error", ""), "paired": True,
        "pairing_method": method,
        "pairing_confidence": "exact" if method == "tool_use_id" else "fallback",
        "orphan_kind": "",
    }


def _orphan_post_span(ev):
    return {
        "tool_name": ev.get("tool_name"), "agent": ev.get("agent"),
        "session_id": ev.get("session_id"), "project": None,
        "summary": None, "cwd": None,
        "ts_start": None, "ts_end": ev.get("ts_utc"),
        "duration_ms": None, "ok": None, "error": ev.get("error", ""),
        "paired": False, "pairing_method": "orphan",
        "pairing_confidence": "none", "orphan_kind": "post_without_pre",
    }


def _unpaired_pre_span(pre):
    return {
        "tool_name": pre.get("tool_name"), "agent": pre.get("agent"),
        "session_id": pre.get("session_id"), "project": pre.get("project"),
        "summary": pre.get("summary"), "cwd": pre.get("cwd"),
        "ts_start": pre.get("ts_utc"), "ts_end": None,
        "duration_ms": None, "ok": None, "error": "", "paired": False,
        "pairing_method": "orphan", "pairing_confidence": "none",
        "orphan_kind": "pre_without_post",
    }


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
