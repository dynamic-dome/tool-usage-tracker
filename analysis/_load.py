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


def pair_events(events):
    """Verschmilzt pre+post zu Spans (session_id + tool_name + FIFO).
    Ungepaarte Events bleiben erhalten (paired=False), zählen nicht in Aggregate."""
    spans = []
    # offene Pres je (session_id, tool_name) als FIFO-Queue
    open_pre = {}
    used_pre = set()
    # erst alle Events in Reihenfolge; Post paart mit ältestem offenen Pre
    ordered = sorted(events, key=lambda e: str(e.get("ts_utc", "")))
    # Index der Pres pro Key
    for ev in ordered:
        if _phase(ev) == "pre":
            key = (ev.get("session_id"), ev.get("tool_name"))
            open_pre.setdefault(key, []).append(ev)
    for ev in ordered:
        if _phase(ev) != "post":
            continue
        key = (ev.get("session_id"), ev.get("tool_name"))
        queue = open_pre.get(key, [])
        match = None
        for pre in queue:
            if id(pre) not in used_pre:
                match = pre
                used_pre.add(id(pre))
                break
        if match is not None:
            spans.append({
                "tool_name": match.get("tool_name"), "agent": match.get("agent"),
                "session_id": match.get("session_id"), "project": match.get("project"),
                "summary": match.get("summary"), "cwd": match.get("cwd"),
                "ts_start": match.get("ts_utc"), "ts_end": ev.get("ts_utc"),
                "duration_ms": _duration_ms(match.get("ts_utc", ""), ev.get("ts_utc", "")),
                "ok": ev.get("ok"), "error": ev.get("error", ""), "paired": True,
            })
        else:
            # verwaistes Post
            spans.append({
                "tool_name": ev.get("tool_name"), "agent": ev.get("agent"),
                "session_id": ev.get("session_id"), "project": None,
                "summary": None, "cwd": None,
                "ts_start": None, "ts_end": ev.get("ts_utc"),
                "duration_ms": None, "ok": None, "error": ev.get("error", ""),
                "paired": False,
            })
    # ungepaarte Pres
    for queue in open_pre.values():
        for pre in queue:
            if id(pre) not in used_pre:
                spans.append({
                    "tool_name": pre.get("tool_name"), "agent": pre.get("agent"),
                    "session_id": pre.get("session_id"), "project": pre.get("project"),
                    "summary": pre.get("summary"), "cwd": pre.get("cwd"),
                    "ts_start": pre.get("ts_utc"), "ts_end": None,
                    "duration_ms": None, "ok": None, "error": "", "paired": False,
                })
    return spans


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
        median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
        p95 = vals[min(n - 1, int(round(0.95 * (n - 1))))]
        out[k] = {"avg": avg, "median": median, "p95": p95, "count": n}
    return out


def path_activity(spans):
    from collections import Counter
    return dict(Counter(s.get("cwd") for s in spans if s.get("cwd")))
