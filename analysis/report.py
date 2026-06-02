"""CLI-Report über Tool-Usage-Events.
Usage: python analysis/report.py [--agent A] [--project P] [--since YYYY-MM-DD] [--data PFAD]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
from collections import Counter

from _load import (duration_stats_by, load_events, pair_events, pairing_summary,
                   success_rate_by)

DEFAULT = Path(__file__).resolve().parents[1] / "data" / "events.jsonl"


def _bar(n, maxn, width=30):
    return "█" * (round(width * n / maxn) if maxn else 0)


def _section(title):
    print(f"\n\033[96m── {title} ─────────────────\033[0m")


def _force_utf8_stdout():
    # Windows-Konsole ist per Default cp1252 und crasht an →/█/… (Regel 10).
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass  # älteres Python / nicht-reconfigurierbarer Stream — best effort


def _raw_event_report(evs):
    ts = sorted(e.get("ts_utc", "") for e in evs)
    print(f"\033[1mTool-Usage Report\033[0m  —  {len(evs)} Events")
    print(f"Zeitraum: {ts[0]}  →  {ts[-1]}")

    _section("Top-Tools")
    tools = Counter(e.get("tool_name", "?") for e in evs)
    mx = max(tools.values())
    for name, n in tools.most_common(15):
        print(f"  {name:<22} {n:>5} {_bar(n, mx)}")

    _section("Events pro Projekt")
    for name, n in Counter(e.get("project", "?") for e in evs).most_common(10):
        print(f"  {name:<22} {n:>5}")

    _section("Events pro Tag (letzte 14)")
    days = Counter(e.get("ts_local", "")[:10] for e in evs)
    for day in sorted(days)[-14:]:
        print(f"  {day}  {days[day]:>5} {_bar(days[day], max(days.values()))}")

    _section("Aktivität pro Stunde")
    hours = Counter(int(e.get("ts_local", " " * 11 + '00')[11:13] or 0)
                    for e in evs if len(e.get("ts_local", "")) >= 13)
    mxh = max(hours.values()) if hours else 0
    for h in range(24):
        print(f"  {h:02d}h {hours.get(h,0):>5} {_bar(hours.get(h,0), mxh)}")


def _span_report(evs):
    spans = pair_events(evs)
    ts_values = [s.get("ts_start") or s.get("ts_end") or "" for s in spans]
    ts = sorted(t for t in ts_values if t)
    print(f"\033[1mTool-Usage Report\033[0m  —  {len(spans)} Spans / {len(evs)} Events")
    if ts:
        print(f"Zeitraum: {ts[0]}  →  {ts[-1]}")

    pairing = pairing_summary(spans)
    _section("Pairing")
    print(f"  Paired     {pairing['paired']:>5}")
    print(f"  Unpaired   {pairing['unpaired']:>5}")
    print(f"  Rate       {pairing['pairing_rate'] * 100:>5.1f}%")
    for name, n in sorted(pairing["by_method"].items()):
        print(f"  {name:<12} {n:>5}")
    for name, n in sorted(pairing["orphans"].items()):
        print(f"  {name:<18} {n:>5}")

    _section("Top-Tools")
    tools = Counter(s.get("tool_name", "?") for s in spans)
    mx = max(tools.values()) if tools else 0
    for name, n in tools.most_common(15):
        print(f"  {name:<22} {n:>5} {_bar(n, mx)}")

    _section("Dauer pro Tool")
    stats = duration_stats_by(spans, "tool_name")
    for name, st in sorted(stats.items(), key=lambda kv: kv[1]["p95"], reverse=True)[:15]:
        print(f"  {str(name):<22} count={st['count']:>3} avg={st['avg']:>7.1f}ms "
              f"median={st['median']:>7.1f}ms p95={st['p95']:>5}ms")

    _section("Erfolg pro Tool")
    rates = success_rate_by(spans, "tool_name")
    for name, rate in sorted(rates.items(), key=lambda kv: kv[1]):
        print(f"  {str(name):<22} {rate * 100:>5.1f}%")

    failures = [s for s in spans if s.get("paired") and s.get("ok") is False]
    _section("Failures")
    if not failures:
        print("  keine")
    for s in failures[:15]:
        print(f"  {s.get('tool_name','?'):<22} {s.get('error','')}")


def main():
    _force_utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent")
    ap.add_argument("--project")
    ap.add_argument("--since")
    ap.add_argument("--data", default=str(DEFAULT))
    ap.add_argument("--exclude-self", action="store_true",
                    help="Events des Mess-Tools selbst (Projekt + report/dashboard-Aufrufe) ausblenden")
    ap.add_argument("--raw-events", action="store_true",
                    help="Legacy-Sicht: Roh-Events statt gepaarter Spans zählen")
    a = ap.parse_args()

    evs = load_events(a.data, agent=a.agent, project=a.project, since=a.since,
                      exclude_self=a.exclude_self)
    if not evs:
        print("Keine Events gefunden.")
        return

    if a.raw_events:
        _raw_event_report(evs)
    else:
        _span_report(evs)


if __name__ == "__main__":
    main()
