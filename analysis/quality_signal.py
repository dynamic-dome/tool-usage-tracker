"""Quality-Signal-Export: Tool-Fehlerrate pro Session als JSON-Vertrag.

Erster Konsument ist das agentic-os quality-gate (C5-Kopplung Tracker x
agentic-os): der Gate-Lauf kann dieses Skript aufrufen und success_rate /
failures der juengsten Session(s) als zusaetzliches Quality-Signal werten.

Vertrag (schema_v 1):
  {
    "schema_v": 1,
    "generated_at": "<ISO-UTC>",
    "overall":  {"sessions", "tool_calls", "failures", "mutating_failures",
                  "success_rate"},
    "sessions": [{"session_id", "project", "agent", "ts_first", "ts_last",
                   "tool_calls", "failures", "mutating_failures",
                   "success_rate", "top_failing_tools": [{"tool", "failures"}]}]
  }

Zaehlbasis ist ehrlich: nur GEPAARTE Spans mit bekanntem ok (True/False).
Unpaired Spans (ok=None) fliessen nie in die Rate ein; Sessions ganz ohne
ok-Signal erscheinen nicht in der Liste. success_rate ist None, wenn es
keinerlei Zaehlbasis gibt.

Usage:
  python -X utf8 analysis/quality_signal.py [--agent A] [--project P]
      [--since YYYY-MM-DD] [--data PFAD] [--exclude-self]
      [--limit N] [--top N] [--out DATEI]

Cold-Path (Auswertung), beruehrt den Hook nie. Nur Stdlib.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone

from _load import load_events, pair_events

DEFAULT = Path(__file__).resolve().parents[1] / "data" / "events.jsonl"


def quality_signal(spans, limit=0, top_n=3):
    """Aggregiert gepaarte Spans mit bekanntem ok zu einem Quality-Signal.

    limit kuerzt nur die sessions-Liste (neueste zuerst); overall bleibt
    immer ueber ALLE Sessions gerechnet, damit der Konsument den Kontext
    nicht verliert."""
    per = defaultdict(lambda: {
        "tool_calls": 0, "failures": 0, "mutating_failures": 0,
        "fail_tools": defaultdict(int),
        "project": None, "agent": None, "ts_first": None, "ts_last": None,
    })

    for s in spans:
        if not s.get("paired") or s.get("ok") is None:
            continue
        sess = per[s.get("session_id")]
        sess["tool_calls"] += 1
        sess["project"] = sess["project"] or s.get("project")
        sess["agent"] = sess["agent"] or s.get("agent")
        for key in ("ts_start", "ts_end"):
            ts = s.get(key)
            if ts:
                if sess["ts_first"] is None or ts < sess["ts_first"]:
                    sess["ts_first"] = ts
                if sess["ts_last"] is None or ts > sess["ts_last"]:
                    sess["ts_last"] = ts
        if s.get("ok") is False:
            sess["failures"] += 1
            sess["fail_tools"][s.get("tool_name") or "?"] += 1
            if s.get("mutating"):
                sess["mutating_failures"] += 1

    sessions = []
    for session_id, sess in per.items():
        calls = sess["tool_calls"]
        top = sorted(sess["fail_tools"].items(), key=lambda kv: (-kv[1], kv[0]))
        sessions.append({
            "session_id": session_id,
            "project": sess["project"],
            "agent": sess["agent"],
            "ts_first": sess["ts_first"],
            "ts_last": sess["ts_last"],
            "tool_calls": calls,
            "failures": sess["failures"],
            "mutating_failures": sess["mutating_failures"],
            "success_rate": (calls - sess["failures"]) / calls if calls else None,
            "top_failing_tools": [
                {"tool": tool, "failures": n} for tool, n in top[:top_n]
            ],
        })
    sessions.sort(key=lambda s: s["ts_last"] or "", reverse=True)

    total_calls = sum(s["tool_calls"] for s in sessions)
    total_failures = sum(s["failures"] for s in sessions)
    overall = {
        "sessions": len(sessions),
        "tool_calls": total_calls,
        "failures": total_failures,
        "mutating_failures": sum(s["mutating_failures"] for s in sessions),
        "success_rate": (total_calls - total_failures) / total_calls
        if total_calls else None,
    }

    return {
        "schema_v": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "sessions": sessions[:limit] if limit and limit > 0 else sessions,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agent")
    ap.add_argument("--project")
    ap.add_argument("--since")
    ap.add_argument("--data", default=str(DEFAULT))
    ap.add_argument("--exclude-self", action="store_true",
                    help="Events des Mess-Tools selbst ausblenden")
    ap.add_argument("--limit", type=int, default=0,
                    help="nur die N neuesten Sessions listen (0 = alle)")
    ap.add_argument("--top", type=int, default=3,
                    help="Top-N fehlschlagende Tools pro Session")
    ap.add_argument("--out", help="Ziel-JSON-Datei (Default: stdout)")
    a = ap.parse_args()

    evs = load_events(a.data, agent=a.agent, project=a.project, since=a.since,
                      exclude_self=a.exclude_self)
    sig = quality_signal(pair_events(evs), limit=a.limit, top_n=a.top)
    payload = json.dumps(sig, ensure_ascii=False, indent=2) + "\n"

    if a.out:
        Path(a.out).write_text(payload, encoding="utf-8")
        print(f"[quality-signal] wrote {a.out} "
              f"({sig['overall']['sessions']} sessions, "
              f"{sig['overall']['failures']} failures)", file=sys.stderr)
    else:
        sys.stdout.write(payload)


if __name__ == "__main__":
    main()
