# -*- coding: utf-8 -*-
"""
Zentrale Konstanten des Rigolen-Tools.
Keine Vectorworks-Abhaengigkeit -> ausserhalb von VW testbar.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

TOOL_NAME = "Rigole"
TOOL_VERSION = "0.17.2"

# ---------------------------------------------------------------------------
# Datensatz / Record Format
# ---------------------------------------------------------------------------
RECORD_NAME = "DB_Rigole"

# WICHTIG: vs.NewField kuerzt Feldnamen ohne Warnung auf 20 Zeichen.
# Alle Namen unten sind daher <= 20 Zeichen.
#
# Feldtypen (Appendix E der VW-Skript-Referenz):
#   1 = Integer, 2 = Boolean, 4 = Text, 5 = Number-decimal
#   Anzeigestil (fFlag) bei Number-decimal = Anzahl Nachkommastellen (0..9)
#
# Aufbau je Eintrag: (Feldname, Typ, Anzeigestil, Defaultwert-als-Text)
FIELD_ID = "Rigolen_ID"
FIELD_ART = "Rigolenart"
FIELD_SYSTEM = "Systembezeichnung"
FIELD_KORB_L = "Korb_Laenge"
FIELD_KORB_B = "Korb_Breite"
FIELD_KORB_H = "Korb_Hoehe"
FIELD_ANZ_L = "Anzahl_Laenge"
FIELD_ANZ_B = "Anzahl_Breite"
FIELD_ANZ_H = "Anzahl_Hoehe"
FIELD_GES_L = "Gesamtlaenge"
FIELD_GES_B = "Gesamtbreite"
FIELD_GES_H = "Gesamthoehe"
FIELD_VERSCHWEISST = "Verschweisst"
FIELD_KOEFF = "Speicherkoeffizient"      # 19 Zeichen
FIELD_V_BRUTTO = "Volumen_Brutto"
FIELD_V_SPEICHER = "Speichervolumen"
FIELD_HOEHENBEZUG = "Hoehenbezug"
FIELD_OK = "OK_Rigole"
FIELD_UK = "UK_Rigole"
FIELD_BELASTUNG = "Belastungsklasse"
FIELD_SYMBOL = "Symbolname"              # Symbol der GESAMTEN Rigole
FIELD_KORB_SYMBOL = "Korb_Symbol"        # Symbol eines einzelnen Korbes
FIELD_SCHACHT_DN = "Schacht_DN"
FIELD_SCHACHT_ANZ = "Schacht_Anzahl"
FIELD_SCHACHT_OK = "Schacht_OK"
FIELD_SCHACHT_UK = "Schacht_UK"
FIELD_KOMMENTAR = "Kommentar"
FIELD_DATUM = "Erstellungsdatum"
FIELD_EINHEIT = "Einheit_Laengen"        # Doku, in welcher Einheit gespeichert wurde

RECORD_FIELDS = [
    # (Feldname,            Typ, Stil, Default)
    (FIELD_ID,                4, 0, ""),
    (FIELD_ART,               4, 0, ""),
    (FIELD_SYSTEM,            4, 0, ""),

    (FIELD_KORB_L,            5, 3, "0"),
    (FIELD_KORB_B,            5, 3, "0"),
    (FIELD_KORB_H,            5, 3, "0"),

    (FIELD_ANZ_L,             1, 0, "0"),
    (FIELD_ANZ_B,             1, 0, "0"),
    (FIELD_ANZ_H,             1, 0, "0"),

    (FIELD_GES_L,             5, 3, "0"),
    (FIELD_GES_B,             5, 3, "0"),
    (FIELD_GES_H,             5, 3, "0"),

    (FIELD_VERSCHWEISST,      2, 2, "FALSE"),

    (FIELD_KOEFF,             5, 3, "0.95"),
    (FIELD_V_BRUTTO,          5, 3, "0"),
    (FIELD_V_SPEICHER,        5, 3, "0"),

    (FIELD_HOEHENBEZUG,       4, 0, "OK"),
    (FIELD_OK,                5, 3, "0"),
    (FIELD_UK,                5, 3, "0"),

    (FIELD_BELASTUNG,         4, 0, ""),
    (FIELD_SYMBOL,            4, 0, ""),
    (FIELD_KORB_SYMBOL,       4, 0, ""),

    (FIELD_SCHACHT_DN,        4, 0, ""),
    (FIELD_SCHACHT_ANZ,       1, 0, "0"),
    (FIELD_SCHACHT_OK,        5, 3, "0"),
    (FIELD_SCHACHT_UK,        5, 3, "0"),

    (FIELD_KOMMENTAR,         4, 0, ""),
    (FIELD_DATUM,             4, 0, ""),
    (FIELD_EINHEIT,           4, 0, "m"),
]

# ---------------------------------------------------------------------------
# Rigolen-ID
# ---------------------------------------------------------------------------
ID_PREFIX = "RIG-"
ID_DIGITS = 3          # RIG-001
ID_START = 1

# ---------------------------------------------------------------------------
# KIESRIGOLE - eigener Datensatz, eigene Nummernfolge, eigene Klassen
# ---------------------------------------------------------------------------
# Die Kiesrigole ist eine andere Bauart: kein Korbraster, sondern ein
# Schuettkoerper mit einem Draenrohr. Sie bekommt deshalb ein eigenes
# Datensatzformat, damit Auswertungen beide Bauarten sauber trennen koennen.
ART_KIESRIGOLE = "Kiesrigole"

RECORD_NAME_KIES = "DB_Kiesrigole"

KFIELD_ID = "Kiesrigolen_ID"
KFIELD_ART = "Rigolenart"
KFIELD_SYSTEM = "Systembezeichnung"
KFIELD_LAENGE = "Laenge"
KFIELD_BREITE = "Breite"
KFIELD_HOEHE = "Hoehe"
KFIELD_MATERIAL = "Material"
KFIELD_KOEFF = "Speicherkoeffizient"      # 19 Zeichen
KFIELD_V_BRUTTO = "Volumen_Brutto"
KFIELD_V_SPEICHER = "Speichervolumen"
KFIELD_ROHR_DN = "Draenrohr_DN"
KFIELD_ROHR_DA = "Draenrohr_Durchm"     # Nenndurchmesser in m
KFIELD_ROHR_UK = "Draenrohr_UK"           # Abstand UK Rohr zur Kiessohle
KFIELD_ROHR_ACHSE = "Draenrohr_Achse"     # daraus errechnete Achshoehe
KFIELD_ROHR_LAENGE = "Draenrohr_Laenge"   # verlegte Laenge, ohne Schaechte
KFIELD_ROHR_BRUTTO = "Draenrohr_brutto"   # Laenge vor dem Auftrennen
KFIELD_SCHACHT_DN = "Schacht_DN"
KFIELD_SCHACHT_ANZ = "Schacht_Anzahl"
KFIELD_SCHACHT_OK = "Schacht_OK"
KFIELD_SCHACHT_UK = "Schacht_UK"
KFIELD_ROHR_VOLUMEN = "Draenrohr_Volumen"
KFIELD_HOEHENBEZUG = "Hoehenbezug"
KFIELD_OK = "OK_Rigole"
KFIELD_UK = "UK_Rigole"
KFIELD_BELASTUNG = "Belastungsklasse"
KFIELD_SYMBOL = "Symbolname"
KFIELD_KOMMENTAR = "Kommentar"
KFIELD_DATUM = "Erstellungsdatum"
KFIELD_EINHEIT = "Einheit_Laengen"

RECORD_FIELDS_KIES = [
    # (Feldname,             Typ, Stil, Default)
    (KFIELD_ID,                4, 0, ""),
    (KFIELD_ART,               4, 0, "Kiesrigole"),
    (KFIELD_SYSTEM,            4, 0, ""),

    (KFIELD_LAENGE,            5, 3, "0"),
    (KFIELD_BREITE,            5, 3, "0"),
    (KFIELD_HOEHE,             5, 3, "0"),

    (KFIELD_MATERIAL,          4, 0, ""),
    (KFIELD_KOEFF,             5, 3, "0.30"),
    (KFIELD_V_BRUTTO,          5, 3, "0"),
    (KFIELD_V_SPEICHER,        5, 3, "0"),

    (KFIELD_ROHR_DN,           4, 0, ""),
    (KFIELD_ROHR_DA,           5, 3, "0"),
    (KFIELD_ROHR_UK,           5, 3, "0"),
    (KFIELD_ROHR_ACHSE,        5, 3, "0"),
    (KFIELD_ROHR_LAENGE,       5, 3, "0"),
    (KFIELD_ROHR_BRUTTO,       5, 3, "0"),

    (KFIELD_SCHACHT_DN,        4, 0, ""),
    (KFIELD_SCHACHT_ANZ,       1, 0, "0"),
    (KFIELD_SCHACHT_OK,        5, 3, "0"),
    (KFIELD_SCHACHT_UK,        5, 3, "0"),
    (KFIELD_ROHR_VOLUMEN,      5, 3, "0"),

    (KFIELD_HOEHENBEZUG,       4, 0, "OK"),
    (KFIELD_OK,                5, 3, "0"),
    (KFIELD_UK,                5, 3, "0"),

    (KFIELD_BELASTUNG,         4, 0, ""),
    (KFIELD_SYMBOL,            4, 0, ""),
    (KFIELD_KOMMENTAR,         4, 0, ""),
    (KFIELD_DATUM,             4, 0, ""),
    (KFIELD_EINHEIT,           4, 0, "m"),
]

ID_PREFIX_KIES = "KIES-"
ID_DIGITS_KIES = 3     # KIES-001

# ---------------------------------------------------------------------------
# RIGOLE KOMPLEX - Rigole nach einem gezeichneten Polygon (26.08.2026)
# ---------------------------------------------------------------------------
# Dritte Bauart, drittes Werkzeug. Gebaut wird aus denselben Rigolenkoerben
# wie bei der rechteckigen Rigole und in denselben Klassen - nur der Umriss
# kommt aus einem vom Anwender gezeichneten Polygon.
#
# Eigenes Datensatzformat, weil die Kennzahlen andere sind: nicht
# Anzahl x Anzahl, sondern belegte Zellen, Polygonflaeche, Rasterwinkel.
# Auswertungen trennen die Bauarten damit sauber.
ART_POLYGON = "Rigole komplex"

RECORD_NAME_POLY = "DB_Rigole_komplex"

PFIELD_ID = "Rigolen_ID"
PFIELD_ART = "Rigolenart"
PFIELD_SYSTEM = "Systembezeichnung"
PFIELD_KORB_L = "Korb_Laenge"
PFIELD_KORB_B = "Korb_Breite"
PFIELD_KORB_H = "Korb_Hoehe"
PFIELD_ANZ_KOERBE = "Anzahl_Koerbe"        # gesamt, ueber alle Lagen
PFIELD_ANZ_LAGE = "Koerbe_je_Lage"
PFIELD_ANZ_HOEHE = "Anzahl_Hoehe"          # Lagen uebereinander
PFIELD_POLY_FLAECHE = "Polygon_Flaeche"    # m2, gezeichnetes Polygon
PFIELD_BELEGT = "Belegte_Flaeche"          # m2, Summe der Koerbe in der Lage
PFIELD_AUSNUTZUNG = "Ausnutzung"           # Prozent
PFIELD_WINKEL = "Rasterwinkel"             # Grad
PFIELD_ECKEN = "Polygon_Ecken"
PFIELD_UMGRENZUNG = "Umgrenzung"           # Objektname des Polygons
PFIELD_GES_L = "Gesamtlaenge"              # Huellmass in Rasterrichtung
PFIELD_GES_B = "Gesamtbreite"
PFIELD_GES_H = "Gesamthoehe"
PFIELD_VERSCHWEISST = "Verschweisst"
PFIELD_KOEFF = "Speicherkoeffizient"
PFIELD_V_BRUTTO = "Volumen_Brutto"
PFIELD_V_SPEICHER = "Speichervolumen"
PFIELD_HOEHENBEZUG = "Hoehenbezug"
PFIELD_OK = "OK_Rigole"
PFIELD_UK = "UK_Rigole"
PFIELD_BELASTUNG = "Belastungsklasse"
PFIELD_SYMBOL = "Symbolname"
PFIELD_KORB_SYMBOL = "Korb_Symbol"
PFIELD_SCHACHT_DN = "Schacht_DN"
PFIELD_SCHACHT_ANZ = "Schacht_Anzahl"
PFIELD_SCHACHT_OK = "Schacht_OK"
PFIELD_SCHACHT_UK = "Schacht_UK"
PFIELD_KOMMENTAR = "Kommentar"
PFIELD_DATUM = "Erstellungsdatum"
PFIELD_EINHEIT = "Einheit_Laengen"

RECORD_FIELDS_POLY = [
    # (Feldname,             Typ, Stil, Default)
    (PFIELD_ID,                4, 0, ""),
    (PFIELD_ART,               4, 0, "Rigole komplex"),
    (PFIELD_SYSTEM,            4, 0, ""),

    (PFIELD_KORB_L,            5, 3, "0"),
    (PFIELD_KORB_B,            5, 3, "0"),
    (PFIELD_KORB_H,            5, 3, "0"),

    (PFIELD_ANZ_KOERBE,        1, 0, "0"),
    (PFIELD_ANZ_LAGE,          1, 0, "0"),
    (PFIELD_ANZ_HOEHE,         1, 0, "0"),

    (PFIELD_POLY_FLAECHE,      5, 2, "0"),
    (PFIELD_BELEGT,            5, 2, "0"),
    (PFIELD_AUSNUTZUNG,        5, 1, "0"),
    (PFIELD_WINKEL,            5, 2, "0"),
    (PFIELD_ECKEN,             1, 0, "0"),
    (PFIELD_UMGRENZUNG,        4, 0, ""),

    (PFIELD_GES_L,             5, 3, "0"),
    (PFIELD_GES_B,             5, 3, "0"),
    (PFIELD_GES_H,             5, 3, "0"),

    (PFIELD_VERSCHWEISST,      2, 2, "FALSE"),

    (PFIELD_KOEFF,             5, 3, "0.95"),
    (PFIELD_V_BRUTTO,          5, 3, "0"),
    (PFIELD_V_SPEICHER,        5, 3, "0"),

    (PFIELD_HOEHENBEZUG,       4, 0, "OK"),
    (PFIELD_OK,                5, 3, "0"),
    (PFIELD_UK,                5, 3, "0"),

    (PFIELD_BELASTUNG,         4, 0, ""),
    (PFIELD_SYMBOL,            4, 0, ""),
    (PFIELD_KORB_SYMBOL,       4, 0, ""),

    (PFIELD_SCHACHT_DN,        4, 0, ""),
    (PFIELD_SCHACHT_ANZ,       1, 0, "0"),
    (PFIELD_SCHACHT_OK,        5, 3, "0"),
    (PFIELD_SCHACHT_UK,        5, 3, "0"),

    (PFIELD_KOMMENTAR,         4, 0, ""),
    (PFIELD_DATUM,             4, 0, ""),
    (PFIELD_EINHEIT,           4, 0, "m"),
]

ID_PREFIX_POLY = "RIGK-"
ID_DIGITS_POLY = 3     # RIGK-001

# Wie fein der Rasterversatz durchprobiert wird (n x n Startlagen innerhalb
# einer Korbzelle, die beste gewinnt). 4 x 4 = 16 Durchlaeufe: sichtbar mehr
# Koerbe als ohne Suche, und noch schnell genug fuer grosse Flaechen.
RASTER_SUCHSCHRITTE = 4

# Notbremse: mehr Korbplaetze als hier erzeugt kein sinnvolles Symbol mehr
# (und dauert sehr lange). Darueber fragt das Werkzeug nach.
POLY_MAX_KOERBE = 2000

# Ab dieser Spannweite zwischen den beiden aeusseren Schaechten kommt ein
# dritter in der Mitte dazu - dieselbe Regel wie bei der Kiesrigole.
POLY_SCHACHT_MITTE_AB = 20.0

# ---------------------------------------------------------------------------
# Klassen (Layer-unabhaengige Sichtbarkeitssteuerung 2D <-> 3D)
# ---------------------------------------------------------------------------
# Klassenschema des Bueros (Vorgabe des Anwenders, 24.08.2026).
# Vectorworks bildet die Klassenhierarchie ueber den Bindestrich ab - die drei
# Unterklassen erscheinen in der Klassenverwaltung deshalb eingerueckt unter
# der Oberklasse und lassen sich dort gemeinsam ein- und ausschalten.
#
#   PD-EW-RW-Rigole                  <- Hauptgruppe
#   PD-EW-RW-Rigole-2D               <- Aussenumgrenzung und Raster
#   PD-EW-RW-Rigole-3D               <- Symbolinstanzen und Symbolinhalt
#   PD-EW-RW-Rigole-Schacht          <- Kontrollschaechte
#   PD-EW-RW-Rigole-Beschriftung     <- Textobjekt
CLASS_RIGOLE = "PD-EW-RW-Rigole"

CLASS_MAIN = CLASS_RIGOLE                        # aeussere Rigolengruppe
CLASS_2D = CLASS_RIGOLE + "-2D"                  # Aussenumgrenzung und Raster
CLASS_3D = CLASS_RIGOLE + "-3D"                  # Symbolinstanzen
CLASS_SCHACHT = CLASS_RIGOLE + "-Schacht"        # Kontrollschaechte
CLASS_LABEL = CLASS_RIGOLE + "-Beschriftung"     # Beschriftung

# Alle vom Werkzeug angelegten Klassen - in dieser Reihenfolge angelegt,
# damit die Oberklasse vor ihren Unterklassen existiert.
CLASSES_ALL = (CLASS_MAIN, CLASS_2D, CLASS_3D, CLASS_SCHACHT,
               CLASS_LABEL)

# WICHTIG: Die Hauptgruppe liegt bewusst in der OBERKLASSE, nicht in einer
# Unterklasse. Wird in Vectorworks die Klasse einer Gruppe unsichtbar
# geschaltet, verschwindet die gesamte Gruppe samt Inhalt. Nur weil die
# Hauptgruppe in der dauerhaft sichtbaren Oberklasse liegt, lassen sich
# 2D und 3D ueber die Unterklassen getrennt schalten.

# --- Klassen der Kiesrigole ------------------------------------------------
# Vorgabe des Anwenders (24.08.2026): Oberklasse PD-EW-Kiesrigole, das
# Draenrohr in der Unterklasse "Drainrohr", die Schuettung in "Fuellung".
#
#   PD-EW-Kiesrigole                 <- Symbolinstanz der Kiesrigole
#   PD-EW-Kiesrigole-Drainrohr       <- Rohrkoerper und Rohrkontur im Plan
#   PD-EW-Kiesrigole-Füllung         <- Schuettkoerper und Umgrenzung im Plan
#   PD-EW-Kiesrigole-Schacht         <- Kontrollschaechte
#   PD-EW-Kiesrigole-Beschriftung    <- Textobjekt
CLASS_KIES = "PD-EW-Kiesrigole"
CLASS_KIES_ROHR = CLASS_KIES + "-Drainrohr"
CLASS_KIES_FUELLUNG = CLASS_KIES + "-Füllung"
CLASS_KIES_SCHACHT = CLASS_KIES + "-Schacht"
CLASS_KIES_LABEL = CLASS_KIES + "-Beschriftung"

CLASSES_KIES = (CLASS_KIES, CLASS_KIES_ROHR, CLASS_KIES_FUELLUNG,
                CLASS_KIES_SCHACHT, CLASS_KIES_LABEL)

# Wie bei der Koerbe-Rigole liegt die Symbolinstanz in der OBERKLASSE, damit
# sich Rohr und Fuellung getrennt schalten lassen, ohne die ganze Rigole zu
# verlieren.

# Rasterlinien der 2D-Darstellung: ab dieser Anzahl wird das Raster
# weggelassen und nur die Aussenumgrenzung gezeichnet (Lesbarkeit im Plan).
GRID_MAX_LINES = 400

# ---------------------------------------------------------------------------
# Objektnamen / Gruppenbezeichner
# ---------------------------------------------------------------------------
GROUP_NAME_TEMPLATE = "Rigole {rigole_id}"      # Name der Hauptgruppe
GROUP_NAME_TEMPLATE_KIES = "Kiesrigole {rigole_id}"

# Die Beschriftung ist ein gewoehnliches Textobjekt OHNE Datensatz - sonst
# taucht sie in Datenbanktabellen als zweite Zeile auf. Damit der Modus
# "Vorhandenes bearbeiten" sie trotzdem wiederfindet, bekommt sie einen
# Namen; Namen sind im Dokument eindeutig.
LABEL_NAME_TEMPLATE = "Rigole {rigole_id} Text"
LABEL_NAME_TEMPLATE_KIES = "Kiesrigole {rigole_id} Text"

# Rigole komplex. Zusaetzlich bekommt das gezeichnete Umgrenzungspolygon
# einen Namen - nur so findet das Werkzeug es beim Bearbeiten wieder, ohne
# saemtliche Eckpunkte in den Datensatz schreiben zu muessen. Hat das
# Polygon schon einen Namen, bleibt dieser stehen und wird gespeichert.
GROUP_NAME_TEMPLATE_POLY = "Rigole komplex {rigole_id}"
LABEL_NAME_TEMPLATE_POLY = "Rigole komplex {rigole_id} Text"
UMGRENZUNG_NAME_TEMPLATE = "Rigole komplex {rigole_id} Umgrenzung"

# ---------------------------------------------------------------------------
# Modusleiste der Werkzeuge
# ---------------------------------------------------------------------------
# ACHTUNG (25.08.2026): Der Plug-in-Manager hat KEINEN Bereich "Modusleiste".
# Eine Modusleiste kann ein Skriptwerkzeug nur dann anlegen, wenn es
# EREIGNISGESTEUERT ist (vs.AddRadioMode im Init-Ereignis) - und das laesst
# sich laut Vectorworks-Entwicklerreferenz (Anmerkung bei vstGetEventInfo)
# ueber die Oberflaeche nicht einschalten.
#
# Deshalb erkennen die Werkzeuge den Modus selbst: ein Klick auf eine
# vorhandene Rigole heisst bearbeiten, ein Klick ins Leere heisst neu
# anlegen. Siehe rigole_vw/bearbeiten.py.
#
# Die folgenden Konstanten bleiben bestehen: sollte das Werkzeug spaeter
# doch einmal ereignisgesteuert laufen, wird die Radiogruppe ohne weitere
# Aenderung gelesen (vwutils.mode_value). Ohne Modusleiste liefert
# vstGetModeValue nichts - dann gilt MODE_NEU und damit die automatische
# Erkennung.
MODE_GROUP = 1
MODE_NEU = 1
MODE_BEARBEITEN = 2

# ---------------------------------------------------------------------------
# Beschriftung
# ---------------------------------------------------------------------------
TEXT_SIZE = 8.0                 # Papier-Punkt; auch auf üblichen Planausdrucken lesbar
TEXT_OFFSET_X = 0.50            # m, rechts von der rechten Rigolenkante
TEXT_OFFSET_Y = 0.50            # m, oberhalb der oberen Rigolenkante
TEXT_JUST_LEFT = 1              # vs.TextJust: 1 = linksbuendig
TEXT_VERT_TOP = 1               # vs.TextVerticalAlign: 1 = oben
TEXT_STYLE_NAME = ""            # "" = kein Textstil, Dokumentstandard verwenden

# ---------------------------------------------------------------------------
# Toleranzen / Grenzen
# ---------------------------------------------------------------------------
LENGTH_EPS = 1.0e-6             # m, Rechen-Toleranz fuer Laengenvergleiche
MIN_DIMENSION = 1.0e-4          # m, kleinste zulaessige Korbabmessung (0.1 mm)
MAX_DIMENSION = 100.0           # m, Plausibilitaetsgrenze je Einzelmass
MAX_BASKETS_TOTAL = 5000        # Sicherheitsgrenze gegen versehentliche Massen
WARN_BASKETS_TOTAL = 500        # ab hier Rueckfrage / Fortschrittsanzeige
MIN_ELEVATION = -500.0          # m, Plausibilitaetsgrenze Hoehenlage
MAX_ELEVATION = 5000.0          # m

# ---------------------------------------------------------------------------
# Persistenz der letzten Einstellungen (vs.SetSavedSetting / vs.GetSavedSetting)
# ---------------------------------------------------------------------------
SETTINGS_CATEGORY = "Rigole_Tool"

# Diese Schluessel werden gespeichert und beim naechsten Aufruf vorbelegt.
# Bewusst NICHT enthalten: Rigolen_ID, Einfuegepunkt, Kommentar.
#
# ACHTUNG: Die Namen muessen EXAKT den Schluesseln entsprechen, die der
# Dialog liefert. In der ersten Fassung standen hier "custom_length" und
# "storage_coefficient", der Dialog liefert aber "basket_length" und
# "storage_percent" - dadurch wurden diese Werte stillschweigend nicht
# gespeichert (aufgefallen in Pruefbericht D, zweiter Lauf).
PERSISTED_KEYS = [
    "rigole_type", "system_name",
    "basket_key", "basket_length", "basket_width", "basket_height",
    "basket_swapped",
    "count_width", "count_height", "length_mode",
    "count_length", "target_length", "rounding",
    "welded", "storage_percent", "load_class",
    "height_mode", "height_value", "use_layer_elevation",
    "draw_2d", "draw_3d",
    "mit_schacht", "schacht_dn", "schacht_ok",
    "create_label", "label_offset_x", "label_offset_y", "label_fields",
    # Kiesrigole
    "kies_laenge", "kies_breite", "kies_hoehe",
    "kies_material", "kies_rohr_dn", "kies_rohr_uk",
    "kies_mit_schacht", "kies_schacht_dn", "kies_schacht_ok",
]

# Eigener Schluesselsatz fuer "Rigole komplex": dort gibt es keine
# Anzahl in Laengs- und Querrichtung, dafuer die Rastersuche.
PERSISTED_KEYS_POLY = [
    "rigole_type", "system_name",
    "basket_key", "basket_length", "basket_width", "basket_height",
    "basket_swapped", "count_height",
    "raster_modus", "raster_winkel", "raster_suche",
    "welded", "storage_percent", "load_class",
    "height_mode", "height_value", "use_layer_elevation",
    "draw_2d", "draw_3d", "zeige_zellen",
    "mit_schacht", "schacht_dn", "schacht_ok",
    "create_label", "label_offset_x", "label_offset_y", "label_fields",
]

# Zulaessige Abweichung zwischen den eingegebenen Korbmassen und den
# tatsaechlichen Abmessungen der gewaehlten Symboldefinition (in Metern).
# Darueber hinaus fragt das Werkzeug nach, bevor es baut.
SYMBOL_TOLERANZ = 0.005

# ---------------------------------------------------------------------------
# Beschriftungsinhalte (Checkboxen im Dialog)
# Reihenfolge = Reihenfolge der Zeilen in der Beschriftung.
# ---------------------------------------------------------------------------
LABEL_FIELDS = [
    # (Schluessel,        Dialogtext,             Default an/aus)
    ("id",                "Rigolen-ID",            True),
    ("art",               "Rigolenart",            True),
    ("system",            "Systembezeichnung",     True),
    ("gesamt",            "Gesamtmasse",           True),
    ("korb",              "Korbabmessungen",       True),
    ("anordnung",         "Anzahl Koerbe",         True),
    # Nur fuer "Rigole komplex": Polygonflaeche und Ausnutzung
    ("flaeche",           "Flaeche und Ausnutzung", True),
    ("verschweisst",      "Verschweisst",          False),
    ("koeffizient",       "Speicherkoeffizient",   True),
    ("speichervolumen",   "Speichervolumen",       True),
    ("ok",                "Oberkante",             True),
    ("uk",                "Unterkante",            True),
    ("belastung",         "Belastungsklasse",      True),
    # Nur fuer die Kiesrigole - bei den Koerben bleiben diese Zeilen leer
    # und werden dann gar nicht erst ausgegeben.
    ("material",          "Material (Kiesrigole)", True),
    ("draenrohr",         "Draenrohr (Kiesrigole)", True),
    ("schacht",           "Schaechte",             True),
]

DEFAULT_LABEL_FIELDS = dict((k, d) for (k, _t, d) in LABEL_FIELDS)

# ---------------------------------------------------------------------------
# Modi
# ---------------------------------------------------------------------------
LENGTH_MODE_COUNT = "count"        # Modus A - Anzahl Koerbe hintereinander
LENGTH_MODE_TOTAL = "total"        # Modus B - gewuenschte Gesamtlaenge

HEIGHT_MODE_OK = "OK"              # Oberkante bekannt
HEIGHT_MODE_UK = "UK"              # Unterkante bekannt

ROUND_UP = "up"
ROUND_DOWN = "down"
ROUND_NEAREST = "nearest"
