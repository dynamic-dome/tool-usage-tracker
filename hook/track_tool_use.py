"""PreToolUse-Hook: zeichnet jede Tool-Anwendung als JSONL-Zeile auf.
Darf NIE blockieren — alles in try/except, immer exit 0."""
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_LEN = 120

# Reihenfolge ist bedeutsam: spezifische Token-Formate ZUERST, damit das
# generische key=value-Pattern (weiter unten) ihnen nicht die rechte Seite
# zerstückelt und sie ins Leere greifen lässt.
_SECRET_PATTERNS = [
    # PEM-Private-Key-Blockheader (der eigentliche Schlüssel folgt im Klartext)
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[^-]*(?:-----END [A-Z ]*PRIVATE KEY-----)?"),
    # OpenAI (inkl. sk-proj-…)
    re.compile(r"sk-[A-Za-z0-9_-]{10,}"),
    # GitHub: ghp_/gho_/ghu_/ghs_/ghr_ Tokens + Fine-grained PATs
    re.compile(r"gh[opusr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    # AWS Access Key ID
    re.compile(r"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    # Slack Tokens
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    # Google API-Key (AIza + 35 Zeichen)
    re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    # Stripe Secret/Restricted Live-Keys
    re.compile(r"[sr]k_live_[0-9A-Za-z]{10,}"),
    # JWT (drei base64url-Segmente, vom typischen eyJ-Header eingeleitet)
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
    # Generische key=value-Zuweisungen (NACH den spezifischen Formaten)
    re.compile(r"(?i)(api[_-]?key|token|password|secret|auth)\s*[=:]\s*(\"[^\"]*\"|'[^']*'|\S+)"),
    re.compile(r"(?i)bearer\s+\S+"),
    # Generisches Hochentropie-Hex (>=32) NUR mit secret/key/token-Kontext davor —
    # ohne Keyword wuerde dies git-Commit-Hashes in Prosa zerstoeren (bewusst eng).
    re.compile(r"(?i)(secret|key|token|hash)\w*\s+[0-9a-f]{32,}"),
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
    if tool_name == "apply_patch":
        return clip(redact(str(tool_input.get("command", ""))))
    if tool_name == "WebFetch":
        return clip(str(tool_input.get("url", "")))
    if tool_name == "WebSearch":
        return clip(redact(str(tool_input.get("query", ""))))
    return ""


def _command_words(command: str):
    return re.findall(r"[A-Za-z0-9_.-]+", command.lower())


def classify_bash_command(command: str) -> dict:
    words = _command_words(command)
    if not words:
        return {"app": "local-cli", "operation": "", "intent": "unknown",
                "risk": "low", "mutating": False}

    # Wrapper wie `npx wrangler ...` auf das eigentliche Tool normalisieren.
    if words[:2] in (["npx", "wrangler"], ["pnpm", "wrangler"]):
        words = words[1:]

    first = words[0]
    second = words[1] if len(words) > 1 else ""
    third = words[2] if len(words) > 2 else ""

    if first == "git":
        read_ops = {"status", "diff", "show", "log", "fetch"}
        high_ops = {"push", "merge", "rebase"}
        write_ops = {"add", "commit", "pull", "checkout", "switch", "restore"}
        op = f"git {second}".strip()
        if second in read_ops:
            return {"app": "git", "operation": op, "intent": "read",
                    "risk": "low", "mutating": False}
        if second in high_ops:
            return {"app": "git", "operation": op, "intent": "write",
                    "risk": "high", "mutating": True}
        if second in write_ops:
            return {"app": "git", "operation": op, "intent": "write",
                    "risk": "medium", "mutating": True}
        return {"app": "git", "operation": op, "intent": "unknown",
                "risk": "medium", "mutating": False}

    if first == "gh":
        op = " ".join(w for w in ("gh", second, third) if w)
        mutating_ops = {"create", "comment", "review", "merge", "delete", "close", "reopen"}
        read_ops = {"view", "list", "status", "checks", "diff"}
        if second == "api" and any(w in {"post", "patch", "delete"} for w in words):
            return {"app": "github", "operation": "gh api", "intent": "write",
                    "risk": "high", "mutating": True}
        if third in mutating_ops:
            return {"app": "github", "operation": op, "intent": "write",
                    "risk": "high" if third == "merge" else "medium",
                    "mutating": True}
        if third in read_ops or second in {"pr", "issue", "run", "workflow", "repo"}:
            return {"app": "github", "operation": op, "intent": "read",
                    "risk": "low", "mutating": False}
        return {"app": "github", "operation": op, "intent": "unknown",
                "risk": "medium", "mutating": False}

    if first in {"wrangler", "wrangler.cmd"}:
        product = "pages" if second == "pages" else ""
        action = third if product else second
        op = " ".join(w for w in ("wrangler", product, action) if w)
        if action == "deploy":
            return {"app": "cloudflare", "operation": op, "intent": "deploy",
                    "risk": "high", "mutating": True}
        if action in {"secret", "d1", "kv", "r2"}:
            return {"app": "cloudflare", "operation": op, "intent": "write",
                    "risk": "high", "mutating": True}
        return {"app": "cloudflare", "operation": op, "intent": "read",
                "risk": "low", "mutating": False}

    if first == "notebooklm":
        op = f"notebooklm {second}".strip()
        mutating = second in {"create", "add", "delete", "use"}
        return {"app": "notebooklm", "operation": op,
                "intent": "write" if mutating else "read",
                "risk": "medium" if mutating else "low", "mutating": mutating}

    if first in {"pytest", "ruff", "mypy"} or (first in {"python", "py"} and "pytest" in words):
        return {"app": "python", "operation": "pytest" if "pytest" in words else first,
                "intent": "test", "risk": "low", "mutating": False}
    if first in {"python", "py", "uv", "pip"}:
        mutating = first in {"uv", "pip"} and second in {"add", "install", "sync"}
        return {"app": "python", "operation": f"{first} {second}".strip(),
                "intent": "write" if mutating else "unknown",
                "risk": "medium" if mutating else "low", "mutating": mutating}

    if first in {"node", "npm", "pnpm"}:
        test_cmd = second in {"test", "vitest"} or "test" in words
        mutating = second in {"install", "add", "remove", "update"}
        return {"app": "node", "operation": f"{first} {second}".strip(),
                "intent": "test" if test_cmd else ("write" if mutating else "unknown"),
                "risk": "medium" if mutating else "low", "mutating": mutating}

    return {"app": "local-cli", "operation": first, "intent": "unknown",
            "risk": "low", "mutating": False}


def classify_mcp_tool(tool_name: str) -> dict:
    """Klassifiziert MCP-Tool-Calls (`mcp__<server>__<tool>`) analog zur
    Bash-Klassifizierung. MCP-Calls kommen als eigene Tool-Namen (nicht als
    Bash), waren bisher ein blinder Fleck im Tracker (Dossier A-3).

    Read vs. mutating wird aus dem Tool-Namen-Suffix heuristisch bestimmt:
    bekannte write-/navigations-Verben -> mutating, bekannte read-Verben ->
    read, alles andere -> unknown/nicht-mutierend (fail-safe, keine
    Over-Klassifizierung)."""
    parts = tool_name.split("__", 2)
    server = parts[1] if len(parts) > 2 else ""
    tool = parts[2] if len(parts) > 2 else (parts[1] if len(parts) > 1 else "")
    op = f"{server}/{tool}" if server else tool

    name = tool.lower()
    WRITE = ("write", "append", "create", "add", "delete", "update", "edit",
             "log_", "navigate", "click", "type", "fill", "drag", "drop",
             "press", "upload", "save", "resize", "select")
    READ = ("read", "search", "find", "list", "get", "query", "status",
            "snapshot", "screenshot", "console", "messages", "view")

    if any(w in name for w in WRITE):
        intent, mutating, risk = "write", True, "medium"
    elif any(w in name for w in READ):
        intent, mutating, risk = "read", False, "low"
    else:
        intent, mutating, risk = "unknown", False, "low"

    return {"app": "mcp", "operation": op, "intent": intent,
            "risk": risk, "mutating": mutating}


def derive_project(cwd) -> str:
    # Plattformportabel: cwd kann ein Windows-Pfad (\) ODER ein POSIX-Pfad (/)
    # sein. Path(...).name zerlegt Backslashes nur AUF Windows korrekt, daher
    # hier explizit auf beiden Separatoren splitten — sonst liefert ein
    # Windows-Pfad auf Linux-CI/Codex faelschlich den vollen String.
    if not cwd:
        return "unknown"
    parts = [p for p in re.split(r"[\\/]+", str(cwd)) if p]
    return parts[-1] if parts else "unknown"


def _read_head_line(head: Path) -> str:
    """Erste Zeile von `.git/HEAD`, bounded gelesen (Hot-Path: nie die ganze
    Datei in den Speicher ziehen — HEAD ist real immer < 100 Bytes)."""
    raw = head.read_bytes()[:256]
    return raw.decode("utf-8", "replace").splitlines()[0].strip() if raw else ""


def _git_branch(cwd) -> str | None:
    """Aktueller Branch aus `.git/HEAD` — reiner Dateiread, KEIN subprocess
    (Hot-Path darf nie blockieren). `ref: refs/heads/<branch>` -> <branch>;
    Detached HEAD (direkter Hash) -> auf 7 Zeichen gekuerzt; nur `refs/heads/`
    gilt als Branch (refs/tags|remotes -> None). Worktree: `.git` ist eine
    DATEI mit `gitdir: <pfad>` -> dort liegt HEAD. Fail-safe: None bei jedem
    Fehler/fehlendem .git."""
    if not cwd:
        return None
    try:
        git = Path(str(cwd)) / ".git"
        if git.is_file():  # Worktree: .git -> "gitdir: <pfad>"-Pointer aufloesen
            pointer = _read_head_line(git)
            if pointer.startswith("gitdir:"):
                git = Path(pointer.split(":", 1)[1].strip())
            else:
                return None
        content = _read_head_line(git / "HEAD")
        if content.startswith("ref:"):
            ref = content[4:].strip()
            if ref.startswith("refs/heads/"):
                return ref[len("refs/heads/"):] or None
            return None  # refs/tags|remotes o.ae. ist kein Branch
        return content[:7] if content else None
    except Exception:
        return None


def _file_ext(file_path) -> str | None:
    """Datei-Endung (ohne Punkt, lowercase) aus einem file_path. None wenn
    keine Endung oder leer."""
    if not file_path:
        return None
    suffix = Path(str(file_path)).suffix
    return suffix[1:].lower() if suffix else None


def _events_path() -> Path:
    """LAZY: liest Env bei JEDEM Aufruf frisch, nie als Konstante einfrieren."""
    override = os.environ.get("TOOL_TRACKER_DATA")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "data" / "events.jsonl"


AGENT = "claude-code"
SCHEMA_V = 2


def derive_agent(raw: dict) -> str:
    # Codex hook payloads include a model field; Claude Code payloads currently do not.
    if raw.get("model"):
        return "codex"
    return AGENT


def build_event(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raw = {}
    cwd = raw.get("cwd", "")
    tool_name = raw.get("tool_name") or "unknown"
    tool_input = raw.get("tool_input") or {}
    now = datetime.now(timezone.utc)
    # ts_local = derselbe Zeitpunkt in System-Lokalzeit (naiv, ohne TZ-Marker,
    # bewusst menschenlesbar). Aus `now` abgeleitet, nicht zweiter Clock-Read.
    now_local = now.astimezone()
    is_git = False
    try:
        is_git = bool(cwd) and (Path(str(cwd)) / ".git").exists()
    except Exception:
        is_git = False
    ev = {
        "ts_utc": now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z",
        "ts_local": now_local.strftime("%Y-%m-%d %H:%M:%S"),
        "agent": derive_agent(raw),
        "tool_name": tool_name,
        "session_id": raw.get("session_id", ""),
        "tool_use_id": raw.get("tool_use_id", ""),
        "cwd": cwd,
        "project": derive_project(cwd),
        "is_git_repo": is_git,
        "hook_event": raw.get("hook_event_name", "PreToolUse"),
        "summary": build_summary(tool_name, tool_input),
        "phase": "pre",
        "schema_v": SCHEMA_V,
    }
    if is_git:
        branch = _git_branch(cwd)
        if branch:
            ev["git_branch"] = branch
    if tool_name in ("Read", "Write", "Edit", "NotebookEdit") and isinstance(tool_input, dict):
        ext = _file_ext(tool_input.get("file_path", ""))
        if ext:
            ev["file_ext"] = ext
    if tool_name == "Bash":
        ev.update(classify_bash_command(str(tool_input.get("command", ""))))
    elif tool_name.startswith("mcp__"):
        ev.update(classify_mcp_tool(tool_name))
    return ev


def main() -> int:
    try:
        data = sys.stdin.read()
        raw = json.loads(data) if data.strip() else {}
        ev = build_event(raw)
        path = _events_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    except Exception:
        pass  # Tracking darf NIE die Arbeit stören
    return 0


if __name__ == "__main__":
    sys.exit(main())
