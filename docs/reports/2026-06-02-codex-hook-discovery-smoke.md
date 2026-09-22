# Codex Hook Discovery Smoke - 2026-06-02

## Ziel

Pruefen, ob die projektlokale Codex-Hook-Konfiguration `.codex/hooks.json` bei einem
echten Codex-Toolcall ausgefuehrt wird.

## Vorbedingungen

- Projekt: `C:\Users\<user>\AI\Hooks-bau\tool-usage-tracker`
- Branch: `main`
- Codex CLI: `codex-cli 0.136.0`
- `.codex/hooks.json` ist JSON-valide.
- Die Hook-Skripte funktionieren isoliert:
  - Simulierte Codex-Payloads mit `model` schreiben `agent:"codex"`.
  - Pre/Post werden mit gleicher `tool_use_id` geschrieben.
  - Secrets werden im Summary redigiert.

## Durchgefuehrter Smoke

Der Smoke wurde mit einem temporaeren Eventpfad ausgefuehrt, damit keine Testdaten in
`data/events.jsonl` landen:

```powershell
$tmp = Join-Path $PWD 'analysis\tmp-codex-exec-hooks.jsonl'
Remove-Item -LiteralPath $tmp -ErrorAction SilentlyContinue
$env:TOOL_TRACKER_DATA = $tmp
codex exec --ephemeral --dangerously-bypass-hook-trust -C . --json `
  'Run exactly one harmless shell command that prints the current working directory, then answer with one short sentence.'
if (Test-Path -LiteralPath $tmp) {
  Get-Content -LiteralPath $tmp
} else {
  '---NO-HOOK-FILE---'
}
```

## Beobachtung

Codex fuehrte den Toolcall aus:

```text
Path
----
C:\Users\<user>\AI\Hooks-bau\tool-usage-tracker
```

Am Ende des Laufs stand:

```text
---NO-HOOK-FILE---
```

## Ergebnis

Der echte `codex exec`-Smoke bestaetigt **nicht**, dass die projektlokale
`.codex/hooks.json` in diesem Ausfuehrungsmodus feuert.

Der aktuelle Integrationsstand ist damit:

- Hook-Skripte: funktionsfaehig.
- Simulierte Codex-Payloads: funktionsfaehig.
- `codex exec` mit `--dangerously-bypass-hook-trust`: Toolcall laeuft, aber keine
  projektlokalen Hook-Events.
- Interaktiver `/hooks`-Trust-Smoke in einer echten Codex-Session bleibt offen.

## Konsequenz

Weitere Implementierung darf sich nicht darauf verlassen, dass Codex-Projekt-Hooks
bereits live aktiv sind. Claude-Code-Kompatibilitaet bleibt der stabile Anker. Codex
wird weiter unterstuetzt, aber die echte Hook-Discovery muss in einer interaktiven
Session nachverifiziert werden.

