"""CLI-Report ueber die Hook-Eigenlaufzeit (B3, Frage A3: Prozess-Spawn-
Overhead von track_tool_use.py/track_tool_post.py teuer genug fuer eine
Batch-/Daemon-Variante?). Liest data/hook_latency.jsonl, berichtet
Count/avg/p50/p95 pro Hook (pre/post) + kombiniert.
Usage: python analysis/hook_latency_report.py [--data PFAD] [--threshold-ms 50]"""
import argparse
import json
import sys
from pathlib import Path

DEFAULT = Path(__file__).resolve().parents[1] / "data" / "hook_latency.jsonl"


def _record_files(path: Path):
    """Rotierte Teile hook_latency.N.jsonl (aelteste zuerst), dann die aktive Datei."""
    parts = []
    for cand in path.parent.glob(f"{path.stem}.*{path.suffix}"):
        mid = cand.name[len(path.stem) + 1: -len(path.suffix)]
        if mid.isdigit():
            parts.append((int(mid), cand))
    files = [c for _, c in sorted(parts)]
    if path.exists():
        files.append(path)
    return files


def load_records(path: Path):
    out = []
    for file in _record_files(Path(path)):
        with file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def stats(durations):
    vals = sorted(durations)
    n = len(vals)
    if n == 0:
        return {"count": 0, "avg": 0.0, "p50": 0.0, "p95": 0.0}
    avg = sum(vals) / n
    p50 = float(vals[n // 2]) if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
    p95 = vals[min(n - 1, int(round(0.95 * (n - 1))))]
    return {"count": n, "avg": avg, "p50": p50, "p95": p95}


def _force_utf8_stdout():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def main():
    _force_utf8_stdout()
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT))
    ap.add_argument("--threshold-ms", type=float, default=50.0)
    args = ap.parse_args()

    recs = load_records(Path(args.data))
    by_hook = {"pre": [], "post": []}
    for r in recs:
        hook = r.get("hook")
        dur = r.get("duration_ms")
        if hook in by_hook and isinstance(dur, (int, float)):
            by_hook[hook].append(dur)

    print(f"Hook-Latenz-Report — {len(recs)} Records aus {args.data}")
    combined = []
    for hook, durs in by_hook.items():
        s = stats(durs)
        combined.extend(durs)
        print(f"  {hook:<5} count={s['count']:>5}  avg={s['avg']:>7.2f}ms  "
              f"p50={s['p50']:>7.2f}ms  p95={s['p95']:>7.2f}ms")
    s = stats(combined)
    print(f"  {'total':<5} count={s['count']:>5}  avg={s['avg']:>7.2f}ms  "
          f"p50={s['p50']:>7.2f}ms  p95={s['p95']:>7.2f}ms")

    print(f"\nA3-Schwelle: {args.threshold_ms:.0f} ms/Call")
    if s["count"] and s["p95"] > args.threshold_ms:
        print("  -> ueber der Schwelle: Batch-/Daemon-Variante pruefen (Owner-Entscheidung).")
    elif s["count"]:
        print("  -> unter der Schwelle: Spawn-pro-Call lassen.")
    else:
        print("  -> keine Daten (data/hook_latency.jsonl leer oder fehlt).")


if __name__ == "__main__":
    main()
