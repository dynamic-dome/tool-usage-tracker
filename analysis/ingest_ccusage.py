"""ccusage-artiger Token-Ingest fuer das ABO-Modell (kein API-Key noetig).

Im Claude-Code-Abo gibt es keinen API-Zugang, ueber den man Tokens zaehlen
koennte. Claude Code schreibt aber pro Session ohnehin eine JSONL-Datei nach
``~/.claude/projects/<projekt-hash>/<session-id>.jsonl``. Jede ``assistant``-
Message darin traegt ein echtes ``usage``-Objekt:

    "usage": {"input_tokens": 17597, "cache_creation_input_tokens": 43521,
              "cache_read_input_tokens": 0, "output_tokens": 126, ...}

Genau diese Files parst auch das Community-Tool ``ccusage``
(github.com/ryoppippi/ccusage). Dieses Add-on liest sie lokal aus — keine
Telemetrie-Aktivierung, kein Netz, keine API.

ZUORDNUNG PRO TURN (ehrlich, nicht pro Tool-Call): Eine assistant-Message kann
MEHRERE ``tool_use``-Bloecke (``toolu_...``) enthalten, traegt aber nur EINE
usage-Summe fuer den ganzen Denk-Schritt. Wir ordnen die Token deshalb der
``requestId`` (= einem Turn) zu und merken uns die Liste der tool_use_ids dieses
Turns. Der Loader joint spaeter ``span.tool_use_id`` -> Turn-Record; mehrere
Calls desselben Turns zeigen dieselbe Turn-Summe (klar als Turn-Wert gelabelt).
Ein kuenstliches Aufsplitten waere erfundene Praezision (CC liefert es nicht).

ABGRENZUNG zu ``ingest_otlp.py``: jenes braucht manuell aktivierte OTLP-Metrics
(``CLAUDE_CODE_ENABLE_TELEMETRY=1``) und kann nur PRO SESSION zuordnen. Dieses
Add-on braucht keine Aktivierung und ordnet PRO TURN zu — die feinere, fuer das
Abo-Modell passende Quelle.

KOSTEN sind im Abo ein RECHNERISCHER GEGENWERT (du zahlst die Flatrate, nicht
diese Summe). Offline-Preistabelle pro Modell, USD pro 1 Mio. Token.

Der Hot-Path (die Hooks) wird NICHT angefasst. Reine Stdlib.
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "data" / "tokens_by_request.json"

# Offline-Preistabelle: USD pro 1 Mio. Token, je Modell.
# (input, output, cache_read, cache_creation). Quelle: oeffentliche Anthropic-
# Preise; bewusst als Konstante gepflegt, kein Netz-Lookup. Im Abo = rechnerisch.
_PRICES = {
    "claude-opus-4-8":   (15.0, 75.0, 1.50, 18.75),
    "claude-opus-4":     (15.0, 75.0, 1.50, 18.75),
    "claude-sonnet-4-6": (3.0,  15.0, 0.30,  3.75),
    "claude-sonnet-4-5": (3.0,  15.0, 0.30,  3.75),
    "claude-sonnet-4":   (3.0,  15.0, 0.30,  3.75),
    "claude-haiku-4-5":  (1.0,   5.0, 0.10,  1.25),
}

# Mapping CC-usage-Feldname -> unser Feldname.
_USAGE_FIELDS = {
    "input_tokens": "input_tokens",
    "output_tokens": "output_tokens",
    "cache_read_input_tokens": "cache_read_tokens",
    "cache_creation_input_tokens": "cache_creation_tokens",
}


def _projects_dir(projects_dir=None):
    """LAZY: CC-Projektverzeichnis. Argument > Env CLAUDE_PROJECTS_DIR >
    ~/.claude/projects (Default)."""
    if projects_dir is not None:
        return Path(projects_dir)
    env = os.environ.get("CLAUDE_PROJECTS_DIR")
    if env:
        return Path(env)
    return Path.home() / ".claude" / "projects"


def _int(v):
    try:
        if isinstance(v, bool):
            return 0
        return int(v)
    except (TypeError, ValueError):
        return 0


def _tool_use_ids(content):
    """tool_use-IDs (toolu_...) aus dem message.content-Array ziehen."""
    ids = []
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tid = block.get("id")
                if tid:
                    ids.append(tid)
    return ids


def _cost_for(model, rec):
    """Rechnerischer USD-Gegenwert aus der Preistabelle. Unbekanntes Modell -> 0.0."""
    price = _PRICES.get(model)
    if not price:
        return 0.0
    p_in, p_out, p_cr, p_cc = price
    usd = (rec.get("input_tokens", 0) * p_in
           + rec.get("output_tokens", 0) * p_out
           + rec.get("cache_read_tokens", 0) * p_cr
           + rec.get("cache_creation_tokens", 0) * p_cc) / 1_000_000
    return round(usd, 6)


def parse_session_files(projects_dir=None, with_cost=False):
    """Liest alle CC-Session-JSONL-Files und liefert {request_id: record}.

    record = {input_tokens, output_tokens, cache_read_tokens,
              cache_creation_tokens, session_id, model, tool_use_ids[, cost_usd]}

    Mehrere assistant-Messages mit derselben requestId werden summiert (defensiv;
    in der Praxis ist requestId pro Turn eindeutig). Graceful: fehlendes
    Verzeichnis -> {}, kaputte Zeilen werden uebersprungen.
    """
    base = _projects_dir(projects_dir)
    if not base.exists():
        return {}
    by_req = {}
    for jsonl in base.rglob("*.jsonl"):
        try:
            text = jsonl.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            msg = obj.get("message")
            if not isinstance(msg, dict):
                continue
            usage = msg.get("usage")
            if not isinstance(usage, dict):
                continue
            req = obj.get("requestId")
            if not req:
                continue
            rec = by_req.get(req)
            if rec is None:
                rec = {v: 0 for v in _USAGE_FIELDS.values()}
                rec["session_id"] = obj.get("sessionId", "")
                rec["model"] = msg.get("model", "")
                rec["tool_use_ids"] = []
                by_req[req] = rec
            for src, dst in _USAGE_FIELDS.items():
                rec[dst] += _int(usage.get(src))
            for tid in _tool_use_ids(msg.get("content")):
                if tid not in rec["tool_use_ids"]:
                    rec["tool_use_ids"].append(tid)
    if with_cost:
        for rec in by_req.values():
            rec["cost_usd"] = _cost_for(rec.get("model", ""), rec)
    return by_req


def aggregate_by_session(by_req):
    """{request_id: record} -> {session_id: summierte Tokens (+cost_usd)}."""
    acc = defaultdict(lambda: defaultdict(float))
    for rec in by_req.values():
        sid = rec.get("session_id", "")
        for field in _USAGE_FIELDS.values():
            acc[sid][field] += rec.get(field, 0)
        if "cost_usd" in rec:
            acc[sid]["cost_usd"] += rec["cost_usd"]
    out = {}
    for sid, d in acc.items():
        rec = {}
        for k, v in d.items():
            rec[k] = round(v, 6) if k == "cost_usd" else int(round(v))
        out[sid] = rec
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out = Path(argv[0]) if argv else DEFAULT_OUT
    by_req = parse_session_files(with_cost=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(by_req, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    by_sess = aggregate_by_session(by_req)
    total = sum(r.get("cost_usd", 0.0) for r in by_req.values())
    print(f"{len(by_req)} Turn(s) / {len(by_sess)} Session(s) -> {out}")
    print(f"rechnerischer Gegenwert (Abo): ${total:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
