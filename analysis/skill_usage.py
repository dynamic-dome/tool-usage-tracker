"""Skill-Usage-Report: welche Claude-Code-Skills werden wie oft und in welchen
Projekten genutzt? Datengrundlage fuer die Entscheidung behalten/deinstallieren
und global vs. lokal-projektspezifisch.

Der Tracker zeichnet jede `Skill`-Tool-Anwendung als Event auf; seit dem
build_summary-Skill-Fall traegt das Pre-Event den Skill-Namen in `summary`.
Skills, die installiert aber NIE genutzt wurden, tauchen hier per Definition
nicht auf — nach der Beobachtungsphase gegen die Skill-Liste gegenchecken.

Usage:
  python analysis/skill_usage.py [--since YYYY-MM-DD] [--data PFAD] [--min N]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
from collections import defaultdict

from _load import load_events

DEFAULT = Path(__file__).resolve().parents[1] / "data" / "events.jsonl"

# >=2 verschiedene Projekte -> ueberall gebraucht -> Kandidat fuer GLOBAL;
# genau 1 Projekt -> lokal-projektspezifischer Kandidat.
_GLOBAL_MIN_PROJECTS = 2

_UNKNOWN = "(unbekannt)"


def skill_usage_stats(events):
    """Aggregiert Skill-Invocations (tool_name=='Skill') zu Pro-Skill-Stats.

    Nur Pre-Events zaehlen: ein Skill-Call erzeugt je ein pre+post-Event, das
    Pre traegt den Skill-Namen. So wird jeder Aufruf genau einmal gezaehlt.
    Events ohne Skill-Namen (Altdaten vor dem build_summary-Fix) sammeln sich
    unter '(unbekannt)'.

    Rueckgabe: Liste von Dicts, sortiert nach count desc, dann Skill-Name:
      {skill, count, projects:[...], project_count, last_used, scope_hint}
    """
    by_skill = defaultdict(lambda: {"count": 0, "projects": set(), "last": ""})
    for ev in events:
        if ev.get("tool_name") != "Skill":
            continue
        if ev.get("phase", "pre") != "pre":
            continue
        name = (ev.get("summary") or "").strip() or _UNKNOWN
        rec = by_skill[name]
        rec["count"] += 1
        rec["projects"].add(ev.get("project") or "unknown")
        ts = ev.get("ts_local") or ""
        if ts > rec["last"]:
            rec["last"] = ts

    out = []
    for name, rec in by_skill.items():
        projects = sorted(rec["projects"])
        if len(projects) >= _GLOBAL_MIN_PROJECTS:
            scope = "global"
        elif projects:
            scope = f"lokal:{projects[0]}"
        else:
            scope = "lokal:?"
        out.append({
            "skill": name,
            "count": rec["count"],
            "projects": projects,
            "project_count": len(projects),
            "last_used": rec["last"],
            "scope_hint": scope,
        })
    out.sort(key=lambda r: (-r["count"], r["skill"]))
    return out


def _force_utf8_stdout():
    # Windows-Konsole ist per Default cp1252 und crasht an Sonderzeichen.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def _print_report(stats, min_count):
    shown = [s for s in stats if s["count"] >= min_count]
    total_calls = sum(s["count"] for s in stats)
    print(f"\033[1mSkill-Usage Report\033[0m  —  {len(stats)} Skills, "
          f"{total_calls} Aufrufe")
    if not shown:
        print("  (keine Skill-Events — Beobachtung laeuft erst an, "
              "oder --min zu hoch)")
        return
    print(f"\n  {'Skill':<40} {'Calls':>6}  {'Proj':>4}  {'Scope':<22} Zuletzt")
    print("  " + "-" * 92)
    for s in shown:
        print(f"  {s['skill']:<40} {s['count']:>6}  {s['project_count']:>4}  "
              f"{s['scope_hint']:<22} {s['last_used']}")

    glob = [s for s in shown if s["scope_hint"] == "global"]
    local = [s for s in shown if s["scope_hint"].startswith("lokal:")]
    print(f"\n  Global-Kandidaten (>= {_GLOBAL_MIN_PROJECTS} Projekte): "
          f"{', '.join(s['skill'] for s in glob) or '—'}")
    print(f"  Lokal-Kandidaten (1 Projekt): "
          f"{', '.join(s['skill'] for s in local) or '—'}")
    print("\n  Hinweis: Nie genutzte Skills erscheinen hier nicht — nach der "
          "Beobachtung gegen die installierte Skill-Liste gegenchecken.")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill-Usage-Report")
    ap.add_argument("--since", help="nur Events ab YYYY-MM-DD (ts_utc-Prefix)")
    ap.add_argument("--data", default=str(DEFAULT), help="Pfad zu events.jsonl")
    ap.add_argument("--min", type=int, default=1,
                    help="nur Skills mit >= N Aufrufen zeigen (Default 1)")
    args = ap.parse_args(argv)

    _force_utf8_stdout()
    events = load_events(args.data, since=args.since)
    stats = skill_usage_stats(events)
    _print_report(stats, args.min)
    return 0


if __name__ == "__main__":
    sys.exit(main())
