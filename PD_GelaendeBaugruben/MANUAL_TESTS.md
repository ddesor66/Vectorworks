# Manuelle Abnahme in Vectorworks 2026

Diese Prüfungen benötigen die echte Vectorworks-Laufzeit und werden nicht durch Python-Doubles ersetzt. Pro Prüflauf sind Datum, Vectorworks-Build, Produktvariante, Datei und Ergebnis zu dokumentieren. Ein Punkt darf erst nach Sichtprüfung als bestanden markiert werden.

## A. Installation und Dialoge

- [ ] Einklickinstaller bei vollständig beendetem Vectorworks ausführen.
- [ ] `PD Kanal- und Leitungstool` öffnen; `Gelände und Baugruben` ist als vierte, eindeutig erkennbare Wahl vorhanden.
- [ ] Alle fünf Schritte öffnen; `Zurück`, `Abbrechen`, Vorschau und Fehlermeldungen funktionieren ohne leeren oder doppelten Dialog.
- [ ] Nach Abbruch sind weder neue Ebenen/Klassen/Objekte noch angefangene Tabellen vorhanden (bereits bewusst bestätigte Klassen ausgenommen).

## B. Quelldaten und natives Bestandsmodell

- [ ] Eine Testauswahl mit 3D-Loci, Vermessungspunkten, offener 3D-Bruchkante, geschlossener 3D-Höhenlinie, Linie, Bogen und Polylinie prüfen.
- [ ] Originalobjekte vor/nach dem Lauf über UUID, Lage, Klasse und Ebene vergleichen; keine Änderung oder Löschung.
- [ ] Gleiches XY/gleiches Z wird als Dublette ausgeschlossen; gleiches XY/abweichendes Z blockiert die Ausgabe.
- [ ] Ausschlussmuster für Dach/Baum/Vegetation sowie optionale Begrenzung prüfen.
- [ ] Bogen mit zwei deutlich verschiedenen Sehnentoleranzen prüfen; Punktanzahl und Laufzeit müssen plausibel reagieren.
- [ ] Erzeugte Quelle markieren und mit `Landschaft > Geländemodell > Geländemodell aus Ausgangsdaten` ein natives DGM erzeugen.
- [ ] Name, Klasse, Äquidistanz, Einheiten und Beschnitt nach dem Hinweisdialog einstellen; DGM aktualisieren und auf Fehler prüfen.

## C. Varianten

- [ ] Bestandsmodell registrieren; Metadaten nach erneutem Öffnen vorhanden.
- [ ] Zwei Sollkopien erzeugen, unabhängig verändern und verifizieren, dass Bestand und jeweils andere Sollkopie unverändert bleiben.
- [ ] Fremdes/Bestands-DGM kann über den Moduldialog nicht gelöscht werden; verwaltete Sollkopie kann nach Bestätigung gelöscht werden.

## D. Baugrube, Böschung und Modifikator

- [ ] Rechteckige Sohle in ebenem DGM mit bekannter Höhe und Böschung 1:1; Oberkante und Höhen visuell/numerisch kontrollieren.
- [ ] Sohlengefälle und Richtung prüfen; Höhen an allen vier Ecken kontrollieren.
- [ ] Böschungsneigung nacheinander als 1:n, Prozent und Grad eingeben und äquivalente Fälle vergleichen.
- [ ] Hindernis und zu kleine maximale Ausdehnung prüfen: roter Abschnitt, Hindernisname und erforderliche steilste Neigung erscheinen; kein stilles Ändern.
- [ ] Unter-/Oberkante sind getrennt benannt und liegen auf den dokumentierten Klassen.
- [ ] Schraffur: senkrechte Zuordnung, langer/kurzer Wechsel, Abstand und Verhältnis, keine Linien außerhalb der Ringfläche visuell kontrollieren.
- [ ] `Pad-Modifikator` aktivieren: prüfen, ob Vectorworks die Klasse/Modifikatoreigenschaft übernimmt. Modifikatorebene im DGM aktivieren, DGM manuell aktualisieren und das Ergebnis kontrollieren.
- [ ] Rückgängig macht den gesamten bestätigten Ausgabeschritt ohne Restobjekte rückgängig.

## E. Massen und Raster

- [ ] Zwei native parallele 10 × 10-m-Flächen mit 1,00 m Abstand: Auftrag 100,000 m³, Abtrag 0,000 m³.
- [ ] Umgekehrte Reihenfolge: Abtrag 100,000 m³, Auftrag 0,000 m³.
- [ ] Geneigte Vergleichsfläche mit analytisch bekannter Menge prüfen.
- [ ] Begrenzung teilweise außerhalb eines DGM: Status Teilüberdeckung, sichtbare `keine Daten`-Texte und keine Nullmengen für diese Felder.
- [ ] Raster um einen beliebigen Winkel drehen und manuellen Ursprung eingeben; Beschriftungen liegen an erwarteten Mittelpunkten.
- [ ] Beschriftungsgröße und Nachkommastellen prüfen.
- [ ] Grobes Raster erzeugt gegebenenfalls `Vorläufig`; nach Verkleinerung wird Konvergenz plausibel besser.
- [ ] Tabelle enthält Modellnamen, Datum, Vorzeichen, Methode, Status, Einheiten, Flächen, Volumen, Extrem-/Mittelhöhen und Konvergenz.
- [ ] Bestehende Tabelle aktualisieren; bei absichtlich gesperrter/fehlerhafter Tabelle bleibt ein Wiederherstellungsblatt erhalten.

## F. Abbruch, Umfang und Stabilität

- [ ] Berechnung mit großem Raster starten, Fortschrittsanzeige prüfen und abbrechen. Keine Rastergruppe/Tabelle aus diesem Lauf bleibt zurück.
- [ ] Raster oberhalb der Zellgrenze wird verständlich abgewiesen, ohne Vectorworks zu blockieren.
- [ ] Mehrfaches Öffnen und Schließen des Assistenten, Dokumentwechsel und Undo/Redo ohne Absturz testen.

## Abnahmeprotokoll

| Feld | Eintrag |
|---|---|
| Datum | |
| Prüfer | |
| Vectorworks-Version/Build | |
| Produktvariante | |
| Testdatei | |
| Ergebnis A–F | |
| Abweichungen/Screenshots | |

