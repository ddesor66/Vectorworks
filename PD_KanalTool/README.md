# PD Kanaltool 1.0.22

Das Kanaltool ist ein eigenständiges Vectorworks-2026-Menü und -Werkzeug. Es
verwendet ausschließlich eigene parametrische Objekte (`PD KAN Objekt`) und
greift nicht in das Datenmodell oder die Bedienoberfläche des Gefälletools ein.

## Einstieg und Zeichenrichtung

- Das eigenständige Menü `PD Kanal-Tool` und das grafische Werkzeug
  `PD Kanal Werkzeug` öffnen direkt das Kanalmodul. Der kombinierte
  Fachmodul-Aufruf bleibt zusätzlich verfügbar.
- Das kombinierte Hauptwerkzeug trägt dasselbe eindeutig blaue Kanalsymbol.
  Es ist nicht mehr mit dem grünen Gefällewerkzeug zu verwechseln. Gelände und
  Baugruben besitzt ein separates orangefarbenes Baugrubenprofil.
- Das Startmenü beginnt immer mit `Neue Kanalanlage durch Punkte zeichnen`.
  Direkt danach folgt `Vorhandene Linie, Polylinie oder Polygon in Kanalanlage
  umwandeln`; ohne passende Auswahl erscheint eine klare Auswahlhilfe.
- Die Erfassungsmaske ist in die nebeneinanderliegenden Bereiche `Rohr und
  Höhen`, `Schächte` und `Darstellung` gegliedert. Die wichtigsten
  Kanal-Unterbefehle stehen außerdem rechts in der Objekt-Info-Palette.
- Eine Haltung wird mit beliebig vielen Punkten gezeichnet. Doppelklick oder
  Enter schließt sie ab zwei Punkten ab. Die Zurücktaste entfernt nur den
  zuletzt gesetzten Punkt; Esc verwirft den noch nicht übernommenen Lauf.
- Bodenabläufe und Hausanschlüsse werden immer am freien Ende begonnen. Der
  letzte Doppelklickpunkt muss auf der vorhandenen Hauptleitung liegen. Erst
  dort wird die Hauptleitung geteilt und der Stutzen angelegt.
- Ein neuer Kanalstrang kann an einer markierten Haltung oder direkt an einem
  markierten Schacht beginnen. Die grafische Auswahl ist auch ohne
  Vorselektion möglich.

## Kanalhaltungen

In den Voreinstellungen wird zwischen Einlinien- und Doppelliniengrafik
gewählt. Die Einliniengrafik verwendet eine wählbare Linienart. Die
Doppelliniengrafik erhält zusätzlich eine schwarze gestrichelte Achslinie.
Kanalart, DN und Material bilden getrennte Klassen, zum Beispiel
`PD-KAN-RW-DN300-STB`; die 3D-Klasse endet mit `_3D`, die Achsklasse mit
`-Achse`. RW, SW und MW besitzen einstellbare Farben. Füllflächen werden mit
50 Prozent Deckkraft dargestellt, Umgrenzungslinien immer mit 100 Prozent.

Jede Haltung besitzt auf der Klasse `PD-KAN-Fließrichtung` einen skalierbaren
Pfeil, der stets von der höheren zur niedrigeren Sohle zeigt. Rohrsohlen,
Gefälle, DN, Material, Ausrundungsradius und ein- oder zweizeilige
Beschriftungen bleiben über das Kanalobjekt editierbar. Die 3D-Rohrachse liegt
einen halben DN über der Sohle.

## Stutzen und Anschlüsse

`Kanalstutzen herstellen` verlangt zuerst eine vorhandene Haltung, danach die
Anschlusslage. Die neue Anschlussleitung hat standardmäßig DN 150, ist
änderbar und kann sohl-, achs-, kämpfer- oder scheitelgleich angeschlossen
werden. Die daraus berechnete Anschlusshöhe wird beschriftet. Die Hauptleitung
wird transaktional in zwei Resthaltungen geteilt; die überlagerte alte Haltung
wird erst nach erfolgreichem Aufbau gelöscht.

Jeder neu erzeugte Kanalstutzen erhält automatisch eine Station. Nullpunkt ist
der Bezugspunkt des Schachts mit der tieferen Hauptleitungssohle; bei gleicher
Sohle gilt reproduzierbar der Endschacht der gespeicherten Fließ- bzw.
Objektrichtung. Gemessen wird entlang der zugehörigen Hauptleitungsachse bis
zum Stutzen. Stationswert und Nullpunktschacht stehen in der
Stutzenbeschriftung und werden nach Lage- oder Höhenänderungen neu berechnet.

Beim Hausanschluss ist die Höhe des freien Endpunkts zwingend anzugeben. Beim
Bodenablauf kann die Oberkante eingegeben oder von der Deckelhöhe des nächsten
Schachts übernommen werden. Ohne Bibliothekssymbol entsteht in 2D ein
30 × 30 cm großer Ablauf und in 3D ein 60 cm tiefer Kasten; beide Maße sind
änderbar. Bei einem reinen 2D-Symbol wird der Ersatzkasten zusätzlich erzeugt,
bei einem Hybrid-/3D-Symbol kann er abgeschaltet werden. Die Leitung beginnt an
der Unterkante des Ablaufs und fällt gleichmäßig zur Hauptleitung.

## Schächte und Sonderbauwerke

Runde Schächte besitzen Schachtdeckel, getrennte Zulauf-/Ablaufsohlen,
Zusatztext, freie Namen und die bekannte 2D/3D-Darstellung. Ein Schacht kann
durch Anklicken einer darüberliegenden geschlossenen Polygon- oder
Polylinienkontur in einen Sonderschacht umgewandelt werden. Anschlüsse enden
dann an der tatsächlichen Kontur; in der Beschriftung entfällt der runde
Schachtdurchmesser.

`Absturz vor Schacht` speichert und beschriftet die obere Sohle der
ankommenden Haltung sowie die Unterkante der Absturzleitung. Wird ein Schacht
in eine Haltung eingesetzt, wird die darunterliegende Haltung entfernt und in
zwei sauber am Schacht endende Resthaltungen aufgeteilt. Beschriftungen,
Fließrichtungspfeile und 3D-Rohre werden dabei gemeinsam neu aufgebaut.

Jede angeschlossene Haltung wird am Schacht als eigener Anschluss geführt.
Die stabile Anschlussidentität besteht aus Haltungs-ID und Endpunkt; DN,
Material, Zu-/Ablauf, Anschlusshöhe und Richtung werden unmittelbar aus den
aktuellen Haltungsdaten abgeleitet. Auch zwei Anschlüsse mit gleicher Höhe
bleiben getrennte Einträge. Bei unterschiedlichen Höhen stehen die
Anschlusshöhen zusätzlich direkt an den jeweiligen Anschlussrichtungen. Das
Schacht-Informationsfeld führt jeden Anschluss mit Kennung, Zu-/Ablauf, Höhe,
DN, Material und Winkel einzeln auf.

Bei runden Kanalschächten wird ausdrücklich zwischen `PP-Schacht` und
`Betonschacht` gewählt. Der eingegebene Durchmesser ist der lichte
Innendurchmesser. Für Betonschächte gilt standardmäßig eine 15 cm starke,
änderbare Wandung; das physische Außenmaß wird durchgängig als
`Ø außen = Ø innen + 2 × Wandstärke` berechnet. Dieses Außenmaß steuert die
2D-Außenkontur, den 3D-Schachtkörper, die Lage des Schachtdeckels, die
Rohranschlusstrimmung und die Beschriftungsabstände. Innen-, Wand- und
Außendurchmesser erscheinen außerdem im Schachttext und im Schachtblatt.
PP-Schächte behalten den eingegebenen Durchmesser ohne Betonwandzuschlag.
Sonderschächte verwenden weiterhin ausschließlich ihre gezeichnete Kontur.

## Schachtblätter

`Schachtblätter aus markierten Schächten erstellen` erzeugt für jeden
markierten Rund- oder Sonderschacht genau eine verwaltete DIN-A4-Layoutebene
im Querformat. Bauvorhaben, frei eingebbare Kanalart, Bemerkung und Firmenlogo
werden einmal für die gesamte Auswahl erfasst. Die Ausgabe enthält Draufsicht,
Winkeluhr, exzentrischen Deckel, schematischen Schnitt, KD, KS, Tiefe und ein
vollständiges Anschlussregister. Bis zu 24 Anschlüsse werden in drei
Tabellenblöcken ohne Folgeseite dargestellt; bei mehr Anschlüssen verhindert
eine verständliche Meldung einen unlesbaren Export.

Höhen können absolut oder relativ zur Schachtsohle ausgegeben werden. Für die
Winkeluhr stehen `12 Uhr = Plannord` mit einstellbarer Plannord-Drehung und die
BFR-Konvention `12 Uhr = tiefster Ablauf` zur Wahl; der verwendete Bezug wird
auf jeder Seite genannt. Die Vorschau, der gemeinsame Mehrseiten-PDF-Export
und der Vectorworks-Druckdialog verwenden dieselbe Vektorgeometrie. Bei jeder
erneuten Erstellung werden alle Werte aus den aktuellen Schacht- und
Haltungsobjekten gelesen; eine zweite Dateneingabe oder ein separater
Schachtblatt-Datenbestand existiert nicht.

## Bearbeitung und Prüfung

Ein Doppelklick auf Haltung, Schacht oder Beschriftung öffnet die
zusammenhängende Kanalkette. Die aktuelle Tabellenzeile hebt das zugehörige
Zeichnungsobjekt dynamisch hervor. Teilen, Vereinigen, Löschen, Verschieben,
Höhenfortschreibung und `Kanalnetz prüfen` arbeiten auf dem persistenten
Netzgraphen. Änderungen werden vor dem Löschen von Ausgangsobjekten validiert
und bleiben über Vectorworks `Rückgängig` wiederherstellbar.

Der Befehl zum DGM-Abgleich verändert ausschließlich die Deckelhöhen `KD` der
sichtbaren Rund- und Sonderschächte. Schachtsohlen, Rohrsohlen und 3D-Rohre
bleiben unverändert; bei einer ungültigen DGM-Abfrage wird die gesamte Änderung
zurückgerollt.

## Laufende Kanal- und Leitungsmengen

Die Haltungstabelle führt zusätzlich Start-/Endkoordinaten, Sohl- und Achshöhen,
Gefälle, Außendurchmesser, Wandstärke und den 3D-Hohlrohrstatus. In der 2D-Grafik
wird der reale Außendurchmesser verwendet; die 3D-Ausgabe kann als geschlossenes
Hohlrohr mit sichtbarer Innenkontur erzeugt werden.

`Massenermittlung, Erdmassen, Verbau und Excel` erzeugt das laufende
Arbeitsblatt `PD Kanal- und Leitungsmengen`. Es wertet Kanal- und
Versorgungsobjekte direkt aus und zählt keine Beschriftungen, Achsen oder
3D-Ersatzgeometrien doppelt. Enthalten sind 2D-/3D-Längen nach Art, DN und
Material, alle Schachthöhen und deren Summe, Zulaufklassen 0/1/2/3/4+,
DIN-EN-1610-Rohrgräben, rechteckige Schachtbaugruben und Verbauflächen.

Für die Grabenbreite wird der reale Rohraußendurchmesser verwendet. Ältere
Haltungen ohne bestätigten Außendurchmesser bleiben auswertbar, werden aber
im Arbeitsblatt und in Excel deutlich als vorläufige DN-Ersatzannahme
gekennzeichnet. Nach erfolgreicher Objektänderung wird ein bereits vorhandenes
Mengen-Arbeitsblatt automatisch neu aufgebaut. Der Excel-Export enthält
getrennte Blätter für Übersicht, Haltungen, Schächte, Leitungen, Erdmassen und
Prüfhinweise.
