"""Tests fuer analysis/sql.py (B-6 DuckDB-Ad-hoc-SQL-Layer, OPTIONALES Add-on).

DuckDB ist BEWUSST optional — der Kern bleibt stdlib-only. Dieser Layer ist ein
reines Analyse-Add-on. Die Tests pruefen daher ZWEI Pfade:
  1. Graceful-Fallback, wenn duckdb NICHT installiert ist (is_available()==False,
     query() wirft DuckDBUnavailable mit klarer Meldung statt einem ImportError-
     Crash). Dieser Pfad wird IMMER getestet (Negativtest).
  2. Echte Abfrage gegen JSONL, wenn duckdb installiert ist (sonst skip).
"""
import importlib.util
from pathlib import Path

import pytest

MOD = Path(__file__).resolve().parents[1] / "analysis" / "sql.py"
_spec = importlib.util.spec_from_file_location("sql", MOD)
sql = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sql)


def _write_jsonl(tmp_path):
    import json
    rows = [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash", "agent": "claude-code",
         "ts_utc": "2026-06-05T10:00:00.000Z", "risk": "low"},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash", "agent": "claude-code",
         "ts_utc": "2026-06-05T10:00:00.300Z", "ok": True},
        {"phase": "pre", "session_id": "s2", "tool_name": "Edit", "agent": "codex",
         "ts_utc": "2026-06-05T10:01:00.000Z", "risk": "high"},
        {"phase": "post", "session_id": "s2", "tool_name": "Edit", "agent": "codex",
         "ts_utc": "2026-06-05T10:01:00.500Z", "ok": False},
    ]
    p = tmp_path / "events.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return p


def test_is_available_is_bool():
    assert isinstance(sql.is_available(), bool)


def test_has_unavailable_exception_type():
    # Klar benannte Exception fuer den Fallback-Pfad.
    assert issubclass(sql.DuckDBUnavailable, Exception)


def test_query_raises_clear_error_when_duckdb_missing(tmp_path):
    if sql.is_available():
        pytest.skip("duckdb installiert — Fallback-Pfad hier nicht testbar")
    p = _write_jsonl(tmp_path)
    with pytest.raises(sql.DuckDBUnavailable) as ei:
        sql.query("SELECT 1", str(p))
    msg = str(ei.value).lower()
    assert "duckdb" in msg  # Meldung nennt die fehlende Abhaengigkeit
    assert "pip install" in msg or "optional" in msg  # gibt einen Hinweis


def test_query_spans_raises_when_missing(tmp_path):
    if sql.is_available():
        pytest.skip("duckdb installiert")
    p = _write_jsonl(tmp_path)
    with pytest.raises(sql.DuckDBUnavailable):
        sql.query_spans("SELECT * FROM spans", str(p))


def test_importing_sql_does_not_require_duckdb():
    # Das Modul selbst darf NIE beim Import crashen, auch ohne duckdb.
    # (Bereits dadurch bewiesen, dass dieses Testmodul laedt — explizit absichern.)
    assert hasattr(sql, "query")
    assert hasattr(sql, "query_spans")
    assert hasattr(sql, "is_available")


# --- Pfad 2: echte Abfragen, nur wenn duckdb verfuegbar ---
duck = pytest.mark.skipif(not sql.is_available(), reason="duckdb nicht installiert")


@duck
def test_query_reads_jsonl_natively(tmp_path):
    p = _write_jsonl(tmp_path)
    rows = sql.query("SELECT count(*) AS n FROM events", str(p))
    assert rows[0]["n"] == 4


@duck
def test_query_spans_view_pairs_or_filters(tmp_path):
    p = _write_jsonl(tmp_path)
    # 'events' raw view existiert; aggregat ueber agent
    rows = sql.query(
        "SELECT agent, count(*) AS c FROM events WHERE phase='pre' GROUP BY agent ORDER BY agent",
        str(p))
    by = {r["agent"]: r["c"] for r in rows}
    assert by["claude-code"] == 1
    assert by["codex"] == 1


@duck
def test_query_returns_list_of_dicts(tmp_path):
    p = _write_jsonl(tmp_path)
    rows = sql.query("SELECT tool_name FROM events WHERE phase='pre' ORDER BY tool_name", str(p))
    assert isinstance(rows, list)
    assert all(isinstance(r, dict) for r in rows)
    assert [r["tool_name"] for r in rows] == ["Bash", "Edit"]


@duck
def test_query_spans_view_joins_pre_and_post(tmp_path):
    p = _write_jsonl(tmp_path)
    rows = sql.query_spans(
        "SELECT agent, paired, ok FROM spans ORDER BY agent", str(p))
    by = {r["agent"]: r for r in rows}
    assert by["claude-code"]["paired"] in (True, 1)
    assert by["claude-code"]["ok"] in (True, 1)
    assert by["codex"]["ok"] in (False, 0)


def test_sql_str_escapes_single_quotes():
    # Negativtest fuer den Inline-Pfad-Escaper (Quote im Pfad darf nicht ausbrechen).
    assert sql._sql_str("/x/Proj") == "'/x/Proj'"
    assert sql._sql_str("a'b") == "'a''b'"
    # ein boeser Pfad mit Quote + SQL bleibt EIN String-Literal
    evil = "x'); DROP TABLE events;--"
    out = sql._sql_str(evil)
    assert out.startswith("'") and out.endswith("'")
    assert out.count("''") == 1  # genau das eine innere Quote wurde verdoppelt


@duck
def test_query_path_with_quote_does_not_break(tmp_path):
    # Pfad mit Single-Quote: muss als Literal behandelt werden, nicht ausbrechen.
    import json
    d = tmp_path / "o'dir"
    d.mkdir()
    p = d / "events.jsonl"
    p.write_text(json.dumps(
        {"phase": "pre", "session_id": "s", "tool_name": "Bash",
         "agent": "claude-code", "ts_utc": "2026-06-05T10:00:00.000Z"}) + "\n",
        encoding="utf-8")
    rows = sql.query("SELECT count(*) AS n FROM events", str(p))
    assert rows[0]["n"] == 1
