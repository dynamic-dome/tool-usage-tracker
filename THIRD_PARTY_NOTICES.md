# Third-party notices

Diese Datei dokumentiert Drittbestandteile, entscheidet aber **nicht** über die
Lizenz des Gesamtprojekts.

## Im Repository gebündelt

### Chart.js 4.4.1

- Datei: `vendor/chart.umd.min.js`
- Projekt: <https://www.chartjs.org/>
- Upstream: <https://github.com/chartjs/Chart.js/tree/v4.4.1>
- Im Distributionsheader genannt: Copyright 2023 Chart.js Contributors,
  veröffentlicht unter der MIT License.
- Die gebündelte Distribution nennt außerdem `@kurkle/color` 0.3.2 mit MIT-Hinweis.

**Vorschlag vor einer formalen Veröffentlichung:** Die unveränderte MIT-Lizenz aus
dem verifizierten Chart.js-Tag `v4.4.1` zusammen mit diesem Hinweis ausliefern und
bei einem Vendor-Update Version, Header und Lizenz erneut abgleichen.

## Entwicklungsabhängigkeiten, nicht gebündelt

`package-lock.json` pinnt Playwright 1.60.0 (`Apache-2.0`) und die optionale
Abhängigkeit `fsevents` 2.3.2 (`MIT`) für lokale Dashboard-Tests. `node_modules/`
wird nicht eingecheckt.

## Zur Laufzeit referenzierte Remote-Ressourcen

### Google Fonts: JetBrains Mono und Outfit

- Einbindung im Dashboard: CSS-Import über
  <https://fonts.googleapis.com/css2?family=JetBrains+Mono&family=Outfit:wght@400;600&display=swap>
- Dienst/Upstream: <https://fonts.google.com/>
- Font-Projektseiten:
  <https://fonts.google.com/specimen/JetBrains+Mono> und
  <https://fonts.google.com/specimen/Outfit>
- Datenschutzinformationen des Dienstes:
  <https://developers.google.com/fonts/faq/privacy>

Die Fonts sind nicht im Repository gebündelt. Beim Öffnen des Dashboards ruft der
Browser das Stylesheet von `fonts.googleapis.com` und die Fontdateien
typischerweise von `fonts.gstatic.com` ab. Dabei werden Netzwerkmetadaten an Google
übermittelt; Tracker-Events und daraus berechnete Dashboard-Kennzahlen sind nicht
Bestandteil dieser Font-Requests.

Diese Dokumentation trifft keine Lizenzbehauptung für die beiden Fonts. Vor einer
Bündelung oder Weiterverteilung müssen die jeweils maßgeblichen Upstream-Dateien,
Versionen und Lizenztexte verifiziert und zusammen mit den erforderlichen Hinweisen
übernommen werden. Für eine rein lokale/offline Ausführung müssen die Remote-Fonts
entfernt oder durch lokal geprüfte Ressourcen ersetzt werden.

## Offene Owner-Entscheidung

Das Root-Projekt hat keine `LICENSE`-Datei. `package.json` nennt derzeit `ISC`,
doch die gewünschte Projektlizenz und die Konsistenz der Paketmetadaten müssen vom
Owner entschieden werden. Diese Datei fügt dem eigenen Code keine Lizenz hinzu.
