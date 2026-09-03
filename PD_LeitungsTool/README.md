# PD Leitungstool 1.1.0

Das Modul verwaltet Versorgungstrassen getrennt vom Kanalnetz. Eine Trasse ist
ein persistentes Vectorworks-Objekt und enthält eine oder mehrere Leitungen mit
eigenen DN-, Außenmaß- und Höhenketten.

Mehrere markierte Trassen lassen sich gemeinsam bearbeiten. Dabei werden die
vollständigen System-, DN-, Material-, Darstellungs-, Beschriftungs-, Höhen-
und 3D-Eigenschaften aus der ersten gewählten Trasse angeboten; Lage,
Objektidentität und Trassenname bleiben je Objekt erhalten. Der Neuaufbau aller
gewählten Trassen ist eine gemeinsame, geprüfte Transaktion und wird bei einem
Fehler vollständig zurückgesetzt.

Die Voreinstellungen umfassen nun auch alle wiederverwendbaren Darstellungs-,
Beschriftungs-, Höhen-, Gelände- und 3D-Werte. Sie können nur für neue Trassen
gespeichert, auf die markierten Leitungssysteme oder auf alle Leitungstrassen
der Zeichnung angewendet werden. Beim reinen Standard-Update bleiben Lage,
Name, DN, Material und bestehende Höhenketten unverändert.

Die Auswahl der ein- oder zweizeiligen Beschriftung ist vor dem ersten
Dialogereignis initialisiert. Dadurch kann eine neue Leitungstrasse nach dem
Öffnen des Dialogs unmittelbar gezeichnet werden, ohne dass beim Bestätigen
ein lokaler Variablenfehler entsteht.

Alle sichtbaren Leitungs- und Geländehöhen werden einheitlich mit genau zwei
Nachkommastellen ausgegeben; die Berechnung und Speicherung bleiben
ungerundet.

Eine Trasse darf mit dem normalen Vectorworks-Löschbefehl entfernt werden.
Bereits angelegte Mengen- und Summenblätter werden dabei als veraltet
vorgemerkt. Der Neuaufbau aus den tatsächlich noch vorhandenen Trassen erfolgt
erst beim nächsten Öffnen oder Export der Massenermittlung, damit das Zeichnen
und Bearbeiten nicht durch große Arbeitsblätter verzögert wird.

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
