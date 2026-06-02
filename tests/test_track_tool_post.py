import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / "hook" / "track_tool_post.py"
_spec = importlib.util.spec_from_file_location("track_tool_post", HOOK)
post = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(post)


def test_build_post_event_success():
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUse",
           "tool_output": {"exit_code": 0, "stdout": "ok", "stderr": ""}}
    ev = post.build_post_event(raw)
    assert ev["phase"] == "post"
    assert ev["schema_v"] == 2
    assert ev["tool_name"] == "Bash"
    assert ev["session_id"] == "s1"
    assert ev["ok"] is True
    assert ev["error"] == ""


def test_build_post_event_failure_event_name():
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUseFailure",
           "tool_error": {"type": "exit_code", "exit_code": 127,
                          "stderr": "command not found: pytetst"}}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False
    assert "command not found" in ev["error"]


def test_build_post_event_failure_via_exit_code_fallback():
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUse",
           "tool_output": {"exit_code": 2, "stdout": "", "stderr": "boom"}}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False
    assert "boom" in ev["error"]


def test_build_post_event_redacts_error():
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUseFailure",
           "tool_error": {"stderr": "api_key=supersecret123 failed"}}
    ev = post.build_post_event(raw)
    assert "‹redacted›" in ev["error"]
    assert "supersecret123" not in ev["error"]


def test_build_post_event_clips_long_error():
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUseFailure",
           "tool_error": {"stderr": "x" * 500}}
    ev = post.build_post_event(raw)
    assert len(ev["error"]) <= 120


def test_build_post_event_missing_fields_no_crash():
    ev = post.build_post_event({})
    assert ev["tool_name"] == "unknown"
    assert ev["phase"] == "post"
    assert ev["ok"] is True


def _run_hook(stdin_text, env_extra):
    env = dict(os.environ, **env_extra)
    return subprocess.run([sys.executable, str(HOOK)], input=stdin_text,
                          capture_output=True, text=True, env=env)


def test_main_appends_post_line(tmp_path):
    target = tmp_path / "ev.jsonl"
    raw = json.dumps({"session_id": "s", "tool_name": "Read",
                      "hook_event_name": "PostToolUse",
                      "tool_output": {"exit_code": 0}})
    r = _run_hook(raw, {"TOOL_TRACKER_DATA": str(target)})
    assert r.returncode == 0
    ev = json.loads(target.read_text(encoding="utf-8").strip())
    assert ev["phase"] == "post"
    assert ev["ok"] is True


def test_main_broken_stdin_exits_zero(tmp_path):
    target = tmp_path / "ev.jsonl"
    r = _run_hook("not json {{{", {"TOOL_TRACKER_DATA": str(target)})
    assert r.returncode == 0
