"""Self-contained HTML-Dashboard über Tool-Usage-Events.
Usage: python analysis/dashboard.py [--data PFAD] [--out PFAD] [--agent A] [--project P] [--since D]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
from collections import Counter

from _load import load_events

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "events.jsonl"
DEFAULT_OUT = ROOT / "dashboard.html"
CHARTJS = ROOT / "vendor" / "chart.umd.min.js"

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _aggregate(evs):
    tools = Counter(e.get("tool_name", "?") for e in evs)
    projects = Counter(e.get("project", "?") for e in evs)
    days = Counter(e.get("ts_local", "")[:10] for e in evs if e.get("ts_local"))
    # Heatmap Stunde x Wochentag
    heat = [[0] * 24 for _ in range(7)]
    for e in evs:
        tl = e.get("ts_local", "")
        if len(tl) >= 13:
            try:
                from datetime import datetime
                d = datetime.strptime(tl[:10], "%Y-%m-%d")
                heat[d.weekday()][int(tl[11:13])] += 1
            except Exception:
                pass
    return tools, projects, days, heat


def build_html(evs):
    tools, projects, days, heat = _aggregate(evs)
    chartjs = CHARTJS.read_text(encoding="utf-8") if CHARTJS.exists() else ""
    day_keys = sorted(days)
    kpis = {
        "total": len(evs),
        "uniq_tools": len(tools),
        "active_days": len(days),
        "top_tool": tools.most_common(1)[0][0] if tools else "—",
    }
    data = {
        "tools": dict(tools.most_common(15)),
        "projects": dict(projects.most_common(10)),
        "days": {k: days[k] for k in day_keys},
        "heat": heat,
        "weekdays": WEEKDAYS,
    }
    return _TEMPLATE.replace("/*CHARTJS*/", chartjs) \
        .replace("/*DATA*/", json.dumps(data)) \
        .replace("/*KPI*/", json.dumps(kpis))


_TEMPLATE = r"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<title>Tool-Usage Dashboard</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono&family=Outfit:wght@400;600&display=swap');
:root{--bg:#0a0e14;--card:#121821;--fg:#c5d1de;--accent:#39d0d8;--accent2:#f7768e}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font-family:'Outfit',sans-serif;padding:24px}
h1{font-family:'JetBrains Mono',monospace;color:var(--accent);letter-spacing:1px}
.kpis{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px}
.kpi{background:var(--card);border:1px solid #1e2733;border-radius:10px;padding:16px 24px;min-width:140px}
.kpi .v{font-family:'JetBrains Mono',monospace;font-size:28px;color:var(--accent)}
.kpi .l{font-size:12px;opacity:.7;text-transform:uppercase;letter-spacing:1px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.card{background:var(--card);border:1px solid #1e2733;border-radius:10px;padding:16px}
.card h2{font-family:'JetBrains Mono',monospace;font-size:14px;color:var(--accent2);margin:0 0 12px}
.full{grid-column:1/3}
canvas{max-height:300px}
</style></head><body>
<h1>▮ TOOL-USAGE COMMAND CENTER</h1>
<div class="kpis" id="kpis"></div>
<div class="grid">
  <div class="card"><h2>Top-Tools</h2><canvas id="cTools"></canvas></div>
  <div class="card"><h2>Top-Projekte</h2><canvas id="cProj"></canvas></div>
  <div class="card full"><h2>Aktivität über Zeit</h2><canvas id="cDays"></canvas></div>
  <div class="card full"><h2>Heatmap — Stunde × Wochentag</h2><canvas id="cHeat"></canvas></div>
</div>
<script>/*CHARTJS*/</script>
<script>
const D=/*DATA*/, K=/*KPI*/;
const AC='#39d0d8', AC2='#f7768e', GRID='#1e2733', FG='#c5d1de';
Chart.defaults.color=FG; Chart.defaults.borderColor=GRID;
document.getElementById('kpis').innerHTML=[['Total Events',K.total],['Unique Tools',K.uniq_tools],['Aktive Tage',K.active_days],['Top-Tool',K.top_tool]].map(([l,v])=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`).join('');
new Chart(cTools,{type:'bar',data:{labels:Object.keys(D.tools),datasets:[{data:Object.values(D.tools),backgroundColor:AC}]},options:{indexAxis:'y',plugins:{legend:{display:false}}}});
new Chart(cProj,{type:'bar',data:{labels:Object.keys(D.projects),datasets:[{data:Object.values(D.projects),backgroundColor:AC2}]},options:{indexAxis:'y',plugins:{legend:{display:false}}}});
new Chart(cDays,{type:'line',data:{labels:Object.keys(D.days),datasets:[{data:Object.values(D.days),borderColor:AC,backgroundColor:'rgba(57,208,216,.15)',fill:true,tension:.3}]},options:{plugins:{legend:{display:false}}}});
const pts=[];D.heat.forEach((row,d)=>row.forEach((v,h)=>{if(v)pts.push({x:h,y:d,r:Math.min(4+v*2,20)})}));
new Chart(cHeat,{type:'bubble',data:{datasets:[{data:pts,backgroundColor:'rgba(57,208,216,.5)'}]},options:{plugins:{legend:{display:false}},scales:{x:{min:-.5,max:23.5,title:{display:true,text:'Stunde'}},y:{min:-.5,max:6.5,ticks:{callback:v=>D.weekdays[v]||''}}}});
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--agent")
    ap.add_argument("--project")
    ap.add_argument("--since")
    a = ap.parse_args()
    evs = load_events(a.data, agent=a.agent, project=a.project, since=a.since)
    Path(a.out).write_text(build_html(evs), encoding="utf-8")
    print(f"Dashboard geschrieben: {a.out}  ({len(evs)} Events)")


if __name__ == "__main__":
    main()
