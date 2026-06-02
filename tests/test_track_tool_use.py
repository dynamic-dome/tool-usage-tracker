import importlib.util
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
