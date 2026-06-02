"""PostToolUse/-Failure-Hook: zeichnet Erfolg/Fehler je Tool-Call auf.
Darf NIE blockieren — alles in try/except, immer exit 0.
Wiederverwendet redact/clip/_events_path aus track_tool_use.py."""
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
    """Erfolg primär aus hook_event_name, Fallback auf exit_code.
    Gegen reales Payload verifizieren (P006) — Schema ist undokumentiert."""
    event = str(raw.get("hook_event_name", "PostToolUse"))
    out = raw.get("tool_output") or {}
    err_obj = raw.get("tool_error") or {}
    exit_code = None
    if isinstance(out, dict):
        exit_code = out.get("exit_code")
    if exit_code is None and isinstance(err_obj, dict):
        exit_code = err_obj.get("exit_code")

    is_fail = event.endswith("Failure") or (isinstance(exit_code, int) and exit_code != 0)
    if not is_fail:
        return True, ""

    # Fehlertext sammeln: tool_error.stderr > tool_output.stderr > generisch
    raw_err = ""
    if isinstance(err_obj, dict):
        raw_err = str(err_obj.get("stderr") or err_obj.get("type") or "")
    if not raw_err and isinstance(out, dict):
        raw_err = str(out.get("stderr") or "")
    if not raw_err:
        raw_err = f"exit_code={exit_code}" if exit_code is not None else "error"
    return False, _pre.clip(_pre.redact(raw_err.splitlines()[0] if raw_err else raw_err))


def build_post_event(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    now = datetime.now(timezone.utc)
    now_local = now.astimezone()
    ok, error = _derive_ok_and_error(raw)
    return {
        "ts_utc": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
        "ts_local": now_local.strftime("%Y-%m-%d %H:%M:%S"),
        "agent": _pre.AGENT,
        "schema_v": _pre.SCHEMA_V,
        "phase": "post",
        "tool_name": raw.get("tool_name") or "unknown",
        "session_id": raw.get("session_id", ""),
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
