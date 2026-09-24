# tool-usage-tracker

Lokaler, hook-basierter Tracker für Tool-Aufrufe aus Claude Code und Codex. Er
schreibt minimierte JSONL-Events, paart Start- und Abschlussereignisse und stellt
Auswertungen als CLI-Report, statisches Dashboard oder lokalen Live-Server bereit.

> **Privacy-Hinweis:** „Sanitisiert“ bedeutet hier Datenminimierung plus
> regelbasierte Redaktion. Es ist keine Garantie, dass alle Secrets oder
> personenbezogenen Daten erkannt werden. Prüfe Ereignisdateien vor jeder
> Weitergabe manuell.

## Schnellstart mit synthetischen Daten

Die mitgelieferte Demo enthält keine echten Nutzungs-, Projekt- oder Kostendaten:

```bash
python analysis/report.py --data examples/demo-events.ndjson
python analysis/server.py --data examples/demo-events.ndjson --port 8770
```

Danach lokal `http://127.0.0.1:8770` öffnen. Für Installation und Hook-Einrichtung
siehe [install.md](install.md), für alle Bedienpfade [HOW-TO-USE.md](HOW-TO-USE.md).

## Datenschutz-Datenvertrag

Die kanonische Implementierung liegt in `hook/track_tool_use.py` (`build_event`,
`build_summary`) und `hook/track_tool_post.py` (`build_post_event`). Die folgende
Tabelle beschreibt den aktuellen Codepfad, nicht nur die beabsichtigte Architektur.

### PreToolUse-Events

| Feld | Quelle/Inhalt | Datenschutzrelevanz |
|---|---|---|
| `ts_utc`, `ts_local` | Zeitpunkt des Tool-Aufrufs | Aktivitäts- und Arbeitszeitmuster |
| `agent` | Aus dem Hook-Payload abgeleitet | Zeigt Claude Code oder Codex |
| `tool_name`, `hook_event`, `phase`, `schema_v` | Tool-/Schema-Metadaten | Meist gering, kann Arbeitsabläufe erkennen lassen |
| `session_id`, `tool_use_id` | Unverändert aus dem Hook-Payload | Stabile Korrelationskennungen; nicht als anonym behandeln |
| `cwd` | **Vollständiges Arbeitsverzeichnis**, unverändert | Kann Benutzer-, Kunden-, Projekt- und Hostnamen enthalten |
| `project` | Letztes Segment von `cwd` | Kann interne Projektnamen enthalten |
| `is_git_repo`, `git_branch` | Lokaler Git-Status/Branch | Branch-Namen können Tickets, Kunden oder Vorhaben nennen |
| `summary` | Toolabhängiger, auf 120 Zeichen begrenzter Auszug | Kann trotz Regex-Redaktion sensible Inhalte enthalten |
| `file_ext` | Nur bei Dateiwerkzeugen | Dateityp, kein Dateiinhalt |
| `app`, `operation`, `intent`, `risk`, `mutating` | Heuristisch abgeleitete Klassifikation | Kann Arbeitsweise und verwendete Plattformen erkennen lassen |

`summary` wird abhängig vom Tool gebildet:

- `Bash`: Befehlstext, nach Secret-Regexen auf 120 Zeichen begrenzt.
- `Read`, `Write`, `Edit`, `NotebookEdit`: letzte drei Pfadsegmente.
- `Grep`, `Glob`: Suchmuster; `Task`, `Agent`: Beschreibung;
  `WebSearch`: Suchanfrage. Diese Werte werden redigiert und begrenzt.
- `WebFetch`: URL, begrenzt, derzeit **ohne** Secret-Redaktion. Query-Parameter
  dürfen daher keine Zugangsdaten enthalten.
- `apply_patch`: Wert aus `tool_input.command`, redigiert und begrenzt.
- `mcp__*` und unbekannte Tools: kein Input im `summary`; Name und abgeleitete
  MCP-Klassifikation können dennoch gespeichert werden.

### PostToolUse-Events

Gespeichert werden Zeitstempel, Agent, Toolname, `session_id`, `tool_use_id`,
`phase`, `schema_v`, der abgeleitete Erfolgswert `ok` und bei Fehlern die erste
Fehlerzeile als `error`. `error` wird durch dieselben Regexen verarbeitet und auf
120 Zeichen begrenzt. Vollständige Tool-Antworten werden nicht gespeichert.

### Was der Hook nicht absichtlich speichert

- keine vollständigen `tool_input`- oder `tool_response`-Objekte;
- keine gelesenen oder geschriebenen Dateiinhalte;
- keine MCP-Argumente;
- keine vollständigen Fehlerausgaben, sondern höchstens die erste begrenzte Zeile.

Diese Aussagen gelten nur für die beiden Hook-Skripte. Ein Befehl, Suchmuster,
eine URL, ein Pfad oder eine Fehlermeldung kann selbst vertrauliche Inhalte tragen.
Die Regexen decken bekannte Formate ab, aber keine beliebigen oder neuartigen
Secrets und keine allgemeine PII-Erkennung.

### Speicherung, Aufbewahrung und Löschung

- Standardpfad: `data/events.jsonl`; Override: `TOOL_TRACKER_DATA`.
- Append-only; ab 5 MiB wird standardmäßig in `events.N.jsonl` rotiert.
  `TOOL_TRACKER_MAX_BYTES` ändert die Schwelle oder deaktiviert Rotation mit `0`.
- Es gibt **keine automatische Löschung**. Rotation begrenzt die Aufbewahrungszeit
  nicht. Zum Löschen den Tracker stoppen und die betreffende lokale Ereignisdatei
  sowie ihre rotierten Teile entfernen.
- `data/` und `*.jsonl` sind per `.gitignore` ausgeschlossen. Das schützt nicht
  vor manueller Übergabe, Backups oder `git add -f`.
- Der Dashboard-Server bindet an `127.0.0.1`. Hook, Analyse und lokaler Server
  senden Ereignisdateien oder daraus erzeugte Eventinhalte nicht selbst an einen
  externen Dienst.
- **Das Dashboard ist dennoch nicht vollständig offline:** Beim Öffnen importiert
  der Browser Google Fonts von `fonts.googleapis.com` und lädt die zugehörigen
  Fontdateien typischerweise von `fonts.gstatic.com`. Dadurch erhält Google
  Netzwerkmetadaten wie IP-Adresse, Zeitpunkt und Browser-/Request-Header. Der
  aktuelle Font-Request enthält keine Tracker-Events oder Dashboard-Kennzahlen;
  diese werden lokal in die Seite eingebettet. Wer auch diese externen Requests
  vermeiden muss, sollte das Dashboard nicht öffnen, solange die Remote-Fonts im
  Code aktiviert sind, oder sie auf Netzwerkebene blockieren; dann greifen die
  CSS-Fallback-Schriften.

### Optionale Datenquellen und Exporte

- `analysis/ingest_ccusage.py` liest lokale Claude-Code-Sessiondateien und schreibt
  Request-/Session-Kennungen, Modell, Tool-Use-IDs, Tokenzahlen und rechnerische
  Kosten in eine lokale, ignorierte JSON-Datei.
- `analysis/ingest_otlp.py` übernimmt Session-IDs, Tokenzahlen und Kosten aus einer
  explizit bereitgestellten OTLP-Datei.
- `analysis/otlp_export.py` kann Daten nur bei ausdrücklichem Aufruf an einen
  konfigurierten Collector senden; dies ist kein automatischer Hook-Pfad.

## Tests

```bash
python -X utf8 -m pytest -q
```

Ein Teil der Tests enthält bewusst synthetische Zeichenfolgen, die wie bekannte
Credential-Formate aussehen, um die Redaktion zu belegen. Herkunft und sichere
Scanner-Behandlung stehen in [SECURITY.md](SECURITY.md).

## Drittanbieter und Lizenz

Das Dashboard bündelt Chart.js und referenziert Google Fonts als Remote-Ressource;
Entwicklungswerkzeuge stehen in `package-lock.json`. Details und konkrete
Lizenztexte und Herkunftsnachweise stehen in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Der eigene Code steht ab der Einführung der Root-[LICENSE](LICENSE) unter der
MIT-Lizenz. Bereits veröffentlichte Versionen, deren Paketmetadaten ISC auswiesen,
werden dadurch nicht rückwirkend unter MIT gestellt. Für gebündelte oder remote
referenzierte Drittbestandteile gelten die jeweils dokumentierten Bedingungen.
