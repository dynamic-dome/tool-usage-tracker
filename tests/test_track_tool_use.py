import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hook" / "track_tool_use.py"
_spec = importlib.util.spec_from_file_location("track_tool_use", HOOK)
track = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(track)


def test_sanitize_truncates_to_120_chars():
    long = "echo " + "a" * 500
    out = track.clip(long)
    assert len(out) <= 120
    assert out.endswith("…")


def test_clip_noop_for_short_string():
    # Unter dem Limit -> nur strip, kein Ellipsis, sonst unverändert
    assert track.clip("kurz") == "kurz"
    assert track.clip("  padded  ") == "padded"
    assert not track.clip("kurz").endswith("…")


def test_clip_exactly_at_limit_unchanged():
    s = "x" * track.MAX_LEN
    out = track.clip(s)
    assert out == s
    assert not out.endswith("…")


def test_clip_never_splits_a_multibyte_char():
    # Regression: clip() muss auf CODEPOINT-Ebene kappen, nie mitten in einem
    # Mehrbyte-Zeichen. (Das einst gemeldete "Write-Ho<mojibake>" war ein
    # PowerShell-cp1252-Konsolen-Rendering von U+2026, KEIN Datenfehler — diese
    # Invariante schreibt fest, dass die Daten byte-sauber bleiben.)
    long = "ä" * 500  # je 2 Bytes in UTF-8
    out = track.clip(long)
    assert len(out) <= track.MAX_LEN
    assert out.endswith("…")
    # Kern: das Resultat ist verlustfrei UTF-8-roundtrip-bar (kein halbes Zeichen)
    assert out == out.encode("utf-8").decode("utf-8")
    # und enthält nur vollständige ä plus das Ellipsis
    assert set(out[:-1]) == {"ä"}


def test_clip_result_is_valid_utf8_for_astral_chars():
    # Astral-Plane-Zeichen (Emoji, 4 Bytes in UTF-8 / Surrogate-Paar-Risiko):
    # auch hier darf clip nie ein Codepoint zerschneiden.
    long = "😀" * 200
    out = track.clip(long)
    assert len(out) <= track.MAX_LEN
    assert out.endswith("…")
    # roundtrip beweist: jedes verbleibende Zeichen ist ein vollständiges Codepoint
    assert out.encode("utf-8").decode("utf-8") == out
    assert set(out[:-1]) == {"😀"}


def test_redact_then_clip_composition():
    # Langer String mit Secret: Ergebnis bleibt ≤ MAX_LEN UND redacted
    raw = "api_key=" + "a" * 300
    out = track.clip(track.redact(raw))
    assert len(out) <= track.MAX_LEN
    assert "‹redacted›" in out
    assert "aaaa" not in out  # die 300 a's sind weg (redacted, nicht nur geclippt)


def test_clip_does_not_create_secret_leak_at_boundary():
    # Ein Secret darf nicht durch Clipping mittendrin abgeschnitten "überleben"
    raw = "x" * 110 + " sk-ABCDEF1234567890ghij"
    out = track.clip(track.redact(raw))
    assert "sk-ABCDEF" not in out


def test_redact_openai_key():
    assert "‹redacted›" in track.redact("key sk-ABCD1234567890efgh")
    assert "sk-ABCD" not in track.redact("key sk-ABCD1234567890efgh")


def test_redact_assignment_secrets():
    assert "‹redacted›" in track.redact("api_key=supersecretvalue123")
    assert "‹redacted›" in track.redact("PASSWORD: hunter2hunter2")
    assert "‹redacted›" in track.redact("Authorization: Bearer abc.def.ghi")


def test_redact_github_token():
    assert "‹redacted›" in track.redact("ghp_0123456789abcdefABCDEF0123")


def test_redact_modern_openai_proj_key():
    s = track.redact("OPENAI_API_KEY=sk-proj-AbCdEf1234567890XYZdef")
    assert "‹redacted›" in s
    assert "sk-proj-AbCdEf" not in s


def test_redact_quoted_secret_with_spaces():
    s = track.redact('password = "my secret pw value"')
    assert "‹redacted›" in s
    assert "secret pw value" not in s


def test_redact_aws_access_key():
    s = track.redact("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE rest")
    assert "‹redacted›" in s
    assert "AKIAIOSFODNN7EXAMPLE" not in s


def test_redact_jwt():
    jwt = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
           "eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4ifQ."
           "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
    s = track.redact("token " + jwt)
    assert "‹redacted›" in s
    assert "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c" not in s


def test_redact_pem_private_key_header():
    s = track.redact("data -----BEGIN RSA PRIVATE KEY----- MIIxyz")
    assert "‹redacted›" in s
    assert "BEGIN RSA PRIVATE KEY" not in s


def test_redact_slack_token():
    s = track.redact("SLACK=xoxb-1234567890-ABCDEFghijkl")
    assert "‹redacted›" in s
    assert "xoxb-1234567890-ABCDEFghijkl" not in s


def test_redact_github_gho_and_pat():
    s1 = track.redact("gho_0123456789abcdefABCDEF0123456789abcd")
    s2 = track.redact("github_pat_11ABCDE0123456789_abcdefGHIJKLmnopqrstuvwx")
    assert "‹redacted›" in s1
    assert "gho_0123456789" not in s1
    assert "‹redacted›" in s2
    assert "github_pat_11ABCDE" not in s2


def test_redact_does_not_eat_benign_text():
    # Kein Secret-Format -> bleibt unangetastet
    benign = "git commit -m 'fix the parser bug in module x'"
    assert track.redact(benign) == benign


def test_summary_bash_redacts_and_clips():
    s = track.build_summary("Bash", {"command": "curl -H 'api_key=secret123abc' x"})
    assert "‹redacted›" in s
    assert len(s) <= 120


def test_summary_edit_shortens_path():
    s = track.build_summary("Edit", {"file_path": r"C:\a\b\c\d\e\file.py"})
    assert s == r"c\d\e\file.py" or s.endswith("file.py")
    assert "C:\\a\\b" not in s


def test_summary_grep_uses_pattern():
    assert track.build_summary("Grep", {"pattern": "TODO"}) == "TODO"


def test_summary_mcp_tool_has_no_input():
    assert track.build_summary("mcp__wiki__wiki_read", {"path": "secret/x.md"}) == ""


def test_summary_unknown_tool_empty():
    assert track.build_summary("SomethingNew", {"weird": "data"}) == ""


def test_derive_project_basename():
    assert track.derive_project(r"C:\Users\domes\AI\Hooks-bau") == "Hooks-bau"


def test_derive_project_fallback_unknown():
    assert track.derive_project("") == "unknown"
    assert track.derive_project(None) == "unknown"


def test_events_path_uses_env_override(tmp_path, monkeypatch):
    target = tmp_path / "ev.jsonl"
    monkeypatch.setenv("TOOL_TRACKER_DATA", str(target))
    assert track._events_path() == target


def test_events_path_is_lazy(tmp_path, monkeypatch):
    monkeypatch.setenv("TOOL_TRACKER_DATA", str(tmp_path / "a.jsonl"))
    first = track._events_path()
    monkeypatch.setenv("TOOL_TRACKER_DATA", str(tmp_path / "b.jsonl"))
    second = track._events_path()
    assert first != second  # frisch gelesen, nicht eingefroren


def test_build_event_has_all_required_fields():
    raw = {"session_id": "s1", "cwd": r"C:\proj\Demo",
           "tool_name": "Bash", "tool_input": {"command": "ls"},
           "hook_event_name": "PreToolUse"}
    ev = track.build_event(raw)
    for k in ("ts_utc", "ts_local", "agent", "tool_name", "session_id",
              "tool_use_id", "cwd", "project", "is_git_repo", "hook_event",
              "summary", "schema_v", "phase"):
        assert k in ev
    assert ev["agent"] == "claude-code"
    assert ev["tool_name"] == "Bash"
    assert ev["project"] == "Demo"
    assert ev["summary"] == "ls"
    assert ev["schema_v"] == 2


def test_build_event_has_phase_pre_and_schema_2():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Bash", "tool_input": {"command": "ls"},
                            "hook_event_name": "PreToolUse"})
    assert ev["schema_v"] == 2
    assert ev["phase"] == "pre"


def test_build_event_missing_fields_no_crash():
    ev = track.build_event({})
    assert ev["tool_name"] == "unknown"
    assert ev["project"] == "unknown"
    assert ev["summary"] == ""


def _run_hook(stdin_text, env_extra):
    env = dict(os.environ, **env_extra)
    return subprocess.run([sys.executable, str(HOOK)], input=stdin_text,
                          capture_output=True, text=True, env=env)


def test_main_appends_valid_jsonl(tmp_path):
    target = tmp_path / "ev.jsonl"
    raw = json.dumps({"session_id": "s", "cwd": r"C:\x\Proj",
                      "tool_name": "Read", "tool_input": {"file_path": r"C:\x\Proj\a.py"},
                      "hook_event_name": "PreToolUse"})
    r = _run_hook(raw, {"TOOL_TRACKER_DATA": str(target)})
    assert r.returncode == 0
    line = target.read_text(encoding="utf-8").strip()
    ev = json.loads(line)
    assert ev["tool_name"] == "Read"
    assert ev["project"] == "Proj"


def test_main_broken_stdin_exits_zero(tmp_path):
    target = tmp_path / "ev.jsonl"
    r = _run_hook("this is not json {{{", {"TOOL_TRACKER_DATA": str(target)})
    assert r.returncode == 0  # nie blockieren


def test_main_appends_not_overwrites(tmp_path):
    target = tmp_path / "ev.jsonl"
    raw = json.dumps({"session_id": "s", "cwd": "x", "tool_name": "Glob",
                      "tool_input": {"pattern": "*.py"}, "hook_event_name": "PreToolUse"})
    _run_hook(raw, {"TOOL_TRACKER_DATA": str(target)})
    _run_hook(raw, {"TOOL_TRACKER_DATA": str(target)})
    assert len(target.read_text(encoding="utf-8").strip().splitlines()) == 2
