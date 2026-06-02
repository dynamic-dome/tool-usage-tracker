"""Live-Dashboard-Server (Stdlib http.server, an 127.0.0.1 gebunden — Regel 16).
Enthält KEINE Aggregationslogik — nur HTTP + Delegation an _load.py.
Usage: python analysis/server.py [--data PFAD] [--port N]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from _load import (load_events, pair_events, success_rate_by,
                   duration_stats_by, path_activity)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "events.jsonl"
CHARTJS = ROOT / "vendor" / "chart.umd.min.js"


def parse_query(query_string):
    raw = parse_qs(query_string)
    return {k: v[0] for k, v in raw.items()}


def _distinct_sorted(events, key):
    """Sortierte, eindeutige nicht-leere Werte eines Feldes — speist die
    Filter-Dropdowns im Dashboard."""
    return sorted({v for ev in events if (v := ev.get(key))})


def spans_payload(data_path, params):
    evs = load_events(data_path,
                      agent=params.get("agent"),
                      project=params.get("project"),
                      since=params.get("since"),
                      exclude_self=params.get("exclude_self") in ("1", "true", "True"))
    spans = pair_events(evs)
    # Auswahl-Optionen aus ALLEN Events (ungefiltert) — sonst könnte man von
    # einem aktiven Filter nie auf einen anderen Wert umschalten.
    all_evs = load_events(data_path)
    return {
        "count": len([s for s in spans if s.get("paired")]),
        "total_events": len(evs),
        "spans": spans,
        "agents": _distinct_sorted(all_evs, "agent"),
        "projects": _distinct_sorted(all_evs, "project"),
        "success_by_tool": success_rate_by(spans, "tool_name"),
        "success_by_project": success_rate_by(spans, "project"),
        "duration_by_tool": duration_stats_by(spans, "tool_name"),
        "path_activity": path_activity(spans),
    }


def make_handler(data_path):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass  # keine Konsolen-Spam

        def _send(self, code, body, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype + "; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/spans":
                params = parse_query(parsed.query)
                try:
                    self._send(200, json.dumps(spans_payload(data_path, params)))
                except Exception as e:
                    self._send(500, json.dumps({"error": str(e)}))
            elif parsed.path == "/":
                self._send(200, index_html(), "text/html")
            else:
                self._send(404, json.dumps({"error": "not found"}))
    return Handler


def index_html():
    """Vollständiges Dashboard-Dokument. Chart.js wird zur Aufruf-Zeit aus
    vendor/ inline gebettet (kein CDN, Regel). Fehlt die Datei → leerer String
    (graceful degrade)."""
    chartjs = CHARTJS.read_text(encoding="utf-8") if CHARTJS.exists() else ""
    return _PAGE_TEMPLATE.replace("/*CHARTJS*/", chartjs)


_PAGE_TEMPLATE = r"""<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tool-Usage Live-Dashboard</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono&family=Outfit:wght@400;600&display=swap');
:root{--bg:#0a0e14;--card:#121821;--border:#1e2733;--fg:#c5d1de;--accent:#39d0d8;--accent2:#f7768e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:'Outfit',sans-serif;padding:20px}
h1{font-family:'JetBrains Mono',monospace;color:var(--accent);letter-spacing:1px;font-size:20px;margin:0}
header{display:flex;flex-wrap:wrap;align-items:center;gap:16px;margin-bottom:20px;padding-bottom:16px;border-bottom:1px solid var(--border)}
.tabs{display:flex;gap:8px}
.tab{font-family:'JetBrains Mono',monospace;font-size:13px;background:var(--card);color:var(--fg);border:1px solid var(--border);border-radius:8px;padding:8px 16px;cursor:pointer}
.tab.active{color:var(--bg);background:var(--accent);border-color:var(--accent)}
.filters{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-left:auto}
.filters label{font-size:12px;opacity:.75;display:flex;flex-direction:column;gap:3px}
.filters input[type=text],.filters input[type=date]{background:var(--card);color:var(--fg);border:1px solid var(--border);border-radius:6px;padding:6px 8px;font-family:'JetBrains Mono',monospace;font-size:12px;width:140px}
.filters input[type=date]::-webkit-calendar-picker-indicator{filter:invert(.8)}
.filters .chk{flex-direction:row;align-items:center;gap:6px}
button.refresh{font-family:'JetBrains Mono',monospace;font-size:13px;background:var(--accent2);color:var(--bg);border:none;border-radius:8px;padding:9px 18px;cursor:pointer;font-weight:600}
.kpis{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px 22px;min-width:150px}
.kpi .v{font-family:'JetBrains Mono',monospace;font-size:26px;color:var(--accent)}
.kpi .l{font-size:11px;opacity:.7;text-transform:uppercase;letter-spacing:1px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
.card{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px}
.card h2{font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--accent2);margin:0 0 12px;text-transform:uppercase;letter-spacing:1px}
.full{grid-column:1/3}
canvas{max-height:300px}
.treemap{display:flex;flex-wrap:wrap;gap:4px;min-height:120px}
.tile{flex-grow:1;flex-basis:90px;min-height:54px;border-radius:6px;padding:8px;cursor:pointer;color:#0a0e14;font-family:'JetBrains Mono',monospace;font-size:11px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;border:1px solid rgba(0,0,0,.25)}
.tile.sel{outline:2px solid var(--accent2);outline-offset:-2px}
.tile .c{font-size:15px;font-weight:600}
.tree{font-family:'JetBrains Mono',monospace;font-size:12px;line-height:1.7;max-height:340px;overflow:auto}
.tree .node{display:flex;align-items:center;gap:8px;padding:1px 0}
.tree .node.hl{background:rgba(247,118,142,.12);border-radius:4px}
.badge{font-size:10px;padding:1px 7px;border-radius:10px;color:#0a0e14;font-weight:600}
.muted{opacity:.55;font-size:11px}
.tl-session{margin-bottom:18px}
.tl-session h3{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--accent);margin:0 0 6px}
.tl-session h3 .proj{color:var(--fg);opacity:.6;font-weight:400;margin-left:8px}
.tl-row{display:flex;flex-wrap:wrap;gap:4px;align-items:center}
.tl-bar{height:26px;border-radius:5px;padding:0 7px;display:flex;align-items:center;overflow:hidden;white-space:nowrap;font-family:'JetBrains Mono',monospace;font-size:11px;color:#0a0e14;cursor:default}
.tl-bar.fail{color:#0a0e14}
.tl-bar.open{background:transparent!important;border:1px dashed var(--accent);color:var(--accent)}
</style></head><body>
<header>
  <h1>&#9646; TOOL-USAGE COMMAND CENTER</h1>
  <div class="tabs">
    <button class="tab active" id="btnAnalytics">Analytics</button>
    <button class="tab" id="btnTimeline">Timeline</button>
  </div>
  <div class="filters">
    <label>agent<input type="text" id="fAgent" list="dlAgents" placeholder="alle"></label>
    <datalist id="dlAgents"></datalist>
    <label>project<input type="text" id="fProject" list="dlProjects" placeholder="alle"></label>
    <datalist id="dlProjects"></datalist>
    <label>since<input type="date" id="fSince"></label>
    <label class="chk"><input type="checkbox" id="fExcludeSelf">exclude_self</label>
    <button class="refresh" id="btnRefresh">&#8635; Refresh</button>
  </div>
</header>

<div id="tabAnalytics">
  <div class="kpis" id="kpis"></div>
  <div class="grid">
    <div class="card"><h2>Top-Tools</h2><canvas id="cTools"></canvas></div>
    <div class="card"><h2>Fehlerrate pro Tool</h2><canvas id="cErr"></canvas></div>
    <div class="card full"><h2>Aktivit&auml;t &uuml;ber Zeit</h2><canvas id="cDays"></canvas></div>
    <div class="card full"><h2>Pfad-Aktivit&auml;t &mdash; Treemap</h2>
      <div class="muted" id="tmHint" style="margin-bottom:8px">Klick auf eine Kachel filtert den Heat-Baum darunter.</div>
      <div class="treemap" id="treemap"></div>
    </div>
    <div class="card full"><h2>Heat-Baum</h2><div class="tree" id="tree"></div></div>
  </div>
</div>

<div id="tabTimeline" style="display:none">
  <div class="card full"><h2>Timeline &mdash; Flow pro Session</h2>
    <div class="muted" style="margin-bottom:10px">Jede Zeile = eine Session. Balkenbreite &prop; Dauer. Gestrichelt = ungepaart (unvollst&auml;ndig).</div>
    <div id="timeline"></div>
  </div>
</div>

<script>/*CHARTJS*/</script>
<script>
"use strict";
var AC='#39d0d8', AC2='#f7768e', GRID='#1e2733', FG='#c5d1de';
if (window.Chart) { Chart.defaults.color = FG; Chart.defaults.borderColor = GRID; }
var charts = {};
var selectedPath = null;

function $(id){ return document.getElementById(id); }

function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}

function destroyChart(key){
  if (charts[key]) { charts[key].destroy(); charts[key] = null; }
}

function heatColor(frac){
  // frac 0..1 -> dunkles Cyan zu hellem Cyan
  var t = Math.max(0, Math.min(1, frac));
  var r = Math.round(20 + t * 35);
  var g = Math.round(60 + t * 148);
  var b = Math.round(75 + t * 141);
  return 'rgb(' + r + ',' + g + ',' + b + ')';
}

function lastSegs(p, n){
  var parts = String(p).split(/[\/\\]+/).filter(function(s){ return s.length; });
  return parts.slice(-n).join('/') || p;
}

function buildQuery(){
  var qs = [];
  var a = $('fAgent').value.trim();
  var pr = $('fProject').value.trim();
  var si = $('fSince').value.trim();
  if (a) qs.push('agent=' + encodeURIComponent(a));
  if (pr) qs.push('project=' + encodeURIComponent(pr));
  if (si) qs.push('since=' + encodeURIComponent(si));
  if ($('fExcludeSelf').checked) qs.push('exclude_self=1');
  return qs.join('&');
}

function renderKPIs(data){
  var spans = data.spans || [];
  var withOk = spans.filter(function(s){ return s.ok !== null && s.ok !== undefined; });
  var okCount = withOk.filter(function(s){ return s.ok === true; }).length;
  var rate = withOk.length ? (okCount / withOk.length * 100) : 0;
  // Aggregierte Dauer über alle Tools (avg + p95 ehrlich gewichtet/approx)
  var durs = [];
  spans.forEach(function(s){ if (s.duration_ms !== null && s.duration_ms !== undefined) durs.push(s.duration_ms); });
  durs.sort(function(x, y){ return x - y; });
  var avg = durs.length ? Math.round(durs.reduce(function(a, b){ return a + b; }, 0) / durs.length) : 0;
  var p95 = durs.length ? durs[Math.min(durs.length - 1, Math.floor(durs.length * 0.95))] : 0;
  var rows = [
    ['Paired Calls', data.count != null ? data.count : 0],
    ['Erfolgsrate', rate.toFixed(1) + '%'],
    ['&#216; Dauer (alle)', avg + ' ms'],
    ['p95 Dauer (alle)', p95 + ' ms']
  ];
  $('kpis').innerHTML = rows.map(function(rc){
    return '<div class="kpi"><div class="v">' + rc[1] + '</div><div class="l">' + rc[0] + '</div></div>';
  }).join('');
}

function renderTools(data){
  var counts = {};
  (data.spans || []).forEach(function(s){
    var t = s.tool_name || '?';
    counts[t] = (counts[t] || 0) + 1;
  });
  var entries = Object.keys(counts).map(function(k){ return [k, counts[k]]; });
  entries.sort(function(a, b){ return b[1] - a[1]; });
  entries = entries.slice(0, 15);
  destroyChart('tools');
  if (!window.Chart) return;
  charts.tools = new Chart($('cTools'), {
    type: 'bar',
    data: { labels: entries.map(function(e){ return e[0]; }),
            datasets: [{ data: entries.map(function(e){ return e[1]; }), backgroundColor: AC }] },
    options: { indexAxis: 'y', plugins: { legend: { display: false } } }
  });
}

function renderDays(data){
  var byDay = {};
  (data.spans || []).forEach(function(s){
    var d = (s.ts_start || '').slice(0, 10);
    if (d) byDay[d] = (byDay[d] || 0) + 1;
  });
  var keys = Object.keys(byDay).sort();
  destroyChart('days');
  if (!window.Chart) return;
  charts.days = new Chart($('cDays'), {
    type: 'line',
    data: { labels: keys,
            datasets: [{ data: keys.map(function(k){ return byDay[k]; }),
                         borderColor: AC, backgroundColor: 'rgba(57,208,216,.15)', fill: true, tension: .3 }] },
    options: { plugins: { legend: { display: false } } }
  });
}

function renderErr(data){
  var sbt = data.success_by_tool || {};
  var keys = Object.keys(sbt);
  var vals = keys.map(function(k){ return (1 - sbt[k]) * 100; });
  destroyChart('err');
  if (!window.Chart) return;
  charts.err = new Chart($('cErr'), {
    type: 'bar',
    data: { labels: keys,
            datasets: [{ data: vals, backgroundColor: AC2 }] },
    options: { indexAxis: 'y',
               plugins: { legend: { display: false } },
               scales: { x: { suggestedMax: 100, title: { display: true, text: 'Fehlerrate %' } } } }
  });
}

function renderTreemap(data){
  var pa = data.path_activity || {};
  var paths = Object.keys(pa);
  var max = 0;
  paths.forEach(function(p){ if (pa[p] > max) max = pa[p]; });
  var tm = $('treemap');
  tm.innerHTML = '';
  if (!paths.length) { tm.innerHTML = '<div class="muted">Keine Pfad-Daten.</div>'; return; }
  paths.sort(function(a, b){ return pa[b] - pa[a]; });
  paths.forEach(function(p){
    var cnt = pa[p];
    var frac = max ? cnt / max : 0;
    var tile = document.createElement('div');
    tile.className = 'tile' + (p === selectedPath ? ' sel' : '');
    tile.style.flexGrow = String(Math.max(1, cnt));
    tile.style.background = heatColor(frac);
    tile.title = p;
    tile.innerHTML = '<div>' + esc(lastSegs(p, 2)) + '</div><div class="c">' + cnt + '</div>';
    tile.addEventListener('click', function(){
      selectedPath = (selectedPath === p) ? null : p;
      renderTreemap(data);
      renderTree(data);
    });
    tm.appendChild(tile);
  });
}

function renderTree(data){
  var pa = data.path_activity || {};
  var paths = Object.keys(pa);
  // Aggregiere Counts pro Pfad-Präfix-Knoten
  var nodes = {};   // joinedKey -> {seg, depth, count, key}
  var max = 0;
  paths.forEach(function(p){
    if (selectedPath && p !== selectedPath) return;
    var parts = String(p).split(/[\/\\]+/).filter(function(s){ return s.length; });
    var acc = [];
    parts.forEach(function(seg, i){
      acc.push(seg);
      var key = acc.join('/');
      if (!nodes[key]) nodes[key] = { seg: seg, depth: i, count: 0, key: key };
      nodes[key].count += pa[p];
      if (nodes[key].count > max) max = nodes[key].count;
    });
  });
  var keys = Object.keys(nodes).sort();
  var tree = $('tree');
  tree.innerHTML = '';
  if (!keys.length) { tree.innerHTML = '<div class="muted">Keine Pfad-Daten.</div>'; return; }
  keys.forEach(function(key){
    var n = nodes[key];
    var frac = max ? n.count / max : 0;
    var row = document.createElement('div');
    row.className = 'node' + (selectedPath && key === selectedPath ? ' hl' : '');
    row.style.paddingLeft = (n.depth * 18) + 'px';
    var badge = '<span class="badge" style="background:' + heatColor(frac) + '">' + n.count + '</span>';
    row.innerHTML = '<span>' + esc(n.seg) + '</span>' + badge;
    tree.appendChild(row);
  });
}

function renderTimeline(data){
  var spans = data.spans || [];
  var tl = $('timeline');
  tl.innerHTML = '';
  if (!spans.length) { tl.innerHTML = '<div class="muted">Keine Spans.</div>'; return; }
  // Max-Dauer im View für relative Skalierung
  var maxDur = 0;
  spans.forEach(function(s){
    if (s.duration_ms !== null && s.duration_ms !== undefined && s.duration_ms > maxDur) maxDur = s.duration_ms;
  });
  if (maxDur <= 0) maxDur = 1;
  var MINW = 60, MAXW = 360;
  // Gruppieren nach session_id
  var groups = {};   // sid -> {sid, project, spans:[]}
  var order = [];
  spans.forEach(function(s){
    var sid = s.session_id || '?';
    if (!groups[sid]) { groups[sid] = { sid: sid, project: s.project || '', spans: [] }; order.push(sid); }
    groups[sid].spans.push(s);
  });
  order.forEach(function(sid){
    var g = groups[sid];
    // Chronologisch; Spans ohne ts_start ans Ende
    g.spans.sort(function(a, b){
      var ta = a.ts_start || '', tb = b.ts_start || '';
      if (!ta && !tb) return 0;
      if (!ta) return 1;
      if (!tb) return -1;
      return ta < tb ? -1 : (ta > tb ? 1 : 0);
    });
    var shortSid = String(sid).length > 12 ? String(sid).slice(0, 8) + '…' : String(sid);
    var sec = document.createElement('div');
    sec.className = 'tl-session';
    var head = '<h3>' + esc(shortSid);
    if (g.project) head += '<span class="proj">' + esc(g.project) + '</span>';
    head += '</h3>';
    var rowHtml = '<div class="tl-row">';
    g.spans.forEach(function(s){
      var dur = (s.duration_ms !== null && s.duration_ms !== undefined) ? s.duration_ms : null;
      var w = dur !== null ? Math.round(MINW + (Math.min(dur, maxDur) / maxDur) * (MAXW - MINW)) : MINW;
      var cls = 'tl-bar';
      var style = 'width:' + w + 'px;';
      if (s.ok === true) { cls += ' ok'; style += 'background:' + AC + ';'; }
      else if (s.ok === false) { cls += ' fail'; style += 'background:' + AC2 + ';'; }
      else { cls += ' open'; }
      var tool = s.tool_name || '?';
      var summ = s.summary || '';
      var durTxt = dur !== null ? dur + 'ms' : 'offen';
      var labelParts = [tool];
      if (summ) labelParts.push(summ);
      labelParts.push(durTxt);
      var fullLabel = labelParts.join(' · ');
      var title = fullLabel;
      if (s.error) title += ' · ' + s.error;
      if (s.cwd) title += ' · ' + s.cwd;
      rowHtml += '<div class="' + cls + '" style="' + style + '" title="' + esc(title) + '">' + esc(fullLabel) + '</div>';
    });
    rowHtml += '</div>';
    sec.innerHTML = head + rowHtml;
    tl.appendChild(sec);
  });
}

function fillOptions(listId, values){
  var dl = $(listId);
  if (!dl) return;
  dl.innerHTML = (values || []).map(function(v){
    return '<option value="' + esc(v) + '">';
  }).join('');
}

function renderFilters(data){
  // Dropdown-Auswahl (datalist) aus den existierenden Werten befüllen.
  fillOptions('dlAgents', data.agents);
  fillOptions('dlProjects', data.projects);
}

function renderAll(data){
  renderFilters(data);
  renderKPIs(data);
  renderTools(data);
  renderDays(data);
  renderErr(data);
  renderTreemap(data);
  renderTree(data);
  renderTimeline(data);
}

async function refresh(){
  var url = '/api/spans' + (buildQuery() ? '?' + buildQuery() : '');
  try {
    var resp = await fetch(url);
    var data = await resp.json();
    renderAll(data);
  } catch (e) {
    $('kpis').innerHTML = '<div class="kpi"><div class="v">!</div><div class="l">Fehler: ' + esc(e && e.message ? e.message : e) + '</div></div>';
  }
}

function showTab(which){
  var aOn = (which === 'analytics');
  $('tabAnalytics').style.display = aOn ? '' : 'none';
  $('tabTimeline').style.display = aOn ? 'none' : '';
  $('btnAnalytics').classList.toggle('active', aOn);
  $('btnTimeline').classList.toggle('active', !aOn);
}

$('btnRefresh').addEventListener('click', refresh);
$('fExcludeSelf').addEventListener('change', refresh);
$('btnAnalytics').addEventListener('click', function(){ showTab('analytics'); });
$('btnTimeline').addEventListener('click', function(){ showTab('timeline'); });

refresh();
</script>
</body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(DEFAULT_DATA))
    ap.add_argument("--port", type=int, default=8770)
    a = ap.parse_args()
    httpd = HTTPServer(("127.0.0.1", a.port), make_handler(a.data))
    print(f"Dashboard-Server: http://127.0.0.1:{a.port}  (Ctrl-C zum Stoppen)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.server_close()


if __name__ == "__main__":
    main()
