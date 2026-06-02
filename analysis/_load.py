"""Geteilter JSONL-Loader für report.py und dashboard.py."""
import json
from pathlib import Path


def load_events(path, agent=None, project=None, since=None):
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
            out.append(ev)
    return out
