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
