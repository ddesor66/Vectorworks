# Vergleich mit ST Sewer 0.973

Untersucht wurden die lokal installierten, frei lesbaren Ressourcen des kompilierten
ST-Sewer-Plug-ins. Fremder Quellcode wurde weder dekompiliert noch übernommen.

## Übernommene Konzepte

- getrennte Sohl- und Achshöhen in der Haltungstabelle
- Start- und Endkoordinaten je Haltung
- explizite Rohrwandstärke
- optionale hohle 3D-Rohre mit Innenkontur
- Außendurchmesser als maßgebende 2D-/3D-Grafikbreite
- klarer Status der 3D-Darstellung in der Auswertung

## Bereits besser oder umfangreicher im PD-Tool

- verwaltete Schachtblätter und PDF-Ausgabe
- DIN-EN-1610-Mengen, Erdmassen und Verbau
- Sonderschächte aus freien Polygonkonturen
- getrennte Kanal-, Leitungs-, Gelände- und Baugrubenmodule
- Kettenbearbeitung, Teilung, Zusammenführung und Objekt-Info-Befehle
- explizite OD-Prüfung und Warnungen bei Ersatzannahmen

## Nicht übernommen

Produktspezifische Namen, Symbole, Grafiken, Übersetzungen und interne
Verbindungsalgorithmen des ST-Plug-ins wurden nicht kopiert. Ovale und rechteckige
Schächte sind dort als Beta gekennzeichnet; im PD-Tool werden solche Bauwerke bereits
allgemeiner als freie Sonderschachtkontur abgebildet.
