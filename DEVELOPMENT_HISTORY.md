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
