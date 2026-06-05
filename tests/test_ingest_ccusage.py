"""Tests fuer den ccusage-Token-Ingest (Abo-Modell, kein API-Key).

Quelle sind Claude Codes lokale Session-JSONL-Files unter
~/.claude/projects/<hash>/<session>.jsonl. Jede assistant-Message traegt ein
echtes `usage`-Objekt + (im content) tool_use-Bloecke mit `toolu_...`-IDs, beide
unter derselben requestId. Token werden PRO requestId/Turn zugeordnet (CC liefert
es nicht feiner — keine erfundene Pro-Call-Aufteilung).

Isolation (§3): CLAUDE_PROJECTS_DIR zeigt auf tmp_path, es werden nie echte
Nutzerdaten gelesen oder geschrieben.
"""
import importlib.util
import json
from pathlib import Path

MOD = Path(__file__).resolve().parents[1] / "analysis" / "ingest_ccusage.py"
_spec = importlib.util.spec_from_file_location("ingest_ccusage", MOD)
icc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(icc)


def _assistant_line(session_id, request_id, model, usage, tool_ids=()):
    """Eine assistant-Zeile im echten CC-Schema (gekuerzt auf das Relevante)."""
    content = [{"type": "tool_use", "id": tid, "name": "Read", "input": {}}
               for tid in tool_ids]
    return json.dumps({
        "type": "assistant",
        "sessionId": session_id,
        "requestId": request_id,
        "timestamp": "2026-06-04T02:21:44.108Z",
        "message": {"model": model, "role": "assistant",
                    "content": content, "usage": usage},
    })


def _user_line(session_id):
    """Eine user-Zeile (KEINE usage) — muss ignoriert werden."""
    return json.dumps({"type": "user", "sessionId": session_id,
                       "message": {"role": "user", "content": "hi"}})


def _write_session(projects_dir, project_hash, session_id, lines):
    d = projects_dir / project_hash
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{session_id}.jsonl").write_text("\n".join(lines) + "\n",
                                           encoding="utf-8")


# --- parse_session_files: Kern-Aggregation ---------------------------------

def test_parses_usage_per_request(tmp_path):
    """Pro requestId ein Token-Record mit den usage-Feldern."""
    proj = tmp_path / "projects"
    usage = {"input_tokens": 100, "output_tokens": 20,
             "cache_read_input_tokens": 5, "cache_creation_input_tokens": 50}
    _write_session(proj, "C--proj", "sess-1", [
        _assistant_line("sess-1", "req-1", "claude-opus-4-8", usage,
                        tool_ids=["toolu_AAA"]),
    ])
    by_req = icc.parse_session_files(proj)
    assert "req-1" in by_req
    rec = by_req["req-1"]
    assert rec["input_tokens"] == 100
    assert rec["output_tokens"] == 20
    assert rec["cache_read_tokens"] == 5
    assert rec["cache_creation_tokens"] == 50
    assert rec["session_id"] == "sess-1"
    assert rec["model"] == "claude-opus-4-8"
    assert "toolu_AAA" in rec["tool_use_ids"]


def test_user_lines_without_usage_ignored(tmp_path):
    """user-Zeilen ohne usage erzeugen keinen Record."""
    proj = tmp_path / "projects"
    _write_session(proj, "C--proj", "sess-1", [
        _user_line("sess-1"),
        _assistant_line("sess-1", "req-1", "claude-opus-4-8",
                        {"input_tokens": 10, "output_tokens": 2}),
    ])
    by_req = icc.parse_session_files(proj)
    assert list(by_req.keys()) == ["req-1"]


def test_multiple_tool_uses_share_one_turn(tmp_path):
    """Mehrere tool_use-Bloecke einer Message teilen sich EINE usage-Summe
    (kein Aufsplitten) und landen alle unter derselben requestId."""
    proj = tmp_path / "projects"
    _write_session(proj, "C--proj", "sess-1", [
        _assistant_line("sess-1", "req-1", "claude-opus-4-8",
                        {"input_tokens": 90, "output_tokens": 9},
                        tool_ids=["toolu_A", "toolu_B", "toolu_C"]),
    ])
    by_req = icc.parse_session_files(proj)
    rec = by_req["req-1"]
    assert rec["input_tokens"] == 90  # NICHT durch 3 geteilt
    assert set(rec["tool_use_ids"]) == {"toolu_A", "toolu_B", "toolu_C"}


def test_missing_projects_dir_returns_empty(tmp_path):
    """Kein CC-Verzeichnis -> leeres Ergebnis, kein Crash (graceful)."""
    assert icc.parse_session_files(tmp_path / "does-not-exist") == {}


def test_corrupt_lines_skipped(tmp_path):
    """Kaputte JSONL-Zeilen werden uebersprungen, valide weiter verarbeitet."""
    proj = tmp_path / "projects"
    d = proj / "C--proj"
    d.mkdir(parents=True)
    good = _assistant_line("s", "req-ok", "m", {"input_tokens": 5, "output_tokens": 1})
    (d / "sess.jsonl").write_text("not json {{{\n" + good + "\n", encoding="utf-8")
    by_req = icc.parse_session_files(proj)
    assert "req-ok" in by_req


# --- Kosten ----------------------------------------------------------------

def test_cost_computed_from_price_table(tmp_path):
    """cost_usd wird aus der Offline-Preistabelle pro Modell berechnet."""
    proj = tmp_path / "projects"
    _write_session(proj, "C--proj", "s", [
        _assistant_line("s", "req-1", "claude-opus-4-8",
                        {"input_tokens": 1_000_000, "output_tokens": 0}),
    ])
    by_req = icc.parse_session_files(proj, with_cost=True)
    # 1M input-Token zu einem positiven, plausiblen Preis.
    assert by_req["req-1"]["cost_usd"] > 0


def test_unknown_model_cost_zero_not_crash(tmp_path):
    """Unbekanntes Modell -> cost_usd 0.0, kein Crash."""
    proj = tmp_path / "projects"
    _write_session(proj, "C--proj", "s", [
        _assistant_line("s", "req-1", "some-future-model-xyz",
                        {"input_tokens": 1000, "output_tokens": 100}),
    ])
    by_req = icc.parse_session_files(proj, with_cost=True)
    assert by_req["req-1"]["cost_usd"] == 0.0


# --- Aggregation pro Session -----------------------------------------------

def test_aggregate_by_session(tmp_path):
    """tokens_by_session summiert ueber alle requestIds einer Session."""
    proj = tmp_path / "projects"
    _write_session(proj, "C--proj", "sess-1", [
        _assistant_line("sess-1", "req-1", "claude-opus-4-8",
                        {"input_tokens": 100, "output_tokens": 10}),
        _assistant_line("sess-1", "req-2", "claude-opus-4-8",
                        {"input_tokens": 200, "output_tokens": 20}),
    ])
    by_req = icc.parse_session_files(proj)
    by_sess = icc.aggregate_by_session(by_req)
    assert by_sess["sess-1"]["input_tokens"] == 300
    assert by_sess["sess-1"]["output_tokens"] == 30


# --- main / Ausgabe --------------------------------------------------------

def test_enrich_spans_joins_tokens_by_tool_use_id(tmp_path):
    """Spans werden ueber tool_use_id mit dem Turn-Record verknuepft; mehrere
    Calls desselben Turns erben dieselbe Turn-Summe (klar als Turn-Wert)."""
    import importlib.util
    LOAD = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
    s = importlib.util.spec_from_file_location("_load", LOAD)
    _load = importlib.util.module_from_spec(s)
    s.loader.exec_module(_load)

    by_req = {
        "req-1": {"input_tokens": 90, "output_tokens": 9,
                  "cache_read_tokens": 0, "cache_creation_tokens": 0,
                  "session_id": "sess-1", "model": "claude-opus-4-8",
                  "tool_use_ids": ["toolu_A", "toolu_B"], "cost_usd": 1.5},
    }
    spans = [
        {"tool_name": "Read", "tool_use_id": "toolu_A", "session_id": "sess-1"},
        {"tool_name": "Read", "tool_use_id": "toolu_B", "session_id": "sess-1"},
        {"tool_name": "Read", "tool_use_id": "toolu_X", "session_id": "sess-1"},
    ]
    out = _load.enrich_spans_with_tokens(spans, by_req)
    # Beide Calls von req-1 tragen die Turn-Summe ...
    assert out[0]["input_tokens"] == 90 and out[0]["turn_tokens"] is True
    assert out[1]["input_tokens"] == 90 and out[1]["turn_tokens"] is True
    assert out[0]["request_id"] == "req-1"
    # ... der unbekannte Call bleibt ohne Token (None, kein Crash).
    assert out[2]["input_tokens"] is None
    assert out[2].get("turn_tokens") is not True


def test_cost_breakdown_dedupes_turn_tokens(tmp_path):
    """Die Sigma-KPIs zaehlen jeden Turn (request_id) nur EINMAL, auch wenn
    mehrere Tool-Calls desselben Turns die Summe geerbt haben. Pro-Tool bleibt
    je Call gezaehlt (Turn-Wert)."""
    import importlib.util
    LOAD = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
    s = importlib.util.spec_from_file_location("_load", LOAD)
    _load = importlib.util.module_from_spec(s)
    s.loader.exec_module(_load)

    # Ein Turn (req-1) mit 3 Calls, jeder traegt die Turn-Summe (90 in / 1.5 USD).
    spans = [
        {"tool_name": "Read", "request_id": "req-1", "turn_tokens": True,
         "input_tokens": 90, "output_tokens": 9, "cache_read_tokens": 0,
         "cost_usd": 1.5, "agent": "claude-code"},
        {"tool_name": "Read", "request_id": "req-1", "turn_tokens": True,
         "input_tokens": 90, "output_tokens": 9, "cache_read_tokens": 0,
         "cost_usd": 1.5, "agent": "claude-code"},
        {"tool_name": "Grep", "request_id": "req-1", "turn_tokens": True,
         "input_tokens": 90, "output_tokens": 9, "cache_read_tokens": 0,
         "cost_usd": 1.5, "agent": "claude-code"},
    ]
    cb = _load.cost_breakdown(spans)
    # Sigma zaehlt den Turn EINMAL: 90 input, 1.5 USD — nicht 270 / 4.5.
    assert cb["total_input_tokens"] == 90
    assert cb["total_output_tokens"] == 9
    assert cb["total_cost_usd"] == 1.5
    # Pro-Tool bleibt je Call (Turn-Wert) — Read 2x1.5, Grep 1x1.5.
    assert cb["cost_by_tool"]["Read"] == 3.0
    assert cb["cost_by_tool"]["Grep"] == 1.5


def test_cost_breakdown_turn_token_carrier_not_first_span(tmp_path):
    """Regression (Verifier MAJOR): traegt der ERSTE Span eines Turns keine
    Token, aber ein spaeterer schon, muss die Turn-Summe trotzdem gezaehlt werden
    — nicht durch das frueh gesetzte 'seen' verschluckt."""
    import importlib.util
    LOAD = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
    s = importlib.util.spec_from_file_location("_load", LOAD)
    _load = importlib.util.module_from_spec(s)
    s.loader.exec_module(_load)
    spans = [
        {"tool_name": "Read", "request_id": "req-1"},  # KEINE Token, zuerst
        {"tool_name": "Grep", "request_id": "req-1",
         "input_tokens": 90, "output_tokens": 9, "cost_usd": 1.5},  # echte Token
    ]
    cb = _load.cost_breakdown(spans)
    assert cb["total_input_tokens"] == 90
    assert cb["total_output_tokens"] == 9
    assert cb["total_cost_usd"] == 1.5


def test_cost_breakdown_without_request_id_counts_per_span(tmp_path):
    """Spans ohne request_id (OTLP-Pfad / Altdaten) zaehlen wie bisher pro Span
    — die Dedup-Logik darf den bestehenden A-1-Pfad nicht veraendern."""
    import importlib.util
    LOAD = Path(__file__).resolve().parents[1] / "analysis" / "_load.py"
    s = importlib.util.spec_from_file_location("_load", LOAD)
    _load = importlib.util.module_from_spec(s)
    s.loader.exec_module(_load)
    spans = [
        {"tool_name": "Read", "input_tokens": 10, "cost_usd": 0.5},
        {"tool_name": "Read", "input_tokens": 20, "cost_usd": 0.7},
    ]
    cb = _load.cost_breakdown(spans)
    assert cb["total_input_tokens"] == 30
    assert cb["total_cost_usd"] == 1.2


def test_main_writes_output(tmp_path, monkeypatch):
    """main liest CLAUDE_PROJECTS_DIR und schreibt das Aggregat als JSON."""
    proj = tmp_path / "projects"
    _write_session(proj, "C--proj", "s", [
        _assistant_line("s", "req-1", "claude-opus-4-8",
                        {"input_tokens": 10, "output_tokens": 2}),
    ])
    out = tmp_path / "tokens_by_request.json"
    monkeypatch.setenv("CLAUDE_PROJECTS_DIR", str(proj))
    rc = icc.main([str(out)])
    assert rc == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "req-1" in data
