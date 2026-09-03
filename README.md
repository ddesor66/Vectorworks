# Vectorworks PD Tools

Quellstand der Vectorworks-2026-Plug-ins aus der Gesamtinstallation **1.30.22**.

Der Branch `main` enthält darüber hinaus das weiterentwickelte Kanaltool 1.3.5,
das Leitungsmodul 1.0.7, das Gefälletool 1.18.2 und die Mengenausgabe 1.2.6. Die Änderungen sind in
`ST_COMPARISON.md` und `DEVELOPMENT_HISTORY.md` dokumentiert.

## Herkunft und Integritaet

Der Stand wurde ohne Ausfuehrung des Installers aus dessen eingebettetem ZIP-Payload extrahiert.

- Version: `1.30.22`
- Dateien im Original-Payload: `276`
- SHA-256 des Payload-ZIP: `e8a1da57f392438294cae38c8c65dcfe00825292ffec55b7faa02714766ad3b5`
- Einzeldateipruefsummen: `SOURCE_MANIFEST.sha256`

Der Installer selbst ist nicht Bestandteil des Repositories. Die installationsbezogene Datei
`PD_Netzwerklizenz.json` war nicht im Payload enthalten und wird durch `.gitignore` dauerhaft
von Git ausgeschlossen.

## Module

Enthalten sind unter anderem die Module fuer Gefaelle, Kanal, Leitungen, Gelaende und
Baugruben, Mengen- und Massenermittlung, Planpruefung, Rigolen, Treppen,
Winkelstuetzmauern und SketchUp-Export sowie die zugehoerigen Vectorworks-Einstiegspunkte.

## Entwicklungsstand

Der bisherige Entwicklungsverlauf ist in [DEVELOPMENT_HISTORY.md](DEVELOPMENT_HISTORY.md)
zusammengefasst. Der oeffentlich freigegebene Ausgangschat ist dort verlinkt.

## Entwicklung und Tests

Dieses Repository wurde aus einem Auslieferungspaket rekonstruiert. Das Paket enthaelt
keine vollstaendige Test-Suite und keine urspruengliche Git-Historie. Aenderungen sollten
daher in eigenen Branches erfolgen und vor der Installation sowohl automatisiert als auch
direkt in Vectorworks 2026 geprueft werden.

## Lizenz

Es wurde keine Open-Source-Lizenz mitgeliefert. Bis der Rechteinhaber eine Lizenzdatei
ergänzt, bleiben alle Rechte vorbehalten.
