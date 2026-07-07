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


def test_build_post_event_success_tool_response():
    raw = {"session_id": "s1", "tool_name": "Bash", "hook_event_name": "PostToolUse",
           "tool_response": {"is_error": False, "exit_code": 0, "stdout": "ok", "stderr": ""}}
    ev = post.build_post_event(raw)
    assert ev["phase"] == "post"
    assert ev["schema_v"] == 2
    assert ev["tool_name"] == "Bash"
    assert ev["session_id"] == "s1"
    assert ev["ok"] is True
    assert ev["error"] == ""


def test_build_post_event_failure_via_is_error():
    raw = {"session_id": "s1", "tool_name": "Read", "hook_event_name": "PostToolUse",
           "tool_response": {"is_error": True, "stderr": "file not found: x.py"}}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False
    assert "file not found" in ev["error"]


def test_build_post_event_failure_via_exit_code():
    raw = {"session_id": "s1", "tool_name": "Bash", "hook_event_name": "PostToolUse",
           "tool_response": {"exit_code": 2, "stderr": "boom"}}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False
    assert "boom" in ev["error"]


def test_build_post_event_failure_via_interrupted():
    raw = {"session_id": "s1", "tool_name": "Bash", "hook_event_name": "PostToolUse",
           "tool_response": {"interrupted": True, "stderr": "cancelled"}}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False


def test_build_post_event_failure_via_failure_event_fallback():
    # legacy/alt path: separate PostToolUseFailure event with tool_output/tool_error
    raw = {"session_id": "s1", "tool_name": "Bash", "hook_event_name": "PostToolUseFailure",
           "tool_error": {"exit_code": 127, "stderr": "command not found: pytetst"}}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False
    assert "command not found" in ev["error"]


def test_build_post_event_redacts_error():
    raw = {"session_id": "s1", "tool_name": "Bash", "hook_event_name": "PostToolUse",
           "tool_response": {"is_error": True, "stderr": "api_key=supersecret123 failed"}}
    ev = post.build_post_event(raw)
    assert "‹redacted›" in ev["error"]
    assert "supersecret123" not in ev["error"]


def test_build_post_event_clips_long_error():
    raw = {"session_id": "s1", "tool_name": "Bash", "hook_event_name": "PostToolUse",
           "tool_response": {"is_error": True, "stderr": "x" * 500}}
    ev = post.build_post_event(raw)
    assert len(ev["error"]) <= 120


def test_build_post_event_captures_tool_use_id_if_present():
    raw = {"session_id": "s1", "tool_name": "Bash", "hook_event_name": "PostToolUse",
           "tool_use_id": "toolu_abc", "tool_response": {"exit_code": 0}}
    ev = post.build_post_event(raw)
    assert ev.get("tool_use_id") == "toolu_abc"


def test_build_post_event_marks_codex_agent_from_model_field():
    raw = {"session_id": "s1", "tool_name": "Bash", "hook_event_name": "PostToolUse",
           "model": "gpt-5.5", "tool_response": {"exit_code": 0}}
    ev = post.build_post_event(raw)
    assert ev["agent"] == "codex"


def test_build_post_event_is_error_wins_over_exit_code_zero():
    raw = {"session_id": "s1", "tool_name": "Bash", "hook_event_name": "PostToolUse",
           "tool_response": {"is_error": True, "exit_code": 0, "stdout": "looks ok", "stderr": "but failed"}}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False


def test_build_post_event_missing_fields_no_crash():
    ev = post.build_post_event({})
    assert ev["tool_name"] == "unknown"
    assert ev["phase"] == "post"
    assert ev["ok"] is True  # no failure signal => success


def test_build_post_event_success_no_signals():
    # tool_response present, no error markers at all => success
    raw = {"session_id": "s1", "tool_name": "Read", "hook_event_name": "PostToolUse",
           "tool_response": {"type": "text", "text": "file contents"}}
    ev = post.build_post_event(raw)
    assert ev["ok"] is True


def _run_hook(stdin_text, env_extra):
    env = dict(os.environ, **env_extra)
    return subprocess.run([sys.executable, str(HOOK)], input=stdin_text,
                          capture_output=True, text=True, env=env)


def test_main_appends_post_line(tmp_path):
    target = tmp_path / "ev.jsonl"
    raw = json.dumps({"session_id": "s", "tool_name": "Read",
                      "hook_event_name": "PostToolUse",
                      "tool_response": {"exit_code": 0}})
    r = _run_hook(raw, {"TOOL_TRACKER_DATA": str(target)})
    assert r.returncode == 0
    ev = json.loads(target.read_text(encoding="utf-8").strip())
    assert ev["phase"] == "post"
    assert ev["ok"] is True


def test_main_broken_stdin_exits_zero(tmp_path):
    target = tmp_path / "ev.jsonl"
    r = _run_hook("not json {{{", {"TOOL_TRACKER_DATA": str(target)})
    assert r.returncode == 0


# ---- B3: Hook-Latenz-Messung (post-Hook loggt ueber _pre.log_latency) ----

def test_main_also_writes_latency_record(tmp_path):
    events = tmp_path / "ev.jsonl"
    latency = tmp_path / "lat.jsonl"
    raw = json.dumps({"session_id": "s", "tool_name": "Read",
                      "hook_event_name": "PostToolUse",
                      "tool_response": {"exit_code": 0}})
    r = _run_hook(raw, {"TOOL_TRACKER_DATA": str(events),
                        "TOOL_TRACKER_LATENCY": str(latency)})
    assert r.returncode == 0
    rec = json.loads(latency.read_text(encoding="utf-8").strip())
    assert rec["hook"] == "post"
    assert rec["tool_name"] == "Read"
    assert rec["duration_ms"] >= 0


def test_main_broken_stdin_still_logs_latency(tmp_path):
    latency = tmp_path / "lat.jsonl"
    r = _run_hook("not json {{{", {"TOOL_TRACKER_DATA": str(tmp_path / "ev.jsonl"),
                                    "TOOL_TRACKER_LATENCY": str(latency)})
    assert r.returncode == 0
    rec = json.loads(latency.read_text(encoding="utf-8").strip())
    assert rec["hook"] == "post"
    assert rec["tool_name"] == "unknown"


def test_build_post_event_failure_real_posttoolusefailure_shape():
    """Reales PostToolUseFailure-Payload (Doku + Live-Befund 2026-06-11):
    exit_code/stderr/is_error liegen TOP-LEVEL, tool_response ist ein STRING.
    Vorher fiel der Fehlertext auf generisches 'error' zurueck."""
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUseFailure",
           "tool_input": {"command": "exit 3"},
           "tool_response": "command failed",
           "exit_code": 3, "stderr": "boom", "is_error": True}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False
    assert "boom" in ev["error"]


def test_build_post_event_failure_top_level_exit_code_only():
    # Failure-Payload ohne stderr: String-Response ist der Fehlertext;
    # ohne jede Text-Quelle dient exit_code top-level als Fallback.
    raw = {"session_id": "s1", "tool_name": "Bash",
           "hook_event_name": "PostToolUseFailure",
           "tool_response": "failed", "exit_code": 7}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False
    assert "failed" in ev["error"]

    bare = {"session_id": "s1", "tool_name": "Bash",
            "hook_event_name": "PostToolUseFailure", "exit_code": 7}
    ev2 = post.build_post_event(bare)
    assert ev2["ok"] is False
    assert "exit_code=7" in ev2["error"]


def test_build_post_event_string_tool_response_with_top_level_is_error():
    # is_error top-level + String-Response: Fehlertext aus dem String ziehen
    raw = {"session_id": "s1", "tool_name": "Edit",
           "hook_event_name": "PostToolUseFailure",
           "tool_response": "File has not been read yet", "is_error": True}
    ev = post.build_post_event(raw)
    assert ev["ok"] is False
    assert "File has not been read" in ev["error"]
