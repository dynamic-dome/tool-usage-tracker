"""Ad-hoc-SQL-Layer ueber die Spans/Events via DuckDB (B-6) — OPTIONALES Add-on.

PHILOSOPHIE: Der Kern dieses Trackers bleibt stdlib-only (Hooks, Loader, Server,
Dashboard brauchen KEIN DuckDB). Dieser Layer ist ein reines Analyse-Add-on fuer
tiefe Ad-hoc-Auswertungen jenseits der fixen Dashboard-Panels — DuckDB liest
NDJSON/JSONL nativ (`read_json_auto`), inferiert das Schema und bringt Window-
Functions (p50/p95 etc.) mit. DuckDB ist eine einzelne Binary, keine Server-
Infrastruktur — passt zur zero-infra-Linie, bleibt aber strikt optional.

GRACEFUL FALLBACK: Ist `duckdb` nicht installiert, crasht NICHTS. `is_available()`
gibt False zurueck und `query()` wirft eine klar benannte `DuckDBUnavailable` mit
Installationshinweis. Der Import dieses Moduls funktioniert IMMER (lazy import).

Nutzung:
    python analysis/sql.py "SELECT tool_name, count(*) c FROM events
                            WHERE phase='pre' GROUP BY 1 ORDER BY c DESC"
    # optional: zweites Argument = Pfad zur JSONL (Default: data/events.jsonl)

Installation des Add-ons (NICHT Teil des Kerns):
    pip install duckdb
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / "data" / "events.jsonl"


class DuckDBUnavailable(RuntimeError):
    """duckdb ist nicht installiert. Der SQL-Layer ist ein optionales Add-on;
    der Kern bleibt stdlib-only. `pip install duckdb`, um ihn zu aktivieren."""


def _import_duckdb():
    try:
        import duckdb  # lazy: nur hier, damit der Modul-Import nie crasht
        return duckdb
    except Exception:  # ImportError o. seltene Lade-Fehler
        return None


def is_available():
    """True, wenn duckdb importierbar ist."""
    return _import_duckdb() is not None


def _require():
    d = _import_duckdb()
    if d is None:
        raise DuckDBUnavailable(
            "duckdb ist nicht installiert. Der SQL-Layer (B-6) ist ein OPTIONALES "
            "Analyse-Add-on — der Kern bleibt stdlib-only. Aktivieren mit: "
            "pip install duckdb"
        )
    return d


def _sql_str(s):
    """Escaped einen String als SQL-String-Literal (Single-Quotes verdoppeln).
    Noetig, weil DuckDB in CREATE VIEW keine prepared Parameter erlaubt — der
    Dateipfad muss inline. Schuetzt gegen ein eingeschleustes Quote im Pfad."""
    return "'" + str(s).replace("'", "''") + "'"


def _register_events(con, data_path):
    """Registriert die JSONL als View `events`. DuckDB inferiert das Schema
    selbst (union_by_name fuer heterogene Zeilen pre/post). Der Pfad wird inline
    eingebettet (DuckDB erlaubt keine prepared Parameter in CREATE VIEW), aber
    SQL-escaped."""
    lit = _sql_str(Path(data_path))
    # union_by_name=true: pre- und post-Events haben unterschiedliche Felder.
    # ignore_errors=true: einzelne kaputte Zeilen kippen die Analyse nicht.
    con.execute(
        "CREATE OR REPLACE VIEW events AS "
        f"SELECT * FROM read_json_auto({lit}, format='newline_delimited', "
        "union_by_name=true, ignore_errors=true)"
    )


def query(sql, data_path=None, params=None):
    """Fuehrt beliebiges SQL gegen die `events`-View aus und gibt eine Liste von
    Dicts zurueck (Spaltennamen -> Werte). Wirft DuckDBUnavailable, wenn duckdb
    fehlt. `data_path` default = data/events.jsonl."""
    d = _require()
    data_path = data_path or DEFAULT_DATA
    con = d.connect(":memory:")
    try:
        _register_events(con, data_path)
        cur = con.execute(sql, params or [])
        cols = [c[0] for c in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        con.close()


def query_spans(sql, data_path=None, params=None):
    """Wie query(), stellt aber zusaetzlich eine `spans`-View bereit, die pre/post
    per (session_id, tool_use_id bzw. tool_name) zu Spans verschmilzt — fuer
    SQL-Auswertungen auf Span-Ebene (Dauer, ok, Risk). Faellt auf die FIFO-naehe
    ueber ROW_NUMBER zurueck, wenn keine tool_use_id vorhanden ist."""
    d = _require()
    data_path = data_path or DEFAULT_DATA
    con = d.connect(":memory:")
    try:
        _register_events(con, data_path)
        # Span-View: paart pre/post je (session_id, tool_name) per Reihenfolge.
        con.execute(
            """
            CREATE OR REPLACE VIEW spans AS
            WITH pre AS (
              SELECT session_id, tool_name, agent, ts_utc AS ts_start,
                     try_cast(risk AS VARCHAR) AS risk,
                     row_number() OVER (PARTITION BY session_id, tool_name
                                        ORDER BY ts_utc) AS rn
              FROM events WHERE phase='pre'
            ),
            post AS (
              SELECT session_id, tool_name, ts_utc AS ts_end, ok,
                     row_number() OVER (PARTITION BY session_id, tool_name
                                        ORDER BY ts_utc) AS rn
              FROM events WHERE phase='post'
            )
            SELECT pre.session_id, pre.tool_name, pre.agent, pre.risk,
                   pre.ts_start, post.ts_end, post.ok,
                   (post.ok IS NOT NULL) AS paired
            FROM pre LEFT JOIN post
              ON pre.session_id=post.session_id
             AND pre.tool_name=post.tool_name
             AND pre.rn=post.rn
            """
        )
        cur = con.execute(sql, params or [])
        cols = [c[0] for c in cur.description] if cur.description else []
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        con.close()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("Usage: python analysis/sql.py \"<SQL>\" [data.jsonl]", file=sys.stderr)
        print("  Views: events (roh), spans (gepaart). Add-on: pip install duckdb",
              file=sys.stderr)
        return 2
    sql_text = argv[0]
    data_path = argv[1] if len(argv) > 1 else None
    try:
        rows = query(sql_text, data_path)
    except DuckDBUnavailable as e:
        print(str(e), file=sys.stderr)
        return 3
    print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
