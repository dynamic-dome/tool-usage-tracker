import importlib.util
import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

SMOKE = Path(__file__).resolve().parents[1] / "analysis" / "dashboard_smoke.py"
SERVER = Path(__file__).resolve().parents[1] / "analysis" / "server.py"

_spec = importlib.util.spec_from_file_location("dashboard_smoke", SMOKE)
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

_server_spec = importlib.util.spec_from_file_location("server", SERVER)
server = importlib.util.module_from_spec(_server_spec)
_server_spec.loader.exec_module(server)


def test_extract_script_blocks_from_dashboard_html():
    scripts = smoke.extract_script_blocks(server.index_html())
    assert len(scripts) >= 2
    assert any("Chart" in script for script in scripts)
    assert any("function renderKPIs" in script for script in scripts)


def test_node_check_dashboard_scripts():
    if not shutil.which("node"):
        pytest.skip("node is not available")
    result = smoke.node_check_html(server.index_html())
    assert result["status"] == "passed"
    assert result["checked"] >= 2


def test_browser_smoke_skips_without_playwright():
    if not shutil.which("node"):
        pytest.skip("node is not available")
    availability = subprocess.run(
        ["node", "-e", "try { require('playwright'); process.exit(0) } catch (e) { process.exit(3) }"],
        capture_output=True,
        text=True,
    )
    if availability.returncode == 0:
        pytest.skip("playwright is installed; exercised by browser smoke implementation")
    result = smoke.browser_smoke("http://127.0.0.1:9")
    assert result["status"] == "skipped"
    assert "playwright" in result["reason"].lower()


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(url, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise AssertionError(f"server did not become ready: {url}")


def test_browser_smoke_loads_dashboard_when_playwright_available(tmp_path):
    if not shutil.which("node"):
        pytest.skip("node is not available")
    availability = subprocess.run(
        ["node", "-e", "try { require('playwright'); process.exit(0) } catch (e) { process.exit(3) }"],
        capture_output=True,
        text=True,
    )
    if availability.returncode != 0:
        pytest.skip("playwright is not available")

    data = tmp_path / "events.jsonl"
    rows = [
        {"phase": "pre", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.000Z",
         "project": "P", "cwd": "c", "summary": "x", "agent": "codex",
         "is_git_repo": True},
        {"phase": "post", "session_id": "s1", "tool_name": "Bash",
         "tool_use_id": "id1", "ts_utc": "2026-06-02T10:00:00.200Z",
         "ok": True, "error": "", "agent": "codex"},
    ]
    with data.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(SERVER), "--data", str(data), "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        url = f"http://127.0.0.1:{port}"
        _wait_for_server(url)
        result = smoke.browser_smoke(url)
        assert result["status"] == "passed"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
