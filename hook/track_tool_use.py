"""PreToolUse-Hook: zeichnet jede Tool-Anwendung als JSONL-Zeile auf.
Darf NIE blockieren — alles in try/except, immer exit 0."""
import os
import re
from pathlib import Path

MAX_LEN = 120

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(api[_-]?key|token|password|secret|auth)\s*[=:]\s*(\"[^\"]*\"|'[^']*'|\S+)"),
    re.compile(r"(?i)bearer\s+\S+"),
]


def redact(text: str) -> str:
    for pat in _SECRET_PATTERNS:
        text = pat.sub("‹redacted›", text)
    return text


def clip(text: str) -> str:
    text = text.strip()
    if len(text) > MAX_LEN:
        return text[: MAX_LEN - 1] + "…"
    return text


def _short_path(p: str, keep: int = 3) -> str:
    p = p.replace("/", "\\")
    parts = [x for x in p.split("\\") if x]
    return "\\".join(parts[-keep:]) if parts else ""


def build_summary(tool_name: str, tool_input: dict) -> str:
    if not isinstance(tool_input, dict):
        return ""
    if tool_name.startswith("mcp__"):
        return ""
    if tool_name == "Bash":
        return clip(redact(str(tool_input.get("command", ""))))
    if tool_name in ("Read", "Write", "Edit", "NotebookEdit"):
        return clip(_short_path(str(tool_input.get("file_path", ""))))
    if tool_name in ("Grep", "Glob"):
        return clip(redact(str(tool_input.get("pattern", ""))))
    if tool_name in ("Task", "Agent"):
        return clip(redact(str(tool_input.get("description", ""))))
    if tool_name == "WebFetch":
        return clip(str(tool_input.get("url", "")))
    if tool_name == "WebSearch":
        return clip(redact(str(tool_input.get("query", ""))))
    return ""


def derive_project(cwd) -> str:
    if not cwd:
        return "unknown"
    name = Path(str(cwd)).name
    return name or "unknown"


def _events_path() -> Path:
    """LAZY: liest Env bei JEDEM Aufruf frisch, nie als Konstante einfrieren."""
    override = os.environ.get("TOOL_TRACKER_DATA")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "data" / "events.jsonl"
