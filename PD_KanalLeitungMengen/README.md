# Kanal- und Leitungsmengen

Das Modul liest ausschließlich die persistenten Fachobjekte des Kanal- und
Leitungstools. Gezeichnete Hilfsgeometrie, Beschriftungen, Achsen und
3D-Darstellungen werden nicht nochmals gezählt.

## Aufruf

Im Einstieg `PD Kanal- und Leitungstool` steht neben `Kanal` und `Leitung` die
Auswahl `Massenermittlung`. Derselbe Befehl ist in beiden Fachdialogen
enthalten. Beim ersten Aufruf entstehen das reine Summen-Arbeitsblatt
`PD Kanal- und Leitungssummen` und das Detail-Arbeitsblatt
`PD Kanal- und Leitungsmengen`. Existiert mindestens eines davon, werden beide
nach erfolgreichen Änderungen der verwalteten Kanal- und Leitungsobjekte sowie
beim Öffnen oder Export erneut aus den aktuellen Objektdaten aufgebaut.

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
  Erdmassen sowie Annahmen und Prüfhinweisen

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
