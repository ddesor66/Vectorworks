# -*- coding: utf-8 -*-
"""
Kennungen der Dialog-Steuerelemente.

WARUM EINE EIGENE DATEI
-----------------------
Am 24.08.2026 hat ein Zahlendreher die halbe Anordnungs-Gruppe verschwinden
lassen: Ein neues Ankreuzfeld bekam die Kennung 30 - dieselbe, die schon der
Gruppenrahmen "Anordnung der Koerbe" trug. Vectorworks meldet so etwas nicht,
das Steuerelement ist einfach weg.

Weil diese Datei kein "import vs" enthaelt, kann die Testsuite sie laden und
die Eindeutigkeit aller Kennungen bei jedem Testlauf pruefen
(test_dialog_ids_are_unique). Der Fehler kann sich damit nicht wiederholen.

NUMMERNKREISE
-------------
    1, 2, 3    von Vectorworks vergeben (OK, Abbrechen, Hilfe)
    100-109    Bereich A - Rigolenkoerper (Hersteller/System)
    110-129    Bereich B - Abmessungen Rigolenkoerper
    130-149    Bereich C - Anordnung der Koerbe
    150-159    Bereich D - Eigenschaften
    160-169    Bereich E - Hoehenlage
    170-179    Bereich F - Darstellung
    180-199    Bereich G - Beschriftung
    200-229    Bereich K - Kiesrigole
    230-249    Bereich S - Kontrollschaechte der Koerbe-Rigole
    300-309    Ergebnisanzeige
    400-449    Ankreuzfelder der Beschriftungsinhalte

Beim Ergaenzen bitte innerhalb des jeweiligen Kreises bleiben - dort ist
reichlich Platz gelassen.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

# --- Von Vectorworks vergeben ---------------------------------------------
BTN_OK = 1
BTN_ABBRECHEN = 2
BTN_HILFE = 3
RESERVIERT = (BTN_OK, BTN_ABBRECHEN, BTN_HILFE)

# --- Bereich A - Rigolenkoerper -------------------------------------------
# Bis 0.16.0 hiess der Bereich "Rigolenart" und trug ein Aufklappmenue mit
# den Bauarten. Seit 0.17.0 steht hier die Auswahl HERSTELLER / SYSTEM
# (T_KORBTYP / P_KORBTYP aus Bereich B) samt Bezeichnung.
#
# T_ART und P_ART sind damit frei geworden. Sie bleiben eingetragen, damit
# die Nummern nicht versehentlich neu vergeben werden, und dienen jetzt als
# Hinweiszeile zum gewaehlten System.
G_ART = 100
T_ART = 101                    # frei - siehe T_SYSTEM_INFO
P_ART = 102                    # frei
T_SYSTEM = 103
E_SYSTEM = 104
T_SYSTEM_INFO = 105            # Hinweistext zum gewaehlten Hersteller/System

# --- Bereich B - Abmessungen Rigolenkoerper -------------------------------
G_KORB = 110
T_KORBTYP = 111
P_KORBTYP = 112
T_KORB_L = 113
E_KORB_L = 114
T_KORB_B = 115
E_KORB_B = 116
T_KORB_H = 117
E_KORB_H = 118
C_SWAP = 119                   # Koerbe quer stellen: Laenge <-> Breite
T_SYMBOL_INFO = 120            # Anzeige: welches Symbol wird verwendet

# --- Bereich C - Anordnung der Koerbe -------------------------------------
G_ANORDNUNG = 130
T_ANZ_B = 131
E_ANZ_B = 132
T_ANZ_H = 133
E_ANZ_H = 134
T_MODUS = 135
P_MODUS = 136
T_ANZ_L = 137
E_ANZ_L = 138
T_ZIEL_L = 139
E_ZIEL_L = 140
T_RUNDUNG = 141
P_RUNDUNG = 142

# --- Bereich D - Eigenschaften --------------------------------------------
G_EIGENSCHAFTEN = 150
C_VERSCHWEISST = 151
T_KOEFF = 152
E_KOEFF = 153
T_KLASSE = 154
P_KLASSE = 155

# --- Bereich E - Hoehenlage -----------------------------------------------
G_HOEHEN = 160
T_HBEZUG = 161
P_HBEZUG = 162
T_HWERT = 163
E_HWERT = 164
C_EBENENHOEHE = 165

# --- Bereich F - Darstellung ----------------------------------------------
G_DARSTELLUNG = 170
C_2D = 171
C_3D = 172

# --- Bereich G - Beschriftung ---------------------------------------------
G_BESCHRIFTUNG = 180
C_LABEL = 181
T_LABEL_OFF = 182
E_LOFF_X = 183
E_LOFF_Y = 184
T_KOMMENTAR = 185
E_KOMMENTAR = 186

# --- Bereich K - Kiesrigole (200-229) --------------------------------------
G_KIES = 200
T_KIES_L = 201
E_KIES_L = 202
T_KIES_B = 203
E_KIES_B = 204
T_KIES_H = 205
E_KIES_H = 206
T_KIES_MATERIAL = 207
P_KIES_MATERIAL = 208
T_KIES_ROHR = 209
P_KIES_ROHR = 210
T_KIES_UK = 211                # Abstand Rohrunterkante zur Sohle
E_KIES_UK = 212
T_KIES_INFO = 213
C_KIES_SCHACHT = 214           # Kontrollschaechte erzeugen
T_KIES_SCHACHT_DN = 215
P_KIES_SCHACHT_DN = 216
T_KIES_SCHACHT_OK = 217
E_KIES_SCHACHT_OK = 218
T_KIES_SCHACHT_INFO = 219
G_KIES_ROHR = 220             # Gruppenrahmen im Werkzeug Kiesrigole
G_KIES_SCHACHT = 221
G_KIES_SPEICHER = 222

# --- Bereich S - Kontrollschaechte der Koerbe-Rigole (230-249) -------------
G_SCHACHT = 230
C_SCHACHT = 231
T_SCHACHT_DN = 232
P_SCHACHT_DN = 233
T_SCHACHT_OK = 234
E_SCHACHT_OK = 235
T_SCHACHT_INFO = 236

# --- Bereich P - Rigole komplex, Polygon (250-279) -------------------------
G_POLY = 250
T_POLY_INFO = 251              # Kennzahlen des angeklickten Polygons
T_RASTER = 252                 # Ausrichtung des Rasters
P_RASTER = 253
T_WINKEL = 254
E_WINKEL = 255
T_SUCHE = 256                  # Feinheit der Rasterverschiebung
P_SUCHE = 257
C_ZELLEN = 258                 # jeden Korbplatz im Plan zeichnen
T_POLY_HINWEIS = 259

# --- Ergebnisanzeige -------------------------------------------------------
G_ERGEBNIS = 300
R_GESAMT = 301
R_ANZAHL = 302
R_VOLUMEN = 303
R_SPEICHER = 304
R_HOEHEN = 305
R_HINWEIS = 306
R_FLAECHE = 307
R_RASTER = 308

# --- Ankreuzfelder der Beschriftungsinhalte -------------------------------
# LABEL_CHECK_BASE + 0 ... + (Anzahl der Beschriftungsfelder - 1)
LABEL_CHECK_BASE = 400
LABEL_CHECK_MAX = 449          # Ende des reservierten Kreises


def einzelne_ids():
    """
    Alle fest vergebenen Kennungen als dict {Name: Wert}.
    Die Ankreuzfelder der Beschriftung sind hier NICHT enthalten - die
    liefert label_check_ids().
    """
    ausnahmen = ("RESERVIERT", "LABEL_CHECK_BASE", "LABEL_CHECK_MAX",
                 "BTN_OK", "BTN_ABBRECHEN", "BTN_HILFE")
    ergebnis = {}
    for name, wert in globals().items():
        if name.startswith("_") or name in ausnahmen:
            continue
        if isinstance(wert, int) and name.isupper():
            ergebnis[name] = wert
    return ergebnis


def label_check_ids(anzahl):
    """Kennungen der Beschriftungs-Ankreuzfelder."""
    return [LABEL_CHECK_BASE + i for i in range(int(anzahl))]
