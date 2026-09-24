# Third-party notices

Diese Datei dokumentiert Drittbestandteile, entscheidet aber **nicht** über die
Lizenz des Gesamtprojekts.

## Im Repository gebündelt

### Chart.js 4.4.1

- Datei: `vendor/chart.umd.min.js`
- Projekt: <https://www.chartjs.org/>
- Upstream: <https://github.com/chartjs/Chart.js/tree/v4.4.1>
- Lizenzquelle des gepinnten Tags:
  <https://github.com/chartjs/Chart.js/blob/v4.4.1/LICENSE.md>
- Im Distributionsheader genannt: Copyright 2023 Chart.js Contributors,
  veröffentlicht unter der MIT License.

Vollständiger Lizenztext aus dem verifizierten Tag `v4.4.1`:

```text
The MIT License (MIT)

Copyright (c) 2014-2022 Chart.js Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

### @kurkle/color 0.3.2

Die gebündelte Chart.js-Distribution enthält `@kurkle/color` 0.3.2 und nennt
diese Version samt Copyright- und MIT-Hinweis im Distributionsheader.

- Upstream: <https://github.com/kurkle/color/tree/v0.3.2>
- Lizenzquelle des gepinnten Tags:
  <https://github.com/kurkle/color/blob/v0.3.2/LICENSE.md>

Vollständiger Lizenztext aus dem verifizierten Tag `v0.3.2`:

```text
The MIT License (MIT)

Copyright (c) 2018-2021 Jukka Kurkela

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

Bei einem Vendor-Update müssen Version, Distributionsheader und beide
Upstream-Lizenztexte erneut abgeglichen werden.

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

## Lizenz des eigenen Codes

Die Root-[LICENSE](LICENSE) lizenziert den eigenen Code ab ihrer Einführung unter
MIT. Diese Drittanbieterhinweise übertragen die Copyrights von Chart.js,
`@kurkle/color` oder anderen Drittbestandteilen nicht auf den Projekteigentümer.
Bereits veröffentlichte Versionen, deren Paketmetadaten ISC auswiesen, werden durch
den Wechsel nicht rückwirkend unter MIT gestellt.
