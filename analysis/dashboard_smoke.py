"""Dashboard smoke helpers used by tests and manual validation."""
import json
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from pathlib import Path


class _ScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self._in_script = False
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "script":
            self._in_script = True
            self._buf = []

    def handle_endtag(self, tag):
        if tag.lower() == "script" and self._in_script:
            self.scripts.append("".join(self._buf))
            self._in_script = False
            self._buf = []

    def handle_data(self, data):
        if self._in_script:
            self._buf.append(data)


def extract_script_blocks(html):
    parser = _ScriptParser()
    parser.feed(html)
    return parser.scripts


def node_check_html(html, node_cmd="node"):
    node = shutil.which(node_cmd)
    if not node:
        return {"status": "skipped", "reason": "node is not available", "checked": 0}

    scripts = extract_script_blocks(html)
    with tempfile.TemporaryDirectory() as tmp:
        for idx, script in enumerate(scripts):
            path = Path(tmp) / f"script-{idx}.js"
            path.write_text(script, encoding="utf-8")
            result = subprocess.run([node, "--check", str(path)],
                                    capture_output=True, text=True)
            if result.returncode != 0:
                return {
                    "status": "failed",
                    "checked": idx,
                    "script": idx,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                }
    return {"status": "passed", "checked": len(scripts)}


def _playwright_available(node):
    result = subprocess.run(
        [node, "-e", "try { require('playwright'); process.exit(0) } catch (e) { process.exit(3) }"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def browser_smoke(url, node_cmd="node", timeout=20):
    node = shutil.which(node_cmd)
    if not node:
        return {"status": "skipped", "reason": "node is not available"}
    if not _playwright_available(node):
        return {"status": "skipped", "reason": "playwright is not available"}

    script = r"""
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('console', msg => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', err => errors.push(String(err && err.message ? err.message : err)));
  await page.goto(process.argv[1], { waitUntil: 'networkidle' });
  const labels = await page.locator('.kpi .l').evaluateAll(nodes => nodes.map(n => n.textContent));
  await browser.close();
  const required = ['Total Events', 'Spans', 'Paired', 'Unpaired', 'Pairing-Rate'];
  const missing = required.filter(label => !labels.includes(label));
  if (errors.length || missing.length) {
    console.log(JSON.stringify({ status: 'failed', errors, missing, labels }));
    process.exit(2);
  }
  console.log(JSON.stringify({ status: 'passed', errors, labels }));
})().catch(async err => {
  console.log(JSON.stringify({ status: 'failed', errors: [String(err && err.message ? err.message : err)] }));
  process.exit(2);
});
"""
    result = subprocess.run([node, "-e", script, url], capture_output=True,
                            text=True, timeout=timeout)
    try:
        payload = json.loads(result.stdout.strip().splitlines()[-1])
    except Exception:
        payload = {"status": "failed", "stdout": result.stdout, "stderr": result.stderr}
    if result.returncode != 0 and payload.get("status") != "failed":
        payload["status"] = "failed"
    return payload
