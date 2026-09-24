# Security and scanner notes

## Sensitive runtime data

Runtime-Dateien unter `data/` können lokale Pfade, Projekt- und Branch-Namen,
Session-Kennungen, begrenzte Befehle, Suchbegriffe, URLs und Fehlertexte enthalten.
Sie gehören nicht in Issues, Logs, Screenshots oder Commits. Vor einer Weitergabe
müssen sie unabhängig geprüft und bei Bedarf durch synthetische Daten ersetzt werden.

Die Secret-Redaktion ist eine risikoreduzierende Regex-Heuristik, keine
Sicherheitsgrenze. Insbesondere beliebige Zugangsdaten, PII und Secrets in
URL-Query-Parametern können unerkannt bleiben.

## Bekannte synthetische Scanner-Fixtures

`tests/test_track_tool_use.py` enthält absichtlich nicht funktionsfähige Beispiele
bekannter Credential-Formate. Sie prüfen ausschließlich, dass `redact()` die Formate
erkennt. Ein älterer Implementierungsplan unter
`docs/superpowers/plans/2026-06-02-tool-usage-tracker.md` enthält ebenfalls ein
synthetisches Beispiel aus demselben Testentwurf.

Für Scanner-Ausnahmen gilt:

1. nur den konkreten Treffer/Fingerprint und den konkreten Pfad ausnehmen;
2. niemals das gesamte Repository, alle Tests oder ein vollständiges Tokenformat
   global erlauben;
3. nach jeder Fixture-Änderung erneut prüfen, dass ausschließlich bekannte
   Teststellen betroffen sind;
4. einen neuen Treffer außerhalb dieser Stellen als echten Befund behandeln, bis
   das Gegenteil belegt ist.

Es wird bewusst keine breite Scanner-Allowlist mitgeliefert. GitHub Secret Scanning
oder ein lokaler Scanner kann die bekannten Testzeilen einzeln als Test markieren;
diese Entscheidung gehört in eine separat geprüfte Security-/CI-Spur.

## Meldungen

Keine vermuteten Secrets oder personenbezogenen Daten in ein öffentliches Issue
kopieren. Für einen sensiblen Befund ist ein privater GitHub-Kontaktweg des Owners
zu verwenden; bis ein solcher ausdrücklich dokumentiert ist, genügt ein öffentlicher
Hinweis ohne Wert, Payload oder personenbezogene Details.
