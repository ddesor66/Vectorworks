# Kanal- und Leitungsmengen

Das Modul liest ausschließlich die persistenten Fachobjekte des Kanal- und
Leitungstools. Gezeichnete Hilfsgeometrie, Beschriftungen, Achsen und
3D-Darstellungen werden nicht nochmals gezählt.

Ein dokumentinterner Löschbeobachter aktualisiert bestehende Detail- und
Summenblätter auch nach dem normalen Vectorworks-Löschen. Gelöschte Haltungen,
Schächte, Rigolen und Leitungstrassen werden deshalb nicht weiter mitgeführt.

## Aufruf

Im Einstieg `PD Kanal- und Leitungstool` steht neben `Kanal` und `Leitung` die
Auswahl `Massenermittlung`. Derselbe Befehl ist in beiden Fachdialogen
enthalten. Vor der Ausgabe wird zwischen der kompakten `Summenliste` und
`Alle Einzelmassen mit Summenzeilen` gewählt. Die Einzelmassen erscheinen im
Arbeitsblatt `PD Kanal- und Leitungsmengen`; die Summenliste im Arbeitsblatt
`PD Kanal- und Leitungssummen`. Automatische Aktualisierungen bauen nur die im
Dokument bereits vorhandene Ausgabeart neu auf.

Die Oberbaustärke wird vollständig in Metern eingegeben, gespeichert und im
Bericht ausgegeben. Eine ältere, noch in Zentimetern gespeicherte Einstellung
wird beim ersten Laden automatisch und wertgleich in Meter umgerechnet.

## Enthaltene Mengen

- Kanal-Achslänge im Grundriss und wirkliche 3D-Rohrlänge, exakt gruppiert
  nach Kanalart, Nennweite und Material
- Kanalstutzen nach Kanalart, DN, Material und Anschlussart
- Länge jeder einzelnen Versorgungsleitung einer Paralleltrasse, gruppiert
  nach Leitungstyp, DN und Material
- jeder Schacht mit KD, KS, Höhe `KD − KS`, Bauart, Innen-/Außenabmessung,
  Zulauf- und Ablaufzahl
- Summen der Schächte mit 0, 1, 2, 3 und mindestens 4 Zuläufen
- Rohrgraben-Aushub und Verbaufläche je Haltung und Rechenabschnitt
- rechteckige Schachtbaugrube mit 50 cm Arbeitsraum und 15 cm Verbau je Seite
- Excel-Ausgabe mit eigenem Summenblatt, Kanalhaltungen, Schächten, Leitungen,
  Stutzen, Erdmassen sowie Annahmen und Prüfhinweisen
- vollständige Einzelzeilen mit einer Summenzeile je Tabelle und einem
  abschließenden Blatt `Einzelmassen Summen`

Ist eine vorhandene Zieldatei während des Exports in Excel geöffnet, bleibt
sie unverändert. Die neue Ausgabe wird stattdessen im selben Ordner unter
einem Namen mit dem Zusatz `_neu_<Zeitstempel>` gespeichert und dieser Pfad
im Abschlussdialog angezeigt.

Interne Objekt- und Netz-IDs werden nicht ausgegeben. Detailzeilen verwenden
stattdessen Haltungs-, Schacht- und Trassennamen. Objektänderungen werden als
ein zusammenhängender Vorgang behandelt, sodass die laufende Massenermittlung
auch bei Änderungen mehrerer zugehöriger Objekte nur einmal neu aufgebaut wird.

## Berechnungsgrundlagen

Für verbaute Rohrgräben wird die lichte Mindestbreite aus dem größeren Wert
von `OD + DN-Zuschlag` und der tiefenabhängigen Mindestbreite bestimmt. Die
15 cm Verbaudicke werden erst danach an beiden Seiten hinzugefügt. Bei linear
wechselnder Grabentiefe wird die Haltung an 1,00 m, 1,75 m und 4,00 m Tiefe
geteilt und abschnittsweise berechnet. Grundlage ist DIN EN 1610:2015-12 mit
Berichtigung 2016-09.

DN bestimmt nur die Tabellenstufe. Der wirkliche Rohraußendurchmesser `OD`
ist eine eigene Objekteigenschaft. Für ältere Kanalobjekte ohne gespeicherten
OD wird vorläufig DN als Ersatzwert verwendet und im Bericht als Warnung
gekennzeichnet. Beim nächsten Bearbeiten kann OD bestätigt oder korrigiert
werden.

Runde Schächte erhalten eine rechteckige Baugrube aus dem physischen
Außenmaß. Bei Betonschächten ist die Wandstärke im Außenmaß enthalten.
Sonderschächte verwenden die Außenabmessungen ihrer Kontur. Rohrgräben werden
an den äußeren Baugrubengrenzen gekürzt, damit Aushub nicht doppelt gezählt
wird. Die ausgewiesene Schachthöhe ist die hydraulische Höhe `KD − KS`, weil
das derzeitige Schachtobjekt keine gesonderte Baukörper-Unterkante speichert.
