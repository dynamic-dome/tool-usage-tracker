"""PostToolUse/-Failure-Hook: zeichnet Erfolg/Fehler je Tool-Call auf.
Result kommt im realen Feld `tool_response` (Fallback tool_output/tool_error
fürs separate PostToolUseFailure-Event). Darf NIE blockieren — alles in
try/except, immer exit 0. Wiederverwendet redact/clip/_events_path aus
track_tool_use.py."""
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Schwester-Modul laden (kanonische Quelle für redact/clip/_events_path)
_PRE = Path(__file__).resolve().parent / "track_tool_use.py"
_spec = importlib.util.spec_from_file_location("track_tool_use", _PRE)
_pre = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pre)


def _derive_ok_and_error(raw: dict):
    """Erfolg/Fehler aus dem REALEN PostToolUse-Schema ableiten, defensiv (P006).

    Ground-truth: das Result steckt in `tool_response` (dict). Ein separates
    PostToolUseFailure-Event KANN stattdessen `tool_output`/`tool_error` tragen
    — daher als Fallback behandeln, nicht darauf wetten. Das exakte Schema ist
    teils undokumentiert (uneinig, ob Bash exit_code mitliefert), deshalb mehrere
    Fehlersignale prüfen statt auf ein einziges Feld zu setzen."""
    event = str(raw.get("hook_event_name", "PostToolUse"))
    # Result-Dict: tool_response primär, dann tool_output, dann tool_error.
    result = raw.get("tool_response")
    if not isinstance(result, dict):
        result = raw.get("tool_output")
    if not isinstance(result, dict):
        result = raw.get("tool_error")
    if not isinstance(result, dict):
        result = {}

    exit_code = result.get("exit_code")
    is_error = bool(result.get("is_error"))
    interrupted = bool(result.get("interrupted"))

    is_fail = (
        event.endswith("Failure")
        or is_error
        or interrupted
        or (isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0)
    )
    if not is_fail:
        return True, ""

    # Fehlertext-Präzedenz: stderr > text(bei is_error) > generisch.
    raw_err = str(result.get("stderr") or "")
    if not raw_err and is_error:
        raw_err = str(result.get("text") or "")
    if not raw_err:
        if isinstance(exit_code, int) and not isinstance(exit_code, bool):
            raw_err = f"exit_code={exit_code}"
        elif interrupted:
            raw_err = "interrupted"
        else:
            raw_err = "error"
    first_line = raw_err.splitlines()[0] if raw_err else raw_err
    return False, _pre.clip(_pre.redact(first_line))


def build_post_event(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    now = datetime.now(timezone.utc)
    now_local = now.astimezone()
    ok, error = _derive_ok_and_error(raw)
    return {
        "ts_utc": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
        "ts_local": now_local.strftime("%Y-%m-%d %H:%M:%S"),
        "agent": _pre.derive_agent(raw),
        "schema_v": _pre.SCHEMA_V,
        "phase": "post",
        "tool_name": raw.get("tool_name") or "unknown",
        "session_id": raw.get("session_id", ""),
        "tool_use_id": raw.get("tool_use_id", ""),
        "ok": ok,
        "error": error,
    }


def main() -> int:
    try:
        data = sys.stdin.read()
        raw = json.loads(data) if data.strip() else {}
        ev = build_post_event(raw)
        path = _pre._events_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Tracking darf NIE die Arbeit stören
    return 0


if __name__ == "__main__":
    sys.exit(main())
