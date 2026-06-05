import importlib.util
import json
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1] / "analysis" / "server.py"
TEMPLATE = Path(__file__).resolve().parents[1] / "analysis" / "dashboard_template.html"
_spec = importlib.util.spec_from_file_location("server", SERVER)
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)


def _write(tmp_path, rows):
    p = tmp_path / "ev.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    return p


def test_spans_payload_enriches_tokens_from_ccusage(tmp_path, monkeypatch):
    """Liegt ein tokens_by_request.json vor (ccusage-Ingest), reichert
    spans_payload die Spans ueber tool_use_id an und cost_breakdown traegt Daten."""
    p = _write(tmp_path, [
        {"phase": "pre", "tool_name": "Read", "session_id": "s",
         "tool_use_id": "toolu_A", "ts_utc": "2026-06-04T10:00:00.000Z"},
        {"phase": "post", "tool_name": "Read", "session_id": "s",
         "tool_use_id": "toolu_A", "ts_utc": "2026-06-04T10:00:01.000Z", "ok": True},
    ])
    tokens = tmp_path / "tokens_by_request.json"
    tokens.write_text(json.dumps({
        "req-1": {"input_tokens": 100, "output_tokens": 10,
                  "cache_read_tokens": 0, "cache_creation_tokens": 0,
                  "session_id": "s", "model": "claude-opus-4-8",
                  "tool_use_ids": ["toolu_A"], "cost_usd": 2.25},
    }), encoding="utf-8")
    monkeypatch.setenv("TOOL_TRACKER_TOKENS", str(tokens))
    payload = srv.spans_payload(str(p), {})
    assert payload["cost"]["has_cost_data"] is True
    span = next(s for s in payload["spans"] if s.get("paired"))
    assert span["input_tokens"] == 100
    assert span["cost_usd"] == 2.25
    assert span["turn_tokens"] is True


def test_spans_payload_exposes_drift(tmp_path):
    """spans_payload liefert einen drift-Block pro Session (D-3)."""
    p = _write(tmp_path, [
        {"phase": "pre", "tool_name": "Read", "session_id": "s",
         "tool_use_id": "t1", "ts_utc": "2026-06-04T10:00:00.000Z"},
        {"phase": "post", "tool_name": "Read", "session_id": "s",
         "tool_use_id": "t1", "ts_utc": "2026-06-04T10:00:01.000Z", "ok": True},
        {"phase": "pre", "tool_name": "Read", "session_id": "s",
         "tool_use_id": "t2", "ts_utc": "2026-06-04T10:00:02.000Z"},
        {"phase": "post", "tool_name": "Read", "session_id": "s",
         "tool_use_id": "t2", "ts_utc": "2026-06-04T10:00:03.000Z", "ok": True},
        {"phase": "pre", "tool_name": "Bash", "session_id": "s", "app": "git",
         "intent": "write", "tool_use_id": "t3", "ts_utc": "2026-06-04T10:00:04.000Z"},
        {"phase": "post", "tool_name": "Bash", "session_id": "s",
         "tool_use_id": "t3", "ts_utc": "2026-06-04T10:00:05.000Z", "ok": True},
    ])
    payload = srv.spans_payload(str(p), {})
    assert "drift" in payload
    assert payload["drift"]["s"]["dominant"] == "file/read"
    assert payload["drift"]["s"]["off_task_count"] == 1


def test_spans_payload_no_tokens_file_is_graceful(tmp_path, monkeypatch):
    """Ohne tokens_by_request.json bleibt alles wie bisher (kein Crash, keine
    Kostendaten)."""
    p = _write(tmp_path, [
        {"phase": "pre", "tool_name": "Read", "session_id": "s",
         "tool_use_id": "toolu_A", "ts_utc": "2026-06-04T10:00:00.000Z"},
        {"phase": "post", "tool_name": "Read", "session_id": "s",
         "tool_use_id": "toolu_A", "ts_utc": "2026-06-04T10:00:01.000Z", "ok": True},
    ])
    monkeypatch.setenv("TOOL_TRACKER_TOKENS", str(tmp_path / "nope.json"))
    payload = srv.spans_payload(str(p), {})
    assert payload["cost"]["has_cost_data"] is False


def test_spans_json_pairs_events(tmp_path):
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "P", "cwd": "c",
         "summary": "x", "agent": "claude-code"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.200Z", "ok": True, "error": "",
         "agent": "claude-code"},
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["count"] == 1
    assert payload["spans"][0]["duration_ms"] == 200
    assert "success_by_tool" in payload
    assert payload["success_by_tool"]["Bash"] == 1.0
    assert payload["pairing"] == {
        "spans": 1,
        "paired": 1,
        "unpaired": 0,
        "pairing_rate": 1.0,
        "by_method": {"fifo": 1},
        "orphans": {},
    }


def test_spans_payload_exposes_pairing_diagnostics(tmp_path):
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.000Z",
         "project": "P", "cwd": "c", "summary": "x", "agent": "codex"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.200Z",
         "ok": True, "error": "", "agent": "codex"},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z", "project": "P",
         "cwd": "c", "summary": "y", "agent": "codex"},
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["pairing"]["spans"] == 2
    assert payload["pairing"]["paired"] == 1
    assert payload["pairing"]["unpaired"] == 1
    assert payload["pairing"]["pairing_rate"] == 0.5
    assert payload["pairing"]["by_method"] == {"tool_use_id": 1, "orphan": 1}
    assert payload["pairing"]["orphans"] == {"pre_without_post": 1}


def test_spans_json_respects_exclude_self(tmp_path):
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "tool-usage-tracker",
         "cwd": "c", "summary": "x", "agent": "claude-code"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.200Z", "ok": True, "agent": "claude-code"},
    ])
    payload = srv.spans_payload(str(p), {"exclude_self": "1"})
    assert payload["count"] == 0  # self-Projekt rausgefiltert vor Paarung


def test_spans_payload_lists_distinct_agents_and_projects(tmp_path):
    # Für die Filter-Dropdowns: sortierte, eindeutige Werte aller Events.
    # (projects nur git-Repos -> Fixtures als is_git_repo=true markiert)
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "zeta", "cwd": "c",
         "summary": "x", "agent": "codex", "is_git_repo": True},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.200Z", "ok": True, "agent": "codex"},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z", "project": "alpha", "cwd": "c",
         "summary": "y", "agent": "claude-code", "is_git_repo": True},
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["agents"] == ["claude-code", "codex"]   # sortiert, unique
    assert payload["projects"] == ["alpha", "zeta"]        # sortiert, unique


def test_spans_payload_filter_options_ignore_active_filter(tmp_path):
    # Die Auswahl-Listen müssen ALLE Werte zeigen, auch wenn gerade gefiltert
    # wird — sonst könnte man nie auf einen anderen Wert umschalten.
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "zeta", "cwd": "c",
         "summary": "x", "agent": "codex", "is_git_repo": True},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z", "project": "alpha", "cwd": "c",
         "summary": "y", "agent": "claude-code", "is_git_repo": True},
    ])
    payload = srv.spans_payload(str(p), {"agent": "codex"})
    # gefilterte spans betreffen nur codex/zeta, aber die Optionen bleiben voll
    assert payload["agents"] == ["claude-code", "codex"]
    assert payload["projects"] == ["alpha", "zeta"]


def test_spans_payload_filter_options_skip_empty_values(tmp_path):
    # Events ohne agent/project dürfen keine leeren Optionen erzeugen.
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "cwd": "c", "summary": "x"},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z", "project": "alpha", "cwd": "c",
         "summary": "y", "agent": "claude-code", "is_git_repo": True},
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["agents"] == ["claude-code"]
    assert payload["projects"] == ["alpha"]


def test_projects_dropdown_only_git_repos(tmp_path):
    # projects-Dropdown listet NUR Projekte, die mind. 1 Event mit
    # is_git_repo=true haben — cwd-Ordner-Rauschen (.agent-memory, plans, …)
    # fliegt raus.
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "real-repo", "cwd": "c",
         "summary": "x", "agent": "claude-code", "is_git_repo": True},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z", "project": "plans", "cwd": "c",
         "summary": "y", "agent": "claude-code", "is_git_repo": False},
        {"phase": "pre", "session_id": "s3", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:02:00.000Z", "project": "noise", "cwd": "c",
         "summary": "z", "agent": "claude-code"},  # gar kein is_git_repo-Feld
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["projects"] == ["real-repo"]


def test_projects_dropdown_one_git_event_qualifies(tmp_path):
    # Ein Projekt mit gemischten Events (mind. 1 git=true) zählt als git-Repo —
    # robust gegen ein einzelnes Ausreißer-nongit-Event (real: 'wiki' 13/1).
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "ts_utc": "2026-06-02T10:00:00.000Z", "project": "mixed", "cwd": "c",
         "summary": "x", "agent": "claude-code", "is_git_repo": False},
        {"phase": "pre", "session_id": "s2", "tool_name": "Read",
         "ts_utc": "2026-06-02T10:01:00.000Z", "project": "mixed", "cwd": "c",
         "summary": "y", "agent": "claude-code", "is_git_repo": True},
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["projects"] == ["mixed"]


def test_spans_payload_exposes_classification_breakdown(tmp_path):
    # B-01: app/intent/risk/mutating werden vom Hook geschrieben und muessen
    # im Payload als Facette/Count fuer das Dashboard auswertbar sein.
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.000Z",
         "project": "P", "cwd": "c", "summary": "git push", "agent": "claude-code",
         "app": "git", "operation": "git push", "intent": "write",
         "risk": "high", "mutating": True},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.200Z",
         "ok": True, "error": "", "agent": "claude-code"},
        {"phase": "pre", "session_id": "s2", "tool_name": "Bash",
         "tool_use_id": "id2", "ts_utc": "2026-06-02T10:01:00.000Z",
         "project": "P", "cwd": "c", "summary": "pytest", "agent": "claude-code",
         "app": "python", "operation": "pytest", "intent": "test",
         "risk": "low", "mutating": False},
        {"phase": "post", "session_id": "s2", "tool_name": "Bash",
         "tool_use_id": "id2", "ts_utc": "2026-06-02T10:01:00.100Z",
         "ok": True, "error": "", "agent": "claude-code"},
    ])
    payload = srv.spans_payload(str(p), {})
    cls = payload["classification"]
    assert cls["risk"]["high"] == 1
    assert cls["risk"]["low"] == 1
    assert cls["mutating_count"] == 1
    assert cls["by_app"]["git"] == 1
    assert cls["by_app"]["python"] == 1
    assert cls["by_intent"]["write"] == 1
    assert cls["by_intent"]["test"] == 1
    # Spans selbst tragen die Felder (fuer Timeline-Tooltip/Filter)
    span = next(s for s in payload["spans"] if s.get("app") == "git")
    assert span["risk"] == "high"
    assert span["mutating"] is True


def test_spans_payload_exposes_cost_breakdown(tmp_path):
    # A-1: Token-/Kosten-Usage (aus dem Post-Event gemergt) muss im Payload als
    # Aggregat fuer KPIs + Kosten-Panel verfuegbar sein.
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.000Z",
         "project": "P", "cwd": "c", "summary": "x", "agent": "claude-code"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.200Z",
         "ok": True, "error": "", "agent": "claude-code",
         "input_tokens": 1000, "output_tokens": 200,
         "cache_read_tokens": 5000, "cost_usd": 0.01},
    ])
    payload = srv.spans_payload(str(p), {})
    cost = payload["cost"]
    assert cost["has_cost_data"] is True
    assert cost["total_input_tokens"] == 1000
    assert cost["total_output_tokens"] == 200
    assert round(cost["total_cost_usd"], 4) == 0.01
    assert round(cost["cost_by_tool"]["Bash"], 4) == 0.01
    # Span selbst traegt die Kostenfelder (fuer Timeline-Tooltip)
    span = payload["spans"][0]
    assert span["cost_usd"] == 0.01
    assert span["input_tokens"] == 1000


def test_spans_payload_cost_absent_flag_when_no_usage(tmp_path):
    # Normalfall (kein Ingest): keine Usage-Felder -> has_cost_data False,
    # Summen 0, Span-Kostenfelder None. Dashboard blendet Panel dann aus.
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.000Z",
         "project": "P", "cwd": "c", "summary": "x", "agent": "claude-code"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.200Z",
         "ok": True, "error": "", "agent": "claude-code"},
    ])
    payload = srv.spans_payload(str(p), {})
    assert payload["cost"]["has_cost_data"] is False
    assert payload["cost"]["total_cost_usd"] == 0.0
    assert payload["spans"][0]["cost_usd"] is None


def test_live_dashboard_template_has_risk_facet():
    # Das Template muss die neue Risk-Facette + Mutating-KPI rendern.
    html = srv.index_html()
    assert "Mutating" in html
    assert "Risk" in html or "risk" in html


def test_live_dashboard_template_has_cost_panel():
    # A-1: Template muss Kosten/Token sichtbar machen.
    html = srv.index_html()
    assert "Kosten" in html or "Cost" in html or "Token" in html
    assert "renderCost" in html


def test_spans_payload_exposes_comparison(tmp_path):
    # B-3: Run-Comparison-Aggregat (pro Agent und pro Session) im Payload.
    p = _write(tmp_path, [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "a1", "ts_utc": "2026-06-05T10:00:00.000Z",
         "project": "P", "cwd": "c", "summary": "x", "agent": "claude-code"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "a1", "ts_utc": "2026-06-05T10:00:00.300Z",
         "ok": True, "error": "", "agent": "claude-code"},
        {"phase": "pre", "session_id": "s2", "tool_name": "Edit",
         "tool_use_id": "b1", "ts_utc": "2026-06-05T10:01:00.000Z",
         "project": "P", "cwd": "c", "summary": "x", "agent": "codex"},
        {"phase": "post", "session_id": "s2", "tool_name": "Edit",
         "tool_use_id": "b1", "ts_utc": "2026-06-05T10:01:00.500Z",
         "ok": False, "error": "boom", "agent": "codex"},
    ])
    payload = srv.spans_payload(str(p), {})
    comp = payload["comparison"]
    assert set(comp) == {"by_agent", "by_session"}
    assert comp["by_agent"]["claude-code"]["tool_calls"] == 1
    assert comp["by_agent"]["codex"]["failures"] == 1
    assert comp["by_session"]["s1"]["total_duration_ms"] == 300


def test_live_dashboard_template_has_compare_tab():
    # B-3: Template muss den Compare-Tab + renderCompare enthalten.
    html = srv.index_html()
    assert "Compare" in html
    assert "renderCompare" in html
    assert "Run-Comparison" in html


def test_parse_query_flags():
    params = srv.parse_query("agent=codex&exclude_self=1&since=2026-06-01")
    assert params["agent"] == "codex"
    assert params["exclude_self"] == "1"
    assert params["since"] == "2026-06-01"


def test_live_dashboard_template_mentions_pairing_quality():
    html = srv.index_html()
    assert "Pairing-Rate" in html
    assert "Unpaired" in html


def test_live_dashboard_template_is_external_asset():
    assert TEMPLATE.exists()
    template = TEMPLATE.read_text(encoding="utf-8")
    assert "/*CHARTJS*/" in template
    assert "TOOL-USAGE COMMAND CENTER" in template
    server_source = SERVER.read_text(encoding="utf-8")
    assert "_PAGE_TEMPLATE" not in server_source


def test_spans_payload_error_does_not_crash_handler(tmp_path, monkeypatch):
    # spans_payload raises -> do_GET should send a 500 JSON, not propagate
    import io

    def boom(*a, **k):
        raise ValueError("corrupt data")
    monkeypatch.setattr(srv, "spans_payload", boom)

    Handler = srv.make_handler("dummy-path")
    # Minimal fake request plumbing to drive do_GET without a real socket
    captured = {}

    class FakeHandler(Handler):
        def __init__(self):
            self.path = "/api/spans"
            self.wfile = io.BytesIO()
        def send_response(self, code): captured["code"] = code
        def send_header(self, *a, **k): pass
        def end_headers(self): pass

    h = FakeHandler()
    h.do_GET()
    assert captured["code"] == 500
    body = h.wfile.getvalue().decode("utf-8")
    assert "error" in body


def test_favicon_request_returns_no_content():
    import io

    Handler = srv.make_handler("dummy-path")
    captured = {}

    class FakeHandler(Handler):
        def __init__(self):
            self.path = "/favicon.ico"
            self.wfile = io.BytesIO()
        def send_response(self, code): captured["code"] = code
        def send_header(self, *a, **k): pass
        def end_headers(self): pass

    h = FakeHandler()
    h.do_GET()
    assert captured["code"] == 204


def test_spans_payload_assigns_turn_index_and_threshold(tmp_path):
    # Zwei Spans derselben Session mit kleinem Gap -> beide turn_index 0,
    # turn_gap_ms im Payload vorhanden.
    import json as _json
    ev = tmp_path / "ev.jsonl"
    rows = [
        {"phase": "pre", "session_id": "s", "tool_use_id": "t1",
         "tool_name": "Read", "ts_utc": "2026-06-04T10:00:00.000Z",
         "cwd": "x", "project": "p"},
        {"phase": "post", "session_id": "s", "tool_use_id": "t1",
         "tool_name": "Read", "ts_utc": "2026-06-04T10:00:00.100Z", "ok": True},
    ]
    ev.write_text("\n".join(_json.dumps(r) for r in rows), encoding="utf-8")
    payload = srv.spans_payload(str(ev), {})
    assert "turn_gap_ms" in payload
    assert all("turn_index" in s for s in payload["spans"] if s.get("ts_start"))


def test_spans_payload_splits_turns_on_large_gap(tmp_path):
    # Zwei gepaarte Spans derselben Session, getrennt durch eine 60s-Pause
    # (> Fallback-Schwelle 30s) -> der Server muss zwei verschiedene turn_index
    # vergeben. Prueft den Split-Pfad (nicht nur den Fallback-Wert).
    import json as _json
    ev = tmp_path / "ev.jsonl"
    rows = [
        {"phase": "pre", "session_id": "s", "tool_use_id": "t1", "tool_name": "Read",
         "ts_utc": "2026-06-04T10:00:00.000Z", "cwd": "x", "project": "p"},
        {"phase": "post", "session_id": "s", "tool_use_id": "t1", "tool_name": "Read",
         "ts_utc": "2026-06-04T10:00:00.100Z", "ok": True},
        {"phase": "pre", "session_id": "s", "tool_use_id": "t2", "tool_name": "Read",
         "ts_utc": "2026-06-04T10:01:00.200Z", "cwd": "x", "project": "p"},
        {"phase": "post", "session_id": "s", "tool_use_id": "t2", "tool_name": "Read",
         "ts_utc": "2026-06-04T10:01:00.300Z", "ok": True},
    ]
    ev.write_text("\n".join(_json.dumps(r) for r in rows), encoding="utf-8")
    payload = srv.spans_payload(str(ev), {})
    dated = [s for s in payload["spans"] if s.get("ts_start")]
    turn_indices = sorted({s["turn_index"] for s in dated})
    assert turn_indices == [0, 1]  # echte Split in zwei Turns
    assert 5000 <= payload["turn_gap_ms"] <= 120000
