import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_redact_google_api_key():
    s = track.redact("GOOGLE_API_KEY=AIzaSyA1234567890abcdefGHIJKLMNOPQRSTUV rest")
    assert "‹redacted›" in s
    assert "AIzaSyA1234567890" not in s


def test_redact_stripe_live_secret_key():
    s = track.redact("STRIPE=sk_live_0123456789abcdefABCDEFghij rest")
    assert "‹redacted›" in s
    assert "sk_live_0123456789" not in s


def test_redact_stripe_restricted_key():
    s = track.redact("rk_live_0123456789abcdefABCDEFghij")
    assert "‹redacted›" in s
    assert "rk_live_0123456789" not in s


def test_redact_generic_long_hex_after_keyword():
    s = track.redact("secret a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6")
    assert "‹redacted›" in s
    assert "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6" not in s


def test_redact_stripe_test_key():
    # Stripe Test-Keys (sk_test_/rk_test_) sind ebenso geheim wie Live-Keys —
    # leak'en App-Zugriff auf Stripe-Testdaten. Ground-Truth-Luecke S-01.
    for raw in ("sk_test_0123456789abcdefABCDEFghij",
                "rk_test_0123456789abcdefABCDEFghij"):
        s = track.redact("STRIPE=" + raw + " rest")
        assert "‹redacted›" in s
        assert raw[:18] not in s


def test_redact_gitlab_pat():
    # GitLab Personal Access Tokens: glpat-<20+ Zeichen>. Nackt (ohne key=value-
    # Kontext) testen, damit das Token-FORMAT greift, nicht die =-Heuristik.
    raw = "glpat-abcdEFGH1234567890_xyz"
    s = track.redact("push failed using " + raw + " now")
    assert "‹redacted›" in s
    assert "glpat-abcdEFGH" not in s


def test_redact_google_oauth_access_token():
    # Google OAuth2 Access Tokens beginnen mit 'ya29.' gefolgt von Base64url.
    # Nackt testen (kein =), damit das Token-Format selbst greifen muss.
    raw = "ya29.A0AfH6SMBxyz1234567890abcdefghIJKLMNOP"
    s = track.redact("request with " + raw + " header")
    assert "‹redacted›" in s
    assert "ya29.A0AfH6" not in s


def test_redact_does_not_eat_filename_with_ya29_substring():
    # Negativtest: 'ya29' als Teilwort ohne den Punkt-Separator (kein Token-Format)
    # darf NICHT redaktiert werden — Pattern muss auf 'ya29.' verankert sein.
    benign = "open file analysis_ya29_results.csv now"
    assert track.redact(benign) == benign


def test_redact_does_not_eat_benign_hex_without_keyword():
    # Ein langer Hex-String OHNE secret/key/token-Kontext (z. B. ein Commit-Hash
    # in Prosa) darf NICHT redaktiert werden — sonst werden git-Logs unbrauchbar.
    s = track.redact("commit a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6 fixed it")
    assert "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6" in s


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


def test_summary_codex_apply_patch_uses_command_prefix():
    patch = "*** Begin Patch\n*** Update File: app.py\n@@\n-print('old')\n+print('new')"
    s = track.build_summary("apply_patch", {"command": patch})
    assert s.startswith("*** Begin Patch")
    assert len(s) <= track.MAX_LEN


def test_summary_skill_uses_skill_name():
    s = track.build_summary("Skill", {"skill": "frontend-design:frontend-design",
                                       "args": "irrelevant"})
    assert s == "frontend-design:frontend-design"


def test_summary_skill_missing_name_empty():
    assert track.build_summary("Skill", {"args": "x"}) == ""


def test_summary_unknown_tool_empty():
    assert track.build_summary("SomethingNew", {"weird": "data"}) == ""


def test_derive_project_basename():
    assert track.derive_project(r"C:\Users\domes\AI\Hooks-bau") == "Hooks-bau"


def test_derive_project_fallback_unknown():
    assert track.derive_project("") == "unknown"
    assert track.derive_project(None) == "unknown"


@pytest.mark.parametrize("cwd,expected", [
    (r"C:\Users\domes\AI\Hooks-bau", "Hooks-bau"),  # Windows
    ("/home/dome/projects/dual-bridge", "dual-bridge"),  # POSIX
    (r"C:/mixed\sep/Proj", "Proj"),                  # gemischte Separatoren
    ("C:\\trailing\\Proj\\", "Proj"),                # trailing separator
])
def test_derive_project_is_platform_portable(cwd, expected):
    # derive_project muss Windows- UND POSIX-Pfade unabhaengig vom Host-OS
    # korrekt auf den Basisordner reduzieren (sonst falsche project-Werte auf CI).
    assert track.derive_project(cwd) == expected


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


def test_build_event_marks_codex_agent_from_model_field():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Bash", "tool_input": {"command": "ls"},
                            "hook_event_name": "PreToolUse",
                            "model": "gpt-5.5"})
    assert ev["agent"] == "codex"


def test_build_event_classifies_git_read_command():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Bash",
                            "tool_input": {"command": "git status --short"},
                            "hook_event_name": "PreToolUse"})
    assert ev["app"] == "git"
    assert ev["operation"] == "git status"
    assert ev["intent"] == "read"
    assert ev["risk"] == "low"
    assert ev["mutating"] is False


def test_build_event_classifies_github_mutating_command():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Bash",
                            "tool_input": {"command": "gh pr merge 42 --squash"},
                            "hook_event_name": "PreToolUse"})
    assert ev["app"] == "github"
    assert ev["operation"] == "gh pr merge"
    assert ev["intent"] == "write"
    assert ev["risk"] == "high"
    assert ev["mutating"] is True


def test_build_event_classifies_wrangler_deploy():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Bash",
                            "tool_input": {"command": "npx wrangler deploy --env production"},
                            "hook_event_name": "PreToolUse"})
    assert ev["app"] == "cloudflare"
    assert ev["operation"] == "wrangler deploy"
    assert ev["intent"] == "deploy"
    assert ev["risk"] == "high"
    assert ev["mutating"] is True


def test_build_event_classifies_python_test_command():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Bash",
                            "tool_input": {"command": "python -m pytest -q"},
                            "hook_event_name": "PreToolUse"})
    assert ev["app"] == "python"
    assert ev["operation"] == "pytest"
    assert ev["intent"] == "test"
    assert ev["risk"] == "low"
    assert ev["mutating"] is False


def test_build_event_does_not_add_classification_to_plain_non_bash():
    # Read/Edit/Write u. a. Builtin-Tools (nicht Bash, nicht MCP) bekommen
    # weiterhin KEINE app/intent/risk/mutating-Klassifizierung.
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Read",
                            "tool_input": {"file_path": r"C:\proj\Demo\a.py"},
                            "hook_event_name": "PreToolUse"})
    assert "app" not in ev
    assert "operation" not in ev


def test_classify_mcp_write_tool():
    c = track.classify_mcp_tool("mcp__wiki__wiki_write")
    assert c["app"] == "mcp"
    assert c["operation"] == "wiki/wiki_write"
    assert c["intent"] == "write"
    assert c["mutating"] is True


def test_classify_mcp_read_tool():
    c = track.classify_mcp_tool("mcp__wiki__wiki_search")
    assert c["app"] == "mcp"
    assert c["operation"] == "wiki/wiki_search"
    assert c["intent"] == "read"
    assert c["mutating"] is False


def test_classify_mcp_playwright_navigate_is_mutating():
    c = track.classify_mcp_tool("mcp__playwright__browser_navigate")
    assert c["app"] == "mcp"
    assert c["operation"] == "playwright/browser_navigate"
    assert c["mutating"] is True


def test_classify_mcp_playwright_snapshot_is_read():
    c = track.classify_mcp_tool("mcp__playwright__browser_snapshot")
    assert c["intent"] == "read"
    assert c["mutating"] is False


def test_classify_mcp_unknown_tool_defaults_safe():
    c = track.classify_mcp_tool("mcp__somesrv__mystery_call")
    assert c["app"] == "mcp"
    assert c["operation"] == "somesrv/mystery_call"
    assert c["intent"] == "unknown"
    assert c["risk"] in ("low", "medium", "unknown")
    assert c["mutating"] is False


def test_build_event_classifies_mcp_tool():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "mcp__wiki__wiki_append_section",
                            "tool_input": {"path": "x.md"},
                            "hook_event_name": "PreToolUse"})
    assert ev["app"] == "mcp"
    assert ev["operation"] == "wiki/wiki_append_section"
    assert ev["mutating"] is True


def test_bash_classification_does_not_leak_secret_arguments():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Bash",
                            "tool_input": {"command": "curl -H api_key=supersecret123 https://example.com"},
                            "hook_event_name": "PreToolUse"})
    assert ev["app"] == "local-cli"
    assert ev["operation"] == "curl"
    assert "supersecret123" not in json.dumps(ev)


def test_build_event_keeps_claude_agent_without_codex_markers():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Bash", "tool_input": {"command": "ls"},
                            "hook_event_name": "PreToolUse"})
    assert ev["agent"] == "claude-code"


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


# ---- A-5: git_branch (aus .git/HEAD, kein subprocess) + file_ext ----

def test_git_branch_reads_ref_from_head(tmp_path):
    # Normaler Repo-Zustand: .git/HEAD enthaelt "ref: refs/heads/<branch>"
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    assert track._git_branch(str(tmp_path)) == "main"


def test_git_branch_handles_nested_branch_name(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/feature/a-5-git-branch\n", encoding="utf-8")
    assert track._git_branch(str(tmp_path)) == "feature/a-5-git-branch"


def test_git_branch_detached_head_returns_short_hash(tmp_path):
    # Detached HEAD: .git/HEAD enthaelt direkt einen 40-Zeichen-Hash (kein
    # "ref:"-Praefix) -> auf 7 Zeichen gekuerzt.
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0\n", encoding="utf-8")
    assert track._git_branch(str(tmp_path)) == "a1b2c3d"  # gekuerzt auf 7


def test_git_branch_non_heads_ref_returns_none(tmp_path):
    # MI-1: HEAD zeigt auf refs/tags/ oder refs/remotes/ (nicht refs/heads/).
    # Darf NICHT den rohen "ref: ..."-String als Branchname zurueckliefern.
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/tags/v1.0.0\n", encoding="utf-8")
    assert track._git_branch(str(tmp_path)) is None


def test_git_branch_truncates_pathological_huge_head(tmp_path):
    # M-1: ein riesiges .git/HEAD darf nicht komplett gelesen werden.
    # Realer Branchname steht in Zeile 1; der Rest (Muell) wird ignoriert,
    # und das Ergebnis bleibt klein.
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n" + "x" * 5_000_000, encoding="utf-8")
    out = track._git_branch(str(tmp_path))
    assert out == "main"


def test_git_branch_resolves_worktree_gitdir_pointer(tmp_path):
    # MI-2: in einem Worktree ist .git eine DATEI mit "gitdir: <pfad>".
    # Der Branch steht in <gitdir>/HEAD.
    real_gitdir = tmp_path / "realgit" / "worktrees" / "wt1"
    real_gitdir.mkdir(parents=True)
    (real_gitdir / "HEAD").write_text("ref: refs/heads/wt-branch\n", encoding="utf-8")
    work = tmp_path / "work"
    work.mkdir()
    (work / ".git").write_text(f"gitdir: {real_gitdir}\n", encoding="utf-8")
    assert track._git_branch(str(work)) == "wt-branch"


def test_git_branch_returns_none_without_git(tmp_path):
    # Kein .git -> None (fail-safe, kein Crash)
    assert track._git_branch(str(tmp_path)) is None


def test_git_branch_returns_none_on_empty_cwd():
    assert track._git_branch("") is None
    assert track._git_branch(None) is None


def test_file_ext_from_python_file():
    assert track._file_ext(r"C:\proj\Demo\module.py") == "py"


def test_file_ext_lowercased():
    assert track._file_ext("/home/x/README.MD") == "md"


def test_file_ext_none_without_extension():
    assert track._file_ext("/home/x/Makefile") is None
    assert track._file_ext("") is None


def test_build_event_adds_git_branch_when_repo(tmp_path):
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    ev = track.build_event({"session_id": "s", "cwd": str(tmp_path),
                            "tool_name": "Bash", "tool_input": {"command": "ls"},
                            "hook_event_name": "PreToolUse"})
    assert ev["is_git_repo"] is True
    assert ev["git_branch"] == "main"


def test_build_event_omits_git_branch_without_repo(tmp_path):
    ev = track.build_event({"session_id": "s", "cwd": str(tmp_path),
                            "tool_name": "Bash", "tool_input": {"command": "ls"},
                            "hook_event_name": "PreToolUse"})
    assert ev["is_git_repo"] is False
    assert "git_branch" not in ev


def test_build_event_adds_file_ext_for_file_tools():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Edit",
                            "tool_input": {"file_path": r"C:\proj\Demo\hook.py"},
                            "hook_event_name": "PreToolUse"})
    assert ev["file_ext"] == "py"


def test_build_event_omits_file_ext_for_non_file_tools():
    ev = track.build_event({"session_id": "s", "cwd": r"C:\proj\Demo",
                            "tool_name": "Bash", "tool_input": {"command": "ls"},
                            "hook_event_name": "PreToolUse"})
    assert "file_ext" not in ev


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
