# Entwicklungsverlauf

Der vollstaendige freigegebene Chat ist hier abrufbar:

https://chatgpt.com/s/cx_6a9822b6179c819196e9e4560a52eb72

## Zusammenfassung

- Einrichtung einer Vectorworks-2026-Entwicklungsumgebung und erster Diagnosetest.
- Bestandspruefung der vorhandenen Plug-ins mit Schwerpunkt Datensicherheit,
  fachliche Richtigkeit, Vectorworks-API, Bedienung, Leistung und Installation.
- Reparaturen am Gefaelletool, darunter Punktzeichnung, Abbruch, Verzweigungen,
  Hoehenbehandlung, Objekt-Ereignisse und Darstellung.
- Erweiterungen der Massen- und Mengenermittlung sowie Ueberarbeitung der Dialoge.
- Neuordnung der Werkzeuge fuer Planpruefung, Rigolen, Sichtbarkeiten und offene Flaechen.
- Entwicklung eigenstaendiger Kanal-, Leitungs-, Gelaende- und Baugrubenmodule.
- Mehrere Iterationen der grafischen Werkzeuge, Symbole, Menues, Objekt-Info-Palette
  sowie Abschluss-, Enter- und Zurueck-Tastenbehandlung.
- Live-Pruefungen in Vectorworks und fortlaufende Korrekturen bis Version 1.30.22.

## Hinweis zur Historie

Der Quellstand wurde aus dem Gesamtinstaller 1.30.22 rekonstruiert. Fruehere
Zwischenstaende und die urspruenglichen Commits waren im Auslieferungspaket nicht
enthalten. Dieses Repository beginnt daher mit einem Snapshot von Version 1.30.22.

## Weiterentwicklung im Repository

- Kanaltool 1.0.23: kompakte Schachtbeschriftung mit Schachtname, Bauart
  (`B`, `PP` oder Freitext), `D.=`, `KD`, einzelnen Zu-/Abläufen und Tiefe.
- Die Kanalkette besitzt eine echte Mehrfachauswahl für Haltungen; ein
  gemeinsames Gefälle kann mit Strg-/Umschalt-Klick vorgemerkt werden.
- Genau zwei markierte vorhandene Schächte können über einen eigenen kompakten
  Dialog direkt mit einer neuen Haltung verbunden werden.
- Regressionsprüfungen decken Schachttext, Fließrichtung, Doppelverbindungen,
  Startmenü, Dialogaufbau und Mehrfachauswahl ab.
- Kanaltool 1.0.24: Die grafische Objektwahl behandelt den von Vectorworks bei
  einem abgebrochenen oder fehlgeschlagenen Treffer gelieferten `None`-Wert
  sicher. Schachtblatt-Layoutebenen setzen zusätzlich die nativen Blatt- und
  Druckseitenvariablen und werden erst nach bestätigter DIN-A4-Querformatgröße
  freigegeben.
- Kanaltool 1.0.25: Der Rohrdurchmesser entfällt in den Zu-/Ablaufzeilen der
  kompakten Schachtbeschriftung. Separate Anschlusshöhen am Schacht werden
  parallel zur zugehörigen Haltung und automatisch leserichtig ausgerichtet.
  Der dauerhaft sichtbare Befehl zum nachträglichen Verbinden zweier Schächte
  übernimmt vorhandene Markierungen und fragt fehlende Schächte grafisch ab.
- Kanaltool 1.0.26: Die Voreinstellungen verwenden drei kompakte native
  Register statt einer unbedienbar hohen Einspaltenmaske. Neue Vorgaben lassen
  sich wahlweise nur speichern, auf die Markierung, auf deren topologisch
  verbundene Kanalsysteme oder auf alle Kanalobjekte der Zeichnung anwenden;
  technische Bestandsdaten bleiben erhalten. Der Schachtname besitzt eine
  eigene Schriftgröße sowie Normal-, Fett- und Unterstreichungsstile.
  Schachtblatt-Layoutebenen setzen DIN A4 quer nun mit den nativen
  Blattvariablen in Dokumenteinheiten und prüfen die Orientierung vor der
  Seitenerzeugung.
- Kanaltool 1.0.27: In der kompakten Plan-Schachtbeschriftung entfallen
  Rohrmaterialkürzel. Anschlusszeilen und die linienparallelen Höhenhinweise
  erscheinen nur bei unterschiedlich dargestellten Anschlusshöhen. Einfache
  Zu- und Abläufe bleiben unnummeriert; Z1/Z2 bzw. A1/A2 werden erst bei
  mehreren Anschlüssen derselben Rolle verwendet. Die vollständigen
  Anschlussdaten im Schachtblatt bleiben unverändert erhalten.
- Kanaltool 1.0.28: Das Aktionsmenü ist auf sieben eindeutige Erstellungs- und
  Globalbefehle reduziert und gegen mehrfach ausgelöste Dialoginitialisierung
  abgesichert. Objektbezogene Aktionen stehen rechts in der Objekt-Info-Palette;
  neu hinzugekommen sind Schacht–Schacht-Verbindung, Haltungen vereinigen und
  ausgewählte Kanalobjekte löschen. Befehle für mehrere Objekte erhalten die
  bestehende Mehrfachauswahl.
- Kanaltool 1.0.29: Höhenänderungen in der Kanalkette und in der direkten
  Schachtbearbeitung erkennen eine daraus entstehende Fließrichtungsumkehr vor
  dem Schreiben. Eine Ja/Nein-Abfrage nennt die betroffenen Haltungen; nur bei
  Bestätigung werden Endpunktzuordnung, positives Gefälle, Zu-/Ablauftexte,
  Pfeile und abhängige Schachtobjekte transaktional neu aufgebaut.
- Kanaltool 1.1.1: Der auf GitHub vorhandene Stand 1.1.0 mit realem
  Rohraußendurchmesser, Rohrwandstärke, hohler 3D-Geometrie und erweiterten
  Mengentabellen wurde konfliktfrei mit den Bedienungs-, Beschriftungs-,
  Schachtblatt-, Ketten- und Fließrichtungsänderungen zusammengeführt.
- Kanaltool 1.1.3: Nach der Freigabe 1.1.2 wurden vier gemeldete
  Laufzeitregressionen isoliert abgesichert. Beim Teilen für Kanalstutzen wird
  die abhängige Haltungsbeschriftung vor der alten Haltung gelöscht und bei
  einer abgewiesenen Löschung wiederhergestellt. Die Schachtblatterzeugung
  akzeptiert die von Vectorworks 2026 unter Windows in Hochformatreihenfolge
  gemeldeten Maße desselben A4-Druckmediums, behält aber den Zeichenrahmen in
  DIN A4 quer. Das Gefälletool behandelt vorübergehend noch nicht verfügbare
  3D-Einfügepunkte neuer PIOs ohne `NoneType`-Absturz. Der Schachtdialog wurde
  verkleinert; Zusatztext und gemeinsame Kanalsohle erscheinen wieder in der
  Schachtbeschriftung.
- Gefälletool 1.17.6: Der in Vectorworks 2026 nach Abschluss einer neu
  gezeichneten Gefällelinie reproduzierte `NoneType`-Fehler ist behoben.
  Neben der bereits abgesicherten 3D-Position wird nun auch eine während des
  ersten PIO-Aufbaus vorübergehend leere 2D-Einfügeposition an allen
  Erzeugungs-, Beschriftungs- und Höhenfanggrenzen sicher behandelt. Ein
  vollständiger Ketten-Render-Test bildet genau diese verzögerte native
  Rückgabe nach.
- Kanaltool 1.1.4 / Leitungstool 1.0.2 / Mengenausgabe 1.1.1: Änderungen an
  Material und anderen Kanal-/Leitungseigenschaften lösen bei einem
  zusammengesetzten Vorgang nur noch einen Tabellenneuaufbau aus;
  Beschriftungs-Resets stoßen keine Mengenermittlung mehr an. Die Ausgabe
  besitzt ein separates reines Summenblatt für gruppierte Kanalrohre nach Art,
  DN und Material, Kanalstutzen, Schächte, Leitungen, Erdmassen und Verbau.
  Interne Objekt- und Netz-IDs wurden aus allen sichtbaren Tabellen entfernt.
  Der Excel-Pfad erhält zuverlässig die Endung `.xlsx`; die erzeugte Datei wird
  in der Regression als OOXML und zusätzlich mit Microsoft Excel geprüft.
- Gefälletool 1.17.7: Die transaktional mitgeführten nativen Vectorworks-
  Vermessungspunkte werden bei der 3D-Erstellung nicht mehr irrtümlich an
  die Beschriftungsroutine für eigene Gefälle-PIOs übergeben. Damit ist der
  Abbruch `NoneType object is not subscriptable` beim Abschließen einer neu
  gezeichneten Gefällelinie beseitigt.
- Gelände- und Baugrubenmodul 1.0.18: Fremdzeichnungen werden ohne die
  beobachtete 1.024-Objekt-Grenze über native Ebenen- und Objektlisten gelesen.
  Importierte Linien werden auf temporären Kopien von Vectorworks selbst in
  echte 3D-Polygone umgewandelt; Texte verwenden Dokument-XY und die reale
  Z-Höhe ihrer Objektmatrix. Höhen- und Dublettenhinweise brechen die Ausgabe
  nicht mehr ab. Für Vermessungskoordinaten im Millionenbereich werden die
  DGM-Quellen am internen Nullpunkt erzeugt, sodass das native Geländemodell
  ohne kilometerweite Konturverzerrungen trianguliert, aber georeferenziert
  angezeigt wird. Ein Live-Test in Vectorworks Landschaft 2026 verarbeitete
  600 Texte, 276 Linien und einen Bogen zu 600 Punkten, 277 Bruchkanten,
  952 Modellpunkten und 1.892 Dreiecken.
- Gelände- und Baugrubenmodul 1.0.19: Die Integritätsprüfung der
  Programmeinstiege akzeptiert nun ausschließlich byteidentische Skripte oder
  deren inhaltlich identische LF-/CRLF-Darstellung. Damit bleiben die
  kryptografisch geprüften Startdateien auch nach einem Windows-Git-Checkout
  ausführbar, ohne beliebige inhaltliche Änderungen zuzulassen.
- Gelände- und Baugrubenmodul 1.0.20: Das nach der nativen DGM-Erzeugung
  markierte Modell wird nun zuverlässig im Zeichenfenster eingepasst. Der
  universelle Vectorworks-Menüname ist streng groß-/kleinschreibungsabhängig;
  `Fit To Objects` ersetzt die zuvor wirkungslose Schreibweise. Im Live-Test
  wurde das vollständige, bereite `DGM Bestand` dadurch unmittelbar mit
  korrekter Ausdehnung und Höhenlinien angezeigt.
- Gelände- und Baugrubenmodul 1.0.21: Für intern normalisierte DGM-Quellen wird
  die georeferenzierte Weltkoordinate nun mit dem aktuellen Vectorworks-
  Dokumentursprung auf die native DGM-Abfragekoordinate abgebildet. Direkt nach
  der Erzeugung wird jeder verbrauchte Quellstützpunkt über
  `DTM6_GetZatXY` geprüft und die Abbildung dauerhaft am Modell gespeichert.
  Baugruben- und Vergleichsberechnungen verwenden dieselbe Transformation. Im
  Live-Test lieferten alle 1.172 Stützpunkte des aus 600 Texten, 276 Linien und
  einem Bogen erzeugten `DGM Bestand` ihre Quellhöhe ohne messbare Abweichung.
- Gelände- und Baugrubenmodul 1.0.22: Die Koordinatenabbildung wird nicht mehr
  als zusätzlicher Datensatz direkt an das native Geländemodell gehängt,
  sondern auf dessen eigener Quelldaten-Ebene gespeichert. Damit wird das
  Plug-in-Objekt nach der nativen Triangulation nicht mehr durch eine
  Datensatzänderung zurückgesetzt und das berechnete TIN bleibt auch nach dem
  Speichern und erneuten Öffnen der Zeichnung erhalten.
- Gelände- und Baugrubenmodul 1.0.23: Die persistente Koordinatenabbildung
  liegt nun vollständig getrennt vom nativen Geländemodell auf dessen visueller
  Kontrollebene. Damit wird auch die Modelleebene nach der Triangulation nicht
  mehr verändert; der native 2D-/3D-Grafikcache mit Geländegrenze,
  Höhenlinien und Triangulation bleibt erhalten. Der Assistent weist außerdem
  eindeutig darauf hin, dass Schritt 1 den nativen Erzeugungsdialog bereits
  selbst öffnet und der Befehl danach nicht nochmals ausgeführt werden darf.
- Gelände- und Baugrubenmodul 1.0.24: Die numerisch stabil um den internen
  Nullpunkt triangulierte DGM-Geometrie wird nach der nativen Erzeugung als
  vollständiges Plug-in-Objekt um den zuvor entfernten XY-Datenanker
  zurückversetzt. Das sichtbare Geländemodell liegt damit wieder deckungsgleich
  auf den ursprünglichen Vermessungsdaten. Die native Höhenprüfung erfolgt
  anschließend an den zurückversetzten Originalkoordinaten.
- Gelände- und Baugrubenmodul 1.0.25: Die Auswahllisten der Modellverwaltung,
  Baugrube und des Modellvergleichs werden erst im nativen Vectorworks-
  Initialisierungsereignis befüllt. Dadurch erscheinen bereits erkannte,
  benannte Geländemodelle sowie Aktionen und Rollen zuverlässig in den
  Pulldown-Menüs von Vectorworks 2026.
- Kanaltool 1.1.5 / Leitungstool 1.0.3 / Gefälletool 1.17.8 /
  Mengenausgabe 1.1.2: Vollständige modulübergreifende Fehlerprüfung mit
  abgesicherten nativen Rückgabewerten, transaktionalem Objektaufbau,
  konsistenter 3D-Rohr- und Sonderschachtgeometrie, stabiler Kopierlogik,
  belastbaren Schachtblättern und topologisch korrekter Massenermittlung.
  Enter, Doppelklick und Rücktaste steuern das Punktwerkzeug zuverlässig;
  ein einzelner Höhenpunkt lässt sich ebenfalls abschließen. Leitungsdaten,
  eigene Typen, Beschriftungsstile und beschädigte Datensätze werden ohne
  Folgeschäden verarbeitet. 132 automatisierte Regressionstests sichern den
  freigegebenen Stand ab.
- Kanaltool 1.2.0 / Mengenausgabe 1.2.0: Rigolenbauwerke werden als eigene,
  verwaltete Kanalobjekte mit frei wählbaren Abmessungen, Unterkante,
  Geländeoberkante, Grundrissdrehung, Farben, Transparenz und Freitext geführt.
  Die gerahmte Beschriftung beginnt mittig und erhält beim Verschieben eine
  Bezugslinie; Grundriss und einfacher 3D-Körper bleiben gemeinsam editierbar.
  Kanäle lassen sich an einer grafisch gewählten Rigolenkante und einer
  explizit abgefragten Anschlusshöhe anbinden. Die Massenermittlung enthält
  Brutto- und 95-%-Wasservolumen, Böschungsbaugruben mit 45°/60° und 0,50 m
  Arbeitsraum, Aushub, optionalen künftigen Oberbau als eigene Position sowie
  die entsprechend verminderte Wiederverfüllung. Ein eigenes Rigolenblatt ist
  Bestandteil der Arbeitsblatt- und Excel-Ausgabe. 143 automatisierte
  Regressionstests sichern den gemeinsamen Stand ab.
- Kanaltool 1.2.1: Die Renderprüfung parametrischer Kanalobjekte arbeitet ohne
  erneutes Schreiben in den laufenden Objektcallback. Dadurch werden neue
  Kanalstränge nach dem grafischen Abschluss nicht mehr zurückgerollt und zwei
  vorhandene Schächte wieder zuverlässig mit einer Haltung verbunden. Native
  Zeichenwerkzeuge halten außerdem die automatische Mengentabelle während der
  vollständigen Geometrieerzeugung an und aktualisieren sie danach genau einmal;
  ein Tabellenfehler kann die bereits erstellte Kanalgeometrie nicht abbrechen.
  147 automatisierte Regressionstests sichern den Stand ab.
- Kanaltool 1.2.2: Unterschiedliche Zu- und Ablaufhöhen werden nicht mehr als
  unbewegliche Unterobjekte des Schachts gezeichnet. Jeder Anschluss erhält ein
  eigenes verknüpftes Beschriftungsobjekt, das unabhängig verschoben und gedreht
  werden kann; seine manuelle Lage bleibt bei Schachtaktualisierungen erhalten.
  Die Anschluss-Schriftgröße ist separat in den kompakten Voreinstellungen
  wählbar. Bestehende Schächte werden beim nächsten Höhen- oder
  Darstellungsupdate automatisch auf die neuen Anschlussbeschriftungen
  umgestellt. 148 automatisierte Regressionstests sichern den Stand ab.
- Kanaltool 1.2.3: Der wahlweise ein- und ausschaltbare Haltungsname wird als
  eigene erste Zeile oberhalb von Gefälle und Länge gezeichnet. Die ein- oder
  zweizeilige Darstellung steuert ausschließlich die darunterliegenden
  technischen Angaben; beim Ausschalten entfällt nur die Namenszeile.
  148 automatisierte Regressionstests sichern den Stand ab.
- Kanaltool 1.2.4: Beim Einsetzen eines Schachts oder Anschlusses in eine
  vorhandene Haltung werden vor dem Austausch nicht nur die abhängigen
  Beschriftungen, sondern auch die nativen Verknüpfungen der alten Haltung zu
  beiden Endschächten gezielt entfernt. Nur die alte Haltung wird gelöst; die
  bereits erzeugten Ersatzhaltungen bleiben verbunden. Scheitert das Löschen,
  werden die gelösten Altverknüpfungen und Beschriftungen wiederhergestellt.
  Zwei zusätzliche Grenztests prüfen Erfolg und Rollback; insgesamt bestehen
  150 automatisierte Tests.
- Kanaltool 1.2.5: Die Umwandlung eines Rundschachts in einen Sonderschacht
  validiert den abschließenden Vectorworks-Objekthandle erneut und akzeptiert
  nur frei gezeichnete, geschlossene Konturen direkt auf der
  Konstruktionsebene. Interne Polygon-Unterobjekte eines parametrischen
  Kanalobjekts können dadurch nicht mehr als später ungültige Vorlage in den
  Ablauf gelangen. Der bereits transaktional aktualisierte Schacht und seine
  angeschlossenen Haltungen werden nicht länger ein zweites Mal zurückgesetzt;
  die Ausgangskontur wird erst nach erfolgreichem Neuaufbau entfernt und bleibt
  bei einem Fehler für den nächsten Versuch erhalten. Vier zusätzliche
  Wiederholungs- und Handle-Grenztests sichern den Absturzfall ab; insgesamt
  bestehen 154 automatisierte Tests.
- Kanaltool 1.2.6: Die Vierpunktkontur der Rigole wird vor der 3D-Extrusion
  ausdrücklich geschlossen. Vectorworks erzeugt dadurch einen nativen
  Extrusionskörper mit vier Seiten sowie Boden- und Deckfläche statt einer
  offenen U-förmigen Mantelfläche. Der globale Polygonmodus wird nach der
  Profilerzeugung zuverlässig zurückgestellt und der resultierende Objekttyp
  gegen den dokumentierten Extrusionstyp 24 geprüft. Zwei zusätzliche
  API-Grenztests prüfen die geschlossene Erzeugungsreihenfolge und weisen ein
  falsches Vectorworks-Ergebnis zurück; insgesamt bestehen 156 automatisierte
  Tests.
- Kanaltool 1.2.7: Schachtblatt- und Papiergröße werden über die nativen
  Layervariablen 165 bis 168 in den von Vectorworks erwarteten physischen Zoll
  gesetzt. Die fehlerhafte zusätzliche Umrechnung mit den Dokumenteinheiten,
  die A4-Blätter in metrischen Projekten auf mehrere hundert Zoll vergrößerte,
  entfällt. Beim gemeinsamen PDF-Export wird jede Schachtblatt-Layoutebene vor
  dem Schreiben aktiviert und der im Exportdialog gewählte gemeinsame
  Dateiname verwendet. Zwei zusätzliche API-Grenztests prüfen die
  Einheitenunabhängigkeit und die vollständige Mehrseiten-PDF-Befehlsfolge;
  insgesamt bestehen 158 automatisierte Tests.
- Kanaltool 1.2.8 / Leitungstool 1.0.4 / Gefälletool 1.17.9 /
  Mengenausgabe 1.2.1: Normales Löschen verwendet nun gerichtete
  Vectorworks-Objektverknüpfungen. Das Löschen eines Schachts oder
  Gefällepunktes entfernt nur wirklich abhängige Haltungen beziehungsweise
  Ketten; das Löschen einer Haltung, Trasse oder Kette aktualisiert die
  verbleibenden Endobjekte, ohne sie zu entfernen. Alte Reset-Verknüpfungen
  werden beim nächsten Objektneuaufbau automatisch migriert. Ein unsichtbarer
  Mengen-Löschbeobachter erzwingt anschließend den Neuaufbau vorhandener
  Detail- und Summenblätter aus dem realen Restbestand. Vier zusätzliche
  Regressionstests prüfen Kanal- und Gefällerichtungen, den Löschbeobachter und
  das Entfernen gelöschter Haltungen aus der Mengenermittlung; insgesamt
  bestehen 162 automatisierte Tests.
- Kanaltool und gemeinsamer Kanal-/Leitungsaufruf 1.2.9: Die
  Schachtbearbeitung führt jeden einmündenden Anschluss als eigenes, stabil
  über die Haltungs-ID zugeordnetes Feld (`Z1`, `Z2` usw.). Eine Änderung
  betrifft nur die gewählte Zulaufhaltung; Gefälle, Fließrichtungsprüfung,
  Schachtsohle und Beschriftungen werden anschließend gemeinsam neu aufgebaut.
  Die ausdrückliche Gleichschaltung aller Zu- und Abläufe bleibt als Option
  erhalten. Zwei zusätzliche Dialog- und Transaktionstests prüfen die
  getrennte Änderung sowie die unveränderte Nachbarhaltung; insgesamt bestehen
  164 automatisierte Tests.
- Kanaltool und gemeinsamer Kanal-/Leitungsaufruf 1.3.0, Leitungstool 1.0.5,
  Gefälletool 1.18.0 und Mengenausgabe 1.2.2: Der Schachteditor verwendet vier
  kurze Register. Sämtliche Zulaufsohlen bleiben gleichzeitig in einer
  mehrspaltigen Matrix sichtbar; auch 20 geprüfte Zuläufe erzeugen keine
  überlange Einzelspalte und benötigen keine Auswahlliste. Zu jedem Zulauf wird
  der beim Ändern sofort aktualisierte Höhenversatz zur direkt darunter
  stehenden Ablaufsohle in Zentimetern angezeigt. Alle Dialog-Grundfunktionen
  der Kanal-, Leitungs-, Gefälle- und Mengenkette begrenzen ihre Größe und
  Position zusätzlich auf den aktuellen Bildschirm. Ein weiterer
  Bildschirm-Grenztest deckt 800 × 500 Pixel ab; insgesamt bestehen 165
  automatisierte Tests.
- Kanaltool und gemeinsamer Kanal-/Leitungsaufruf 1.3.1: Für jedes Kanalsystem
  RW, SW und MW stehen getrennte Schacht-Linienfarben, Schacht-Füllfarben und
  Fülltransparenzen zur Verfügung, ohne die Rohrfarben zu verändern. Die
  Fülltransparenz wirkt in 2D und 3D, während die Schachtkontur vollständig
  deckend bleibt. Jeder Schacht kann diese drei Systemwerte zusätzlich
  individuell überschreiben. Alte Einstellungen übernehmen beim ersten Laden
  ihre bisherige Systemfarbe für Linie und Füllung. Vier zusätzliche Modell-,
  Dialog- und Vectorworks-API-Grenztests erhöhen den Gesamtumfang auf 169
  automatisierte Tests.
- Kanaltool und gemeinsamer Kanal-/Leitungsaufruf 1.3.2, Leitungstool 1.0.6
  und Gefälletool 1.18.1: Zu- und Ablaufhöhen am Schacht werden wieder als
  eigenständig verschiebbare, leitungsparallele Beschriftungsobjekte erzeugt
  und können in den Kanal-Voreinstellungen gemeinsam ein- oder ausgeschaltet
  werden. Beim Anwenden auf bestehende Objekte werden fehlende
  Anschlussbeschriftungen ergänzt. Das Schachttextfeld führt unabhängig von
  der Anschlusslage immer sämtliche Zuläufe vor sämtlichen Abläufen auf.
  Zusätzlich zeigen Kanal-, Leitungs- und Gefälletool alle Höhenwerte in
  Dialogen, Listen, Meldungen, Zeichnungsbeschriftungen und Schachtblättern
  einheitlich mit genau zwei Nachkommastellen; intern wird weiterhin mit voller
  Genauigkeit gerechnet und gespeichert. Drei zusätzliche Dialog-, Format- und
  Reihenfolgetests erhöhen den Gesamtumfang auf 172 automatisierte Tests.
- Mengenausgabe 1.2.3: Vor Arbeitsblatt- und Excel-Ausgabe wird ausdrücklich
  zwischen der kompakten Summenliste und der vollständigen Einzelmassenliste
  gewählt. Die Einzelmassen enthalten eigene Summenzeilen für Haltungen,
  Schächte, Rigolen, Leitungen, Erdmassen und Stutzen sowie eine abschließende
  Gesamtsummenübersicht. Eine in Excel geöffnete Zieldatei blockiert die
  Ausgabe nicht mehr; die neue Datei erhält in diesem Fall einen eindeutigen
  `_neu_`-Zeitstempel. Die Oberbaustärke wird jetzt durchgängig in Metern
  eingegeben, gespeichert und ausgegeben; alte Zentimeterwerte werden beim
  Laden wertgleich migriert. Fünf zusätzliche Auswahl-, Summen-, Migrations-,
  Arbeitsblatt- und Dateisperrentests sichern die Änderung ab. Nach der
  Zusammenführung mit dem aktuellen Gelände-/Baugrubenstand bestehen insgesamt
  190 automatisierte Tests.
- Mengenausgabe 1.2.4: Die Oberbaustärke wird im Dialog als fest in Metern
  definiertes Zahlenfeld statt als von den Dokumenteinheiten abhängiges
  Längenfeld gelesen. Dadurch bleibt die Eingabe `0,5` auch in Dokumenten mit
  Millimeter als Dokumenteinheit exakt `0,5 m` und wird nicht fälschlich als
  `500 m` gegen den zulässigen Bereich geprüft. Der Dialogtest kontrolliert
  nun zusätzlich, dass Erzeugung und Auslesen denselben REAL-Feldtyp verwenden.
- Gelände- und Baugrubenmodul 1.0.26: Die Quelldatenerfassung ist strikt auf
  die aktuelle Markierung begrenzt. Die frühere Erweiterung auf sämtliche
  Objekte der aktiven oder einer von der Auswahl berührten Ebene wurde samt
  Dialogoption entfernt. Große DWG-Auswahlen werden weiterhin über mehrere
  native Wege vervollständigt, beim vollständigen Ebenendurchlauf aber nur bei
  gesetztem Vectorworks-Auswahlstatus übernommen. Wiederholte Läufe erzeugen
  getrennte, eindeutig benannte Quell- und Kontrollebenen sowie eigenständige
  DGM, ohne bereits vorhandene Modelle zu verändern.
