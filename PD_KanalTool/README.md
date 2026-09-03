# PD Kanaltool 1.3.2

Das Kanaltool ist ein eigenständiges Vectorworks-2026-Menü und -Werkzeug. Es
verwendet ausschließlich eigene parametrische Objekte (`PD KAN Objekt`) und
greift nicht in das Datenmodell oder die Bedienoberfläche des Gefälletools ein.

Schachtblätter werden als echte DIN-A4-Layoutebenen im Querformat erzeugt. Die
physische Blatt- und Papiergröße wird unabhängig von Meter-, Zentimeter- oder
Millimeter-Dokumenteinheiten in Zoll an Vectorworks übergeben. Für eine
gemeinsame mehrseitige PDF aktiviert der Export jede vorbereitete Layoutebene,
bevor sie in die vom Benutzer gewählte Datei geschrieben wird.

Kanalobjekte können auch mit dem normalen Vectorworks-Löschbefehl entfernt
werden. Beim Löschen eines Schachts verschwinden nur die davon abhängigen
Haltungen; beim Löschen einer Haltung bleiben die Endschächte erhalten und
werden aktualisiert. Vorhandene Mengenblätter werden aus dem verbleibenden
Objektbestand neu aufgebaut.

Alle sichtbaren Deckel-, Sohl-, Anschluss- und sonstigen Höhenwerte werden in
Dialogen, Meldungen, Planbeschriftungen und Schachtblättern einheitlich mit
genau zwei Nachkommastellen ausgegeben. Die intern gespeicherten Werte und die
Berechnungen behalten ihre volle Genauigkeit.

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
- Das Aktionsmenü enthält nur eindeutige Erstellungs- und Globalbefehle. Nach
  Auswahl einer Haltung oder eines Schachts stehen Bearbeiten, neuer Strang,
  Schacht–Schacht-Verbindung, Schacht einsetzen, Stutzen, Sonderschacht,
  Absturz, Haltungen vereinigen, DGM-Abgleich, Schachtblatt und Löschen direkt
  rechts in der Objekt-Info-Palette. Wiederholte Dialoginitialisierungen fügen
  keine doppelten Aktionspunkte mehr hinzu.
- Eine Haltung wird mit beliebig vielen Punkten gezeichnet. Doppelklick oder
  Enter schließt sie ab zwei Punkten ab. Die Zurücktaste entfernt nur den
  zuletzt gesetzten Punkt; Esc verwirft den noch nicht übernommenen Lauf.
- Ändert eine Schacht- oder Rohrsohle die Fließrichtung einer Haltung, nennt
  das Tool vor der Übernahme jede betroffene Richtung. Erst nach einer
  Ja-Bestätigung werden Anfang/Ende, Zu-/Ablauf, positives Gefälle,
  Fließrichtungspfeil, Stationierung und abhängige Beschriftungen gemeinsam
  neu aufgebaut; bei Nein bleibt der bisherige Stand unverändert.
- Bodenabläufe und Hausanschlüsse werden immer am freien Ende begonnen. Der
  letzte Doppelklickpunkt muss auf der vorhandenen Hauptleitung liegen. Erst
  dort wird die Hauptleitung geteilt und der Stutzen angelegt.
- Ein neuer Kanalstrang kann an einer markierten Haltung oder direkt an einem
  markierten Schacht beginnen. Die grafische Auswahl ist auch ohne
  Vorselektion möglich.
- Der Abschluss eines neuen Kanalstrangs und die direkte Verbindung zweier
  Schächte laufen ohne reentrante Schreibzugriffe im parametrischen
  Objektcallback. Eine vorhandene Mengentabelle wird erst nach dem vollständig
  aufgebauten Kanalnetz genau einmal aktualisiert.
- Ein einzelner markierter Schacht öffnet seinen vollständigen Eigenschaftsdialog.
  Bei mehreren markierten runden Schächten oder Sonderschächten werden dieselben
  vollständigen Dialoge nacheinander geöffnet und erst anschließend gemeinsam
  übernommen. Damit bleiben Namen und Höhen individuell, während Durchmesser,
  Bauart/Material, Wandstärke, Schachtdeckel, Zusatztext und alle übrigen
  Schachtwerte gezielt je Schacht geändert werden können. Angeschlossene
  Haltungen und Beschriftungen werden danach automatisch neu aufgebaut.
- Zu- und Ablaufhöhen erhalten am Schacht jeweils ein eigenständig
  verschiebbares, an der Leitung ausgerichtetes Beschriftungsobjekt. Diese
  Außenbeschriftungen können in den Voreinstellungen gemeinsam ein- oder
  ausgeschaltet und durch Anwenden auf Auswahl, Kanalsystem oder Zeichnung auch
  bei vorhandenen Schächten aktualisiert werden. Im Schachttextfeld stehen
  unabhängig von der geometrischen Anschlussreihenfolge stets zuerst alle
  Zuläufe und danach alle Abläufe.

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

Jede Haltung erhält automatisch den Namen `H-<unterer Schachtname>`, zum
Beispiel `H-RW.003`. Maßgebend ist der in gespeicherter Fließrichtung tiefer
liegende Schacht; unsichtbare Zwischenknoten werden bis zum nächsten sichtbaren
Schacht durchlaufen. Nach einer bestätigten Fließrichtungsänderung oder einer
Umbenennung des unteren Schachts wird der Haltungsname automatisch erneuert.
Anzeige und Schriftgröße des Haltungsnamens sind in den Voreinstellungen unter
`Beschriftung` unabhängig voneinander einstellbar. Ist der Name eingeschaltet,
steht er immer als eigene erste Zeile oberhalb der technischen Angaben. Die
Auswahl `Technische Angaben in einer/ zwei Zeilen` betrifft nur Gefälle, Länge,
DN und Material; ohne Haltungsnamen entfällt die zusätzliche Namenszeile.

Die Voreinstellungen sind in die kompakten Register `Kataloge und Farben`,
`Schachtfarben`, `Darstellung`, `Beschriftung` sowie
`Schächte und Schachtdeckel` gegliedert. Für RW, SW und MW können unabhängig
von den Rohrfarben jeweils Schacht-Linienfarbe, Schacht-Füllfarbe und
Fülltransparenz von 0 bis 100 % festgelegt werden. Die Kontur bleibt dabei
immer vollständig deckend. In der Einzelbearbeitung eines Schachts können
diese drei Werte bei Bedarf abweichend vom Kanalsystem gespeichert werden.
Die Darstellung gilt einheitlich für Rundschächte, Sonderschächte und
Bodenabläufe in 2D und 3D. Beim Speichern kann
gezielt gewählt werden, ob die Vorgaben nur für neue Objekte, für die aktuelle
Markierung, für die vollständigen verbundenen Kanalsysteme der Markierung oder
für alle Kanalobjekte der Zeichnung gelten. Eine Bestandsaktualisierung erhält
Sohlhöhen, Schachtnamen, DN, Material, Lage und individuelle Farben. Ist bereits
eine Haltung markiert, wird deren Aktualisierung vorausgewählt; bei einer reinen
Schachtmarkierung das verbundene Kanalsystem und ohne Markierung wird bei einem
vorhandenen Kanalnetz die gesamte Zeichnung vorausgewählt. Damit
wird ein Wechsel auf Einliniengrafik beim Speichern sofort sichtbar. Die reine
Voreinstellung für nur neu zu zeichnende Objekte bleibt ausdrücklich wählbar.

Für den Schachtnamen sind eine eigene Schriftgröße und die Stile `Normal`,
`Fett`, `Unterstrichen` und `Fett und unterstrichen` wählbar. Nur die erste
Namenszeile erhält diese Typografie; die technischen Schachtdaten verwenden die
allgemeine Beschriftungsgröße.

Die kompakte Plan-Schachtbeschriftung zeigt keine Rohrmaterialkürzel. Zu- und
Ablaufzeilen erscheinen nur, wenn sich die dargestellten Anschlusshöhen
unterscheiden. Ein einzelner Anschluss heißt schlicht `Zulauf` bzw. `Ablauf`;
erst mehrere Zuläufe oder Abläufe erhalten `Z1`, `Z2` bzw. `A1`, `A2`.
Die zusätzlichen Höhenhinweise an den Rohranschlüssen sind eigenständige,
mit dem Schacht verknüpfte Beschriftungsobjekte. Sie können einzeln verschoben
und gedreht werden; eine manuell gewählte Lage bleibt bei späteren
Schachtaktualisierungen erhalten. Ihre Schriftgröße ist im Register
`Beschriftung` separat einstellbar.
Schachtblätter behalten ihre vollständigen Anschlussdaten einschließlich
Material und eindeutiger Kennung.

Beim Bearbeiten eines Schachts erhält jeder vorhandene Zulauf ein eigenes,
eindeutig mit `Z1`, `Z2` usw. und dem Haltungsnamen bezeichnetes Feld für die
Kanalsohle. Alle Felder stehen gleichzeitig sichtbar in einer kompakten
mehrspaltigen Matrix; auch viele Zuläufe verlängern das Fenster nicht. Direkt
hinter jedem Zulauf steht `ΔA`, der vorzeichenbehaftete Höhenversatz zur
Ablaufsohle in Zentimetern. Die Ablaufhöhe folgt unmittelbar unter der
Zulaufmatrix. Eine geänderte Zulaufhöhe wird ausschließlich an der zugeordneten
Haltung gespeichert; andere Zuläufe und der Ablauf bleiben unverändert. Die
Option `Alle Zu- und Abläufe mit gleicher Höhe` kann die Werte weiterhin
bewusst gemeinsam setzen. Eine daraus entstehende Umkehr der Fließrichtung
wird vor dem Speichern angezeigt und nur nach Bestätigung übernommen.

Schachtbearbeitung, Kanal- und Leitungseinstellungen, Gefälle- sowie
Mengendialoge begrenzen Größe und Position auf die aktuelle Monitorfläche.
Der Schachteditor ist zusätzlich in die kurzen Register `Allgemein`,
`Anschlusshöhen`, `Schachtbau` und `Deckel und Darstellung` aufgeteilt.

## Stutzen und Anschlüsse

`Kanalstutzen herstellen` verlangt zuerst eine vorhandene Haltung, danach die
Anschlusslage. Die neue Anschlussleitung hat standardmäßig DN 150, ist
änderbar und kann sohl-, achs-, kämpfer- oder scheitelgleich angeschlossen
werden. Die daraus berechnete Anschlusshöhe wird beschriftet. Die Hauptleitung
wird transaktional in zwei Resthaltungen geteilt; die überlagerte alte Haltung
wird erst nach erfolgreichem Aufbau und mit anschließender Löschkontrolle
entfernt. Die beiden geometrischen Restsegmente erhalten zusammen nur eine
Beschriftung mit der Gesamtlänge. Dasselbe gilt für eine aus mehreren
Knicksegmenten bestehende Abzweigleitung; die ein- oder zweizeilige Darstellung
wird aus den Haltungseinstellungen übernommen. Im 3D verbindet ein durchgängiges
T-/Y-Formstück beide Hauptleitungsseiten mit dem höhengerecht angesetzten
Abzweig, sodass keine offenen oder losgelösten Rohrstücke verbleiben.

Jeder neu erzeugte Anschluss auf einer vorhandenen Haltung erhält automatisch
eine Station. Das gilt für normale Abzweige, Kanalstutzen, Hausanschlüsse und
Bodenabläufe. Nullpunkt ist der Bezugspunkt des Schachts mit der tieferen
Hauptleitungssohle; bei gleicher Sohle gilt reproduzierbar der Endschacht der
gespeicherten Fließ- bzw. Objektrichtung. Gemessen wird entlang der zugehörigen
Hauptleitungsachse bis zum Anschluss. Stationswert und Nullpunktschacht stehen
in der Anschlussbeschriftung, werden nach Lage- oder Höhenänderungen neu
berechnet und bleiben nach einem späteren Teilen der Haltung verknüpft. Die
Achse wird bis zu den aktuell begrenzenden sichtbaren Schächten neu aufgebaut;
damit werden auch ältere Stutzendaten und später eingefügte Schächte korrekt
berücksichtigt.

Beim Hausanschluss ist die Höhe des freien Endpunkts zwingend anzugeben. Beim
Bodenablauf kann die Oberkante eingegeben oder von der Deckelhöhe des nächsten
Schachts übernommen werden. Ohne Bibliothekssymbol entsteht in 2D ein
30 × 30 cm großer Ablauf und in 3D ein 60 cm tiefer Kasten; beide Maße sind
änderbar. Bei einem reinen 2D-Symbol wird der Ersatzkasten zusätzlich erzeugt,
bei einem Hybrid-/3D-Symbol kann er abgeschaltet werden. Die Leitung beginnt an
der Unterkante des Ablaufs und fällt gleichmäßig zur Hauptleitung.
Hausanschluss- und Bodenablaufleitungen erhalten unabhängig von ihrer Anzahl
an Knicken genau eine gemeinsame Leitungsbeschriftung. Die Einstellung für
eine oder zwei Zeilen und die numerische Beschriftungsdrehung gelten für die
komplette Leitung. Die Drehung ist im Dialog `Kanalstrecke bearbeiten`
dauerhaft einstellbar. Zusätzlich kann die Beschriftung mit dem normalen
Vectorworks-Drehwerkzeug frei gedreht werden; diese grafische Drehung bleibt
beim gewöhnlichen Aktualisieren desselben Beschriftungsobjekts erhalten.

## Schächte und Sonderbauwerke

Runde Schächte besitzen Schachtdeckel, getrennte Zulauf-/Ablaufsohlen,
freie Namen und die bekannte 2D/3D-Darstellung. Für die Bauart steht im
Schachttext automatisch `B` für Beton oder `PP`; der Eintrag kann am Schacht
durch einen freien Text ersetzt werden. Ein Schacht kann
durch Anklicken einer darüberliegenden geschlossenen Polygon- oder
Polylinienkontur in einen Sonderschacht umgewandelt werden. Anschlüsse enden
dann an der tatsächlichen Kontur; in der Beschriftung entfällt der runde
Schachtdurchmesser. Als Kontur werden nur frei gezeichnete Objekte direkt auf
der Konstruktionsebene angenommen; die interne Polygongeometrie eines
Kanalobjekts wird sicher ausgeschlossen. Die Umwandlung setzt den Schacht und
seine angeschlossenen Haltungen genau einmal zurück. Scheitert der Neuaufbau,
bleibt die Ausgangskontur für einen erneuten Versuch erhalten.

`Absturz vor Schacht` speichert und beschriftet die obere Sohle der
ankommenden Haltung sowie die Unterkante der Absturzleitung. Eine Nullhöhe wird
vor dem Speichern abgewiesen. In 3D entsteht eine zusammenhängende Baugruppe
aus oberem Anschlussarm, senkrechtem Fallrohr und unterem Anschlussarm zum
Schacht; wiederholtes Bearbeiten ersetzt den vorhandenen Absturz derselben
Haltung. Wird ein Schacht
in eine Haltung eingesetzt, wird die darunterliegende Haltung entfernt und in
zwei sauber am Schacht endende Resthaltungen aufgeteilt. Vor dem Austausch
werden neben den Beschriftungen auch beide nativen Verknüpfungen der alten
Haltung zu ihren Endschächten gezielt gelöst; die neuen Resthaltungen behalten
ihre eigenen Verknüpfungen. Beschriftungen,
Fließrichtungspfeile und 3D-Rohre werden dabei gemeinsam neu aufgebaut. Die
ursprüngliche Haltung wird erst nach dem vollständigen Ersatz gelöscht; ihr
Verschwinden und das Löschen ihrer Beschriftung werden anschließend geprüft.

Jede angeschlossene Haltung wird am Schacht als eigener Anschluss geführt.
Die stabile Anschlussidentität besteht aus Haltungs-ID und Endpunkt; DN,
Material, Zu-/Ablauf, Anschlusshöhe und Richtung werden unmittelbar aus den
aktuellen Haltungsdaten abgeleitet. Auch zwei Anschlüsse mit gleicher Höhe
bleiben getrennte Einträge. Bei unterschiedlichen Höhen stehen die
Anschlusshöhen zusätzlich direkt an den jeweiligen Anschlussrichtungen. Das
Schacht-Informationsfeld ist bewusst kompakt und führt Schachtname, den
optionalen Zusatztext unmittelbar darunter, Bauart, `D.=`, `KD`, die
Kanalsohle und die Tiefe. Bei gleicher Höhe aller Anschlüsse erscheint genau
eine gemeinsame Zeile `KS`; nur bei unterschiedlichen Höhen werden Zu- und
Abläufe einzeln benannt. Rohrmaterial, Rohrdurchmesser und Richtungswinkel
bleiben den Schachtblättern vorbehalten. Separate Anschlusshöhen am Schacht
stehen leserichtig parallel zur jeweiligen Haltung.

Bei runden Kanalschächten wird ausdrücklich zwischen `PP-Schacht` und
`Betonschacht` gewählt. Der eingegebene Durchmesser ist der lichte
Innendurchmesser. Für Betonschächte gilt standardmäßig eine 15 cm starke,
änderbare Wandung; das physische Außenmaß wird durchgängig als
`Ø außen = Ø innen + 2 × Wandstärke` berechnet. Dieses Außenmaß steuert die
2D-Außenkontur, den 3D-Schachtkörper, die Lage des Schachtdeckels, die
Rohranschlusstrimmung und die Beschriftungsabstände. Innen-, Wand- und
Außendurchmesser bleiben als technische Berechnungswerte und für das
Schachtblatt erhalten; im kompakten Schachttext steht nur `D.=` mit dem
lichten Durchmesser.
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
zusammenhängende Kanalkette. In der Tabelle können mit Strg-/Umschalt-Klick
mehrere Haltungen ausgewählt und mit einem gemeinsamen Gefälle geändert
werden; alle markierten Zeichnungsobjekte werden dynamisch hervorgehoben.
Über den dauerhaft sichtbaren Startmenübefehl lassen sich zwei vorhandene
Schächte direkt mit einer neuen Haltung verbinden. Bereits markierte Schächte
werden übernommen; fehlende Schächte werden nacheinander grafisch gewählt.
DN, Material, Ein-/Doppelliniengrafik und 3D-Erzeugung werden zuvor in einem
kompakten Dialog gewählt; die Fließrichtung folgt automatisch der höheren zur
tieferen Sohle. Teilen,
Vereinigen, Löschen, Verschieben,
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

Die Rigole wird in 3D aus einer ausdrücklich geschlossenen Vierpunktkontur als
native Vectorworks-Extrusion erzeugt. Damit besitzt der Körper vier Seiten
sowie eine geschlossene Boden- und Deckfläche; der globale Polygonmodus wird
direkt danach wieder auf offen zurückgestellt, damit nachfolgende Kanalachsen
nicht unbeabsichtigt geschlossen werden.
