# PD Leitungstool

Das Modul verwaltet Versorgungstrassen getrennt vom Kanalnetz. Eine Trasse ist
ein persistentes Vectorworks-Objekt und enthält eine oder mehrere Leitungen mit
eigenen DN-, Außenmaß- und Höhenketten.

Der übliche Ablauf ist: Typ wählen, eine gemeinsame Trassenachse zeichnen,
Anzahl/Abstand/Achsbezug festlegen und mit Doppelklick abschließen. Ein
Doppelklick auf das erzeugte Objekt öffnet die Bearbeitung. Die Klassen werden
automatisch nach Leitungstyp und DN angelegt.

Bei Geländebezug wird die Überdeckung zur realen Rohraußenkrone gerechnet. Das
Tool rät keine materialabhängige Wandstärke; der Außendurchmesser muss bestätigt
werden. Die tatsächliche ausgerundete Parallelgeometrie wird entlang des
Geländemodells in Abständen von höchstens 1,00 m geprüft. Verschieben oder
Drehen einer DGM-gebundenen Trasse löst eine neue Abfrage des gespeicherten
Geländemodells aus. Die Höhen können anschließend über die Höhenkette einzeln
verändert werden; damit wird die betreffende Trasse bewusst auf manuelle Höhen
umgestellt.

Die Leitungsprüfung meldet Grundriss- und 3D-Länge der tatsächlich gerenderten
Trassen, Winkelpunkte sowie bei DGM-Bindung minimale und maximale Überdeckung
und erkannte Unterschreitungen. Ein zu enger Ausrundungsradius wird gegen
Parallelversatz und realen Rohraußendurchmesser geprüft. Scheitert ein nativer
Vectorworks-Neuaufbau, werden die vorherigen Objektdaten wiederhergestellt und
es wird keine Erfolgsmeldung ausgegeben.
