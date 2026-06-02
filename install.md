# Installation — tool-usage-tracker

Hook in `~/.claude/settings.json` (oder `settings.local.json`) unter `PreToolUse`
einhängen. **Achtung:** Hooks laden erst bei Claude-Code-Neustart.

```json
{
  "PreToolUse": [
    {
      "matcher": "*",
      "hooks": [
        {
          "type": "command",
          "command": "python \"C:\\Users\\domes\\AI\\Hooks-bau\\tool-usage-tracker\\hook\\track_tool_use.py\"",
          "timeout": 10
        }
      ]
    }
  ]
}
```

Danach Claude neu starten. Geladene Hooks prüfen mit `/hooks`.

## Auswertung

```bash
# CLI-Report (Terminal)
python analysis/report.py
python analysis/report.py --agent claude-code --project Hooks-bau --since 2026-06-01

# HTML-Dashboard (öffnet dashboard.html per Doppelklick, offline-fähig)
python analysis/dashboard.py
```

Beide nehmen `--data <pfad>` (Default: `data/events.jsonl`) und die Filter
`--agent`, `--project`, `--since YYYY-MM-DD`.

## Daten-Ort & Override

Events landen in `data/events.jsonl` (append-only, gitignored). Der Pfad lässt
sich per Env-Var `TOOL_TRACKER_DATA` überschreiben — z.B. für Tests oder einen
zentralen Sammel-Ort über mehrere Maschinen.

## Verhalten / Privatsphäre

- Der Hook **blockiert nie**: bei jedem Fehler (auch kaputtem stdin) beendet er
  still mit exit 0, schreibt dann ggf. kein Event. Tracking stört die Arbeit nie.
- `summary` ist sanitisiert: max. 120 Zeichen, Secrets (`sk-…`, `ghp_…`,
  `api_key=…`, `Bearer …`, quoted secrets) werden zu `‹redacted›`. **Kein**
  Datei-Inhalt wird je gespeichert, nur Pfade/Befehls-Prefixe.
- MCP-Tools (`mcp__*`) und unbekannte Tools speichern **keinen** Input.

## Test / Verifikation

```bash
# Volle Test-Suite
python -X utf8 -m pytest -q

# Echter End-to-End-Smoke gegen das Hook-Skript (sauberes JSON via subprocess,
# NICHT via echo — echo zerlegt Windows-Backslashes zu ungültigem JSON):
python -X utf8 -c "import json,subprocess,sys,os; raw=json.dumps({'cwd':r'C:\test\Demo','tool_name':'Bash','tool_input':{'command':'ls'},'hook_event_name':'PreToolUse'}); os.environ['TOOL_TRACKER_DATA']='tmp.jsonl'; print(subprocess.run([sys.executable,'hook/track_tool_use.py'],input=raw,text=True).returncode); print(open('tmp.jsonl').read())"
```
