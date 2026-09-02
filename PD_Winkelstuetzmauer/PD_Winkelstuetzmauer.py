# -*- coding: utf-8 -*-
"""
==============================================================================
 PD Winkelstuetzmauer  -  Abwicklung & Aufsicht
 Vectorworks 2026 / Python 3  -  Menuebefehl (Plug-in Menu Command)
==============================================================================

 Zeichnet aus drei Referenzlinien (Unterkante, Oberkante, Aufsichtslinie)
 die Abwicklung und die Aufsicht einer Winkelstuetzmauer aus Fertigteil-
 Mauerwinkeln, verteilt die Elemente hoehen- und laengenoptimiert,
 nummeriert und beschriftet sie, legt sie hoehenabhaengig auf Klassen und
 erzeugt eine Summenliste.

 Autor : erstellt fuer PD  -  Version 1.10.1
 Lizenz: Gemeinsame PD-Vectorworks-Netzwerkfreigabe
==============================================================================
"""

import vs
import os
import json
import math
import datetime
import uuid
import traceback
import struct
import zlib
import binascii
import sys

_pd_plugin_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pd_plugin_root not in sys.path:
    sys.path.insert(0, _pd_plugin_root)
from pd_plan_frame import PlanFrame, wall_frame  # noqa: E402
import pd_chamfer  # noqa: E402
from PD_ToolsPD.ddvw.core import wall_reference  # noqa: E402

# ---------------------------------------------------------------------------
# Konstanten
# ---------------------------------------------------------------------------

VERSION      = '1.10.1'
TOOL_TITLE   = 'PD Winkelstuetzmauer'
MANUFACTURER = 'manufactured by Dirk D.'


def _dialog_title(title):
    return '%s | v%s | %s' % (str(title), VERSION, MANUFACTURER)

# --------------------------------------------------------------------------
# Lizenzbindung erfolgt zentral ueber PD_ToolsPD.

# Auf True setzen, um nach jedem Arbeitsschritt eine Meldung anzuzeigen.
# Damit laesst sich eingrenzen, an welcher Stelle das Skript stehen bleibt.
DEBUG = False

MAX_ITER = 200000            # Sicherheitsgrenze fuer Objektdurchlaeufe
CHAMFER_CM = 0.5             # 5 x 5 mm an jeder Kante aller 3D-Koerper


def _dbg(text):
    if DEBUG:
        try:
            vs.AlrtDialog('Kontrollpunkt: ' + text)
        except Exception:
            pass

REC_NAME     = 'PD_MW_Steuerung'      # Datensatzformat an der Zeichnungsgruppe
REC_FIELD    = 'Daten'                # JSON-Feld mit allen Parametern
SETTINGS_FILE = 'PD_MW_Einstellungen.json'
REGISTRY_FILE = 'PD_MW_Mauern.json'

# Regel-Hoehenkatalog laut Herstellerliste (Hoehe cm ; Fusslaenge cm ; Farbe)
DEFAULT_CATALOG = [
    (40,  30,  '#78D66F'),
    (55,  30,  '#6FD686'),
    (60,  40,  '#6FD6A6'),
    (80,  50,  '#6FD6C5'),
    (105, 60,  '#6FC8D6'),
    (130, 70,  '#6FA9D6'),
    (155, 85,  '#6F89D6'),
    (180, 100, '#756FD6'),
    (205, 110, '#946FD6'),
    (230, 125, '#B46FD6'),
    (255, 150, '#D36FD6'),
    (280, 150, '#D66FBA'),
    (305, 160, '#D66F9B'),
    (330, 180, '#D66F7B'),
    (355, 190, '#D6836F'),
    (380, 200, '#D6A26F'),
    (405, 220, '#D6C26F'),
]

# Unarmierte Winkelsteine (Hoehe cm ; Fusslaenge cm ; Farbe)
# Steinlaenge durchgehend 40 cm -> Regelbreite 40 cm
DEFAULT_CATALOG_UN = [
    (30, 20, '#A8D5A2'),
    (40, 30, '#6BB7C4'),
    (50, 30, '#5B8FD4'),
    (60, 40, '#A96FC9'),
    (80, 40, '#E0705F'),
]

FARB_MODI = ['Manuelle Tabellenfarben',
             'Verlauf gruen (niedrig) - rot (hoch)',
             'Verlauf hell - dunkel (einfarbig)',
             'Graustufen hell - dunkel']

STEIN_TYPEN = ['Winkelsteine armiert (55 - 305 cm)',
               'Winkelsteine unarmiert (30 - 80 cm)',
               'Gabionenwand']
TYP_GABIONE = 2

# Erforderliche Gabionenbreite, von oben nach unten gemessen:
# (Tiefe unter Wandoberkante in cm, Breite in cm)
GAB_BREITEN = [(0, 50), (50, 100), (100, 150), (150, 200), (200, 250),
               (250, 250), (300, 300), (350, 350), (400, 400), (450, 450),
               (500, 500), (550, 550)]
GAB_FUND_UEBERSTAND_CM = 15.0
GAB_FUND_TIEFE_CM = 80.0
WINKEL_FUND_UEBERSTAND_CM = 20.0
WINKEL_FUND_TIEFE_CM = 80.0
# Qualitative, kontrastreiche Palette. Anders als ein Verlauf bleiben auch
# benachbarte Gabionenbreiten eindeutig voneinander unterscheidbar.
GAB_TYP_FARBEN = (
    (31, 119, 180), (255, 127, 14), (44, 160, 44), (214, 39, 40),
    (148, 103, 189), (140, 86, 75), (227, 119, 194), (127, 127, 127),
    (188, 189, 34), (23, 190, 207), (57, 59, 121), (99, 121, 57),
)
GAB_STANDARD_BREITEN = tuple(dict.fromkeys(int(b) for _t, b in GAB_BREITEN))
DEFAULT_GAB_COLORS = dict(
    (str(b), '#%02X%02X%02X' % GAB_TYP_FARBEN[i])
    for i, b in enumerate(GAB_STANDARD_BREITEN))
DEFAULT_FUNDAMENT_FARBE = '#B7B7B7'
REGELBREITE_UN = 40.0


DEFAULTS = {
    'stein_typ':     0,        # 0 = armiert, 1 = unarmiert, 2 = Gabionenwand
    # --- Gabionenwand (Masse in m) ---
    'gab_laenge':    2.00,     # Regellaenge einer Gabione
    'gab_lage':      0.50,     # Hoehe einer Gabionenlage
    'gab_einbinde':  0.30,     # Einbindetiefe unter der Unterkante
    'gab_ueber':     0.20,     # Ueberstand ueber dem Gelaende
    'gab_staffel':   0.50,     # Mindestwert der Abstaffelung in der Oberkante
    'gab_lage_min':  0.25,     # unterste Lage darf hierauf reduziert werden,
                               # wenn die Einbindung sonst zu tief wuerde
                               # (0 = keine Reduzierung)
    'gab_breiten':   ('50\n100\n150\n200\n250\n250\n300\n350\n400\n'
                      '450\n500\n550'),
    'gab_colors':    dict(DEFAULT_GAB_COLORS),
    'gab_prefix':    'PD-MA-GAB-',
    'gab_ebene_name': 'Gabione',
    'gab_ebene_massstab': 50.0,
    'gab_fund_tiefe': 80.0,  # cm  Fundamentsohle unter UK Gelaende
    'gab_fund_ueberstand': 15.0,  # cm  Fundamentueberstand auf allen Seiten
    'schnitt_station': 5.00,   # m  Station fuer den Einzelschnitt
    'unit':          'm',      # Zeichnungseinheit: 'm', 'cm', 'mm'
    'ueber_ok':      10.0,     # cm  Mindestueberstand ueber Oberkante
    'unter_uk':      15.0,     # cm  Mindesttiefe unter Unterkante
    'fund_ueberstand': 20.0,    # cm  Fundament vor/hinter dem Fuss
    'fund_tiefe':    80.0,      # cm  Fundamentsohle unter UK Gelaende
    'winkel_fuss_staerke': 15.0, # cm  Plattendicke des Winkelsteinfusses
    'breite_mode':   0,        # 0 = 50 cm, 1 = 100 cm, 2 = frei
    'breite_frei':   75.0,     # cm
    'pass_min':      15.0,     # cm  Mindestbreite eines Passstuecks
    'eck_schenkel':  50.0,     # cm  Schenkellaenge je Seite eines Eckelements
    'ecke_abstufen': False,    # Eckschenkel im Knickpunkt abstufen (je eigene Hoehe)
    'stufe_min':     0.0,      # cm  Mindesthoehe einer Abtreppung der Oberkante
                               #     0 = jede Aenderung wird abgetreppt
    'pass_lage':     0,        # 0 = Ende, 1 = Anfang, 2 = Mitte
    'hoehen_mode':   0,        # 0 = Kopf an Oberkante, 1 = Fuss auf Unterkante,
                               # 2 = Ausgleich, 3 = Oberkante parallel
    'ok_abstand':    10.0,     # cm  Parallelabstand der Elementoberkante zur Oberkante
    'einzelliste':   True,     # Tabelle mit jedem einzelnen Mauerwinkel
    'dicke_mode':    2,        # 0=10, 1=12, 2=15, 3=20, 4=frei  (cm)
    'dicke_frei':    18.0,     # cm
    'seite':         0,        # 0 = links der Linienrichtung, 1 = rechts
    'aufsicht':      True,
    'draw_3d':       True,
    'aufsicht_umkehren': False,
    'ref_aktiv':     False,
    'ref_hoehe':     100.00,   # m  Bezugskote fuer y = 0 der Abwicklung
    'ref_liste':     [],       # zuletzt benutzte Bezugshoehen (Auswahlfeld)
    'ref_y':         0.0,      # Zeichnungshoehe, auf der die Bezugskote liegt
    'font':          'Arial',
    'font_size':     8.0,      # pt
    'txt_rot':       True,     # Hoehenbeschriftung Abwicklung um 90 Grad drehen
    'ws_tabelle':    True,     # Summenliste als Arbeitsblatt
    'zeichnungs_tabelle': True,# Summenliste zusaetzlich als Zeichnungstext
    'prefix':        'PD-MWL-',
    'winkel_prefix': 'PD-MWL-',
    'winkel_ebene_name': 'Winkelstützmauer',
    'winkel_ebene_massstab': 25.0,
    'toleranz':      5.0,      # cm  zulaessige Laengendifferenz Aufsicht/Abwicklung
    'heights':       [c[0] for c in DEFAULT_CATALOG],
    'feet':          dict((str(int(h)), float(f)) for h, f, _c in DEFAULT_CATALOG),
    'colors':        dict((str(int(h)), c) for h, _f, c in DEFAULT_CATALOG),
    'catalog_armiert': [[h, f, c, 'Regelelement']
                        for h, f, c in DEFAULT_CATALOG],
    'catalog_unarmiert': [[h, f, c, 'Regelelement']
                          for h, f, c in DEFAULT_CATALOG_UN],
    'catalog_armiert_custom': False,
    'catalog_unarmiert_custom': False,
    'gab_catalog_custom': False,
    'fundament_farbe': DEFAULT_FUNDAMENT_FARBE,
    'farben_neu':    False,    # vorhandene Klassenfarben ueberschreiben
    'farb_modus':    1,        # 0 = Katalog, 1..3 = abgestufter Verlauf
    'transparenz':   50.0,     # %  Transparenz der Mauerwinkel-Fuellung
    'bemassung':     True,     # Mauer in Abwicklung und Aufsicht bemassen
    'dim_abstand':   60.0,     # cm  Abstand der Masslinie vom Objekt
    'ebene_aktiv':   True,     # auf eigener Konstruktionsebene zeichnen
    'ebene_name':    'Winkelstützmauer',
    'ebene_massstab': 25.0,    # Massstab dieser Ebene (1:25)
    'fuss_zeichnen': True,     # Fusslaenge in der Aufsicht gestrichelt darstellen
    'fuss_ls':       'ISO-02 Strich',   # Name des Linientyps fuer den Fuss
}

# ---------------------------------------------------------------------------
# Hilfsfunktionen: Dateiablage / Einstellungen / Katalog
# ---------------------------------------------------------------------------
















def lizenz_pruefen():
    """Gemeinsame Vectorworks-Netzwerkfreigabe statt Arbeitsplatzbindung."""
    from PD_ToolsPD import authorized
    return authorized()


def settings_dir():
    """Anwenderordner fuer Einstellungen, Registry und Lizenz."""
    for fid in (-2, 1, 12, 0):
        try:
            p = vs.GetFolderPath(fid)
            if isinstance(p, (list, tuple)):
                p = p[0]
            if p and os.path.isdir(p):
                target = os.path.join(p, 'PD_Winkelstuetzmauer')
                if not os.path.isdir(target):
                    os.makedirs(target)
                return target
        except Exception:
            pass
    target = os.path.join(os.path.expanduser('~'), 'PD_Winkelstuetzmauer')
    try:
        if not os.path.isdir(target):
            os.makedirs(target)
    except Exception:
        return os.path.expanduser('~')
    return target


def _png_chunk(art, daten):
    """PNG-Chunk mit Laenge und CRC erzeugen."""
    inhalt = art + daten
    return (struct.pack('>I', len(daten)) + inhalt +
            struct.pack('>I', binascii.crc32(inhalt) & 0xffffffff))


def _png_logo_schwarz_80(quelle, ziel):
    """PNG-Logo rein schwarz mit 80 Prozent Deckkraft schreiben.

    Verwendet nur die Python-Standardbibliothek, damit keine zusaetzliche
    Bildbibliothek in Vectorworks installiert sein muss. Weisse Hintergruende
    werden transparent; graue Kantenglaettung bleibt als Teildeckkraft
    erhalten. Unterstuetzt die ueblichen 8-Bit-PNG-Farbtypen ohne Interlace.
    """
    try:
        if (os.path.isfile(ziel) and
                os.path.getmtime(ziel) >= os.path.getmtime(quelle) and
                os.path.getsize(ziel) > 32):
            return ziel
        with open(quelle, 'rb') as fp:
            roh = fp.read()
        if roh[:8] != b'\x89PNG\r\n\x1a\n':
            return ''

        pos, ihdr, idat = 8, None, []
        palette, transparenz = None, b''
        while pos + 12 <= len(roh):
            laenge = struct.unpack('>I', roh[pos:pos + 4])[0]
            art = roh[pos + 4:pos + 8]
            ende = pos + 12 + laenge
            if ende > len(roh):
                return ''
            daten = roh[pos + 8:pos + 8 + laenge]
            if art == b'IHDR':
                ihdr = daten
            elif art == b'PLTE':
                palette = [tuple(daten[i:i + 3])
                           for i in range(0, len(daten) - 2, 3)]
            elif art == b'tRNS':
                transparenz = daten
            elif art == b'IDAT':
                idat.append(daten)
            elif art == b'IEND':
                break
            pos = ende
        if ihdr is None or len(ihdr) != 13 or not idat:
            return ''
        breite, hoehe, bit, farbtyp, komp, filt, interlace = struct.unpack(
            '>IIBBBBB', ihdr)
        if (bit != 8 or interlace != 0 or komp != 0 or filt != 0 or
                farbtyp not in (0, 2, 3, 4, 6) or breite < 1 or hoehe < 1 or
                breite * hoehe > 20000000):
            return ''
        kanaele = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[farbtyp]
        schritt = breite * kanaele
        gepackt = zlib.decompress(b''.join(idat))
        if len(gepackt) != (schritt + 1) * hoehe:
            return ''

        def paeth(a, b, c):
            p = a + b - c
            pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
            return a if pa <= pb and pa <= pc else (b if pb <= pc else c)

        zeilen, vorher, offset = [], bytearray(schritt), 0
        for _y in range(hoehe):
            filterart = gepackt[offset]
            scan = bytearray(gepackt[offset + 1:offset + 1 + schritt])
            offset += schritt + 1
            for x in range(schritt):
                links = scan[x - kanaele] if x >= kanaele else 0
                oben = vorher[x]
                oben_links = vorher[x - kanaele] if x >= kanaele else 0
                if filterart == 1:
                    scan[x] = (scan[x] + links) & 255
                elif filterart == 2:
                    scan[x] = (scan[x] + oben) & 255
                elif filterart == 3:
                    scan[x] = (scan[x] + ((links + oben) // 2)) & 255
                elif filterart == 4:
                    scan[x] = (scan[x] + paeth(
                        links, oben, oben_links)) & 255
                elif filterart != 0:
                    return ''
            zeilen.append(scan)
            vorher = scan

        ausgabe = []
        for scan in zeilen:
            rgba = bytearray()
            for x in range(breite):
                i = x * kanaele
                if farbtyp == 0:
                    r = g = b = scan[i]
                    a = 255
                elif farbtyp == 2:
                    r, g, b = scan[i:i + 3]
                    a = 255
                elif farbtyp == 3:
                    idx = scan[i]
                    if palette is None or idx >= len(palette):
                        return ''
                    r, g, b = palette[idx]
                    a = transparenz[idx] if idx < len(transparenz) else 255
                elif farbtyp == 4:
                    r = g = b = scan[i]
                    a = scan[i + 1]
                else:
                    r, g, b, a = scan[i:i + 4]
                # Deckung aus der Dunkelheit ableiten. Damit wird sowohl ein
                # transparentes als auch ein weisses Ausgangsbild sauber.
                helligkeit = (299 * r + 587 * g + 114 * b) // 1000
                alpha = int(round(a * (255 - helligkeit) / 255.0 * 0.80))
                rgba.extend((0, 0, 0, max(0, min(255, alpha))))
            ausgabe.append(b'\x00' + bytes(rgba))

        png = (b'\x89PNG\r\n\x1a\n' +
               _png_chunk(b'IHDR', struct.pack(
                   '>IIBBBBB', breite, hoehe, 8, 6, 0, 0, 0)) +
               _png_chunk(b'IDAT', zlib.compress(b''.join(ausgabe), 9)) +
               _png_chunk(b'IEND', b''))
        tmp = ziel + '.tmp'
        with open(tmp, 'wb') as fp:
            fp.write(png)
        os.replace(tmp, ziel)
        return ziel
    except Exception:
        try:
            if os.path.isfile(ziel + '.tmp'):
                os.remove(ziel + '.tmp')
        except Exception:
            pass
        return ''


def logo_pfad():
    """Vorhandenes plan-d-Logo als schwarze 80-Prozent-Variante finden."""
    dateinamen = (
        'PD_MW_Logo.png', 'PD_MW_Logo_80.png', 'PD_MW_Logo_75.png',
        'Logo_plan°d_Landschaftsarchitektur+Infrastrukturplanung_512x266px.png',
    )
    ordner = []
    try:
        ordner.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:
        pass
    try:
        ordner.append(settings_dir())
    except Exception:
        pass
    ordner.append(r'H:\Logo plan°d\02 Raster\PNG')
    for basis in ordner:
        for name in dateinamen:
            pfad = os.path.join(basis, name)
            try:
                if os.path.isfile(pfad):
                    ziel = os.path.join(settings_dir(), 'PD_MW_Logo_80.png')
                    return _png_logo_schwarz_80(pfad, ziel) or pfad
            except Exception:
                pass
    return ''


SETTINGS_VERSION = 5


def load_settings():
    s = dict(DEFAULTS)
    try:
        f = os.path.join(settings_dir(), SETTINGS_FILE)
        if os.path.isfile(f):
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            for k in s:
                if k in data:
                    s[k] = data[k]
            if int(data.get('ver', 0)) < 3:
                # Bis Version 2 gab es nur einen gemeinsamen Ebenen-/Praefix-
                # Zustand. Den zuletzt aktiven Typ einmalig in seinen eigenen
                # Bereich uebernehmen, ohne den anderen Typ zu verunreinigen.
                if int(data.get('stein_typ', 0)) == TYP_GABIONE:
                    s['gab_ebene_name'] = data.get('ebene_name', 'Gabione')
                    s['gab_ebene_massstab'] = data.get('ebene_massstab', 50.0)
                    s['gab_prefix'] = data.get('prefix', 'PD-MA-GAB-')
                else:
                    s['winkel_ebene_name'] = data.get(
                        'ebene_name', 'Winkelstützmauer')
                    s['winkel_ebene_massstab'] = data.get('ebene_massstab', 25.0)
                    s['winkel_prefix'] = data.get('prefix', 'PD-MWL-')
    except Exception:
        pass
    s['ver'] = SETTINGS_VERSION
    return s


def save_settings(s):
    try:
        s = dict(s)
        s['ver'] = SETTINGS_VERSION
        f = os.path.join(settings_dir(), SETTINGS_FILE)
        tmp = f + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fp:
            json.dump(s, fp, indent=2, ensure_ascii=False)
        os.replace(tmp, f)
    except Exception:
        pass


def is_color_token(s):
    """Erkennt '#RRGGBB' oder 'R,G,B' (0-255)."""
    s = (s or '').strip()
    if not s:
        return False
    if s.startswith('#') and len(s) in (4, 7):
        return True
    parts = s.split(',')
    if len(parts) == 3:
        try:
            return all(0 <= int(x.strip()) <= 255 for x in parts)
        except Exception:
            return False
    return False


def parse_color(s, fallback_h=0.0):
    """Farbtext -> (r, g, b) im Vectorworks-Bereich 0..65535."""
    s = (s or '').strip()
    try:
        if s.startswith('#'):
            t = s[1:]
            if len(t) == 3:
                t = ''.join(ch * 2 for ch in t)
            r, g, b = (int(t[i:i + 2], 16) for i in (0, 2, 4))
            return int(r * 257), int(g * 257), int(b * 257)
        if ',' in s:
            r, g, b = (int(x.strip()) for x in s.split(',')[:3])
            return int(r * 257), int(g * 257), int(b * 257)
    except Exception:
        pass
    # Rueckfall: aus der Hoehe abgeleiteter, stets gleicher Farbton
    return hsv_rgb((float(fallback_h) * 0.137) % 1.0, 0.42, 0.90)


def color_hex(rgb):
    """Vectorworks-RGB (0..65535) als stabilen Hex-Farbtext speichern."""
    try:
        werte = [max(0, min(65535, int(round(v)))) for v in rgb[:3]]
        return '#%02X%02X%02X' % tuple(int(round(v / 257.0)) for v in werte)
    except Exception:
        return '#808080'


def color_token(s, fallback_h=0.0):
    """Beliebige gueltige Eingabe auf #RRGGBB normalisieren."""
    return color_hex(parse_color(s, fallback_h))


def dialog_farbe_setzen(dlg, item, farbe, fallback_h=0.0):
    """Ein Vectorworks-Farbauswahlfeld aus einem Hex-Farbwert vorbelegen."""
    try:
        idx = vs.RGBToColorIndex(*parse_color(farbe, fallback_h))
        vs.SetColorChoice(dlg, item, idx)
        return True
    except Exception:
        return False


def dialog_farbe_lesen(dlg, item, fallback, fallback_h=0.0):
    """Aktuelle Farbe eines Farbauswahlfeldes als #RRGGBB liefern."""
    try:
        idx = vs.GetColorChoice(dlg, item)
        rgb = vs.ColorIndexToRGB(idx)
        if rgb is not None and len(rgb) >= 3:
            return color_hex(rgb)
    except Exception:
        pass
    return color_token(fallback, fallback_h)


def fundament_rgb(p=None):
    """Im Dialog gewaehlt Fundamentfarbe, mit eingebautem Rueckfall."""
    p = p if isinstance(p, dict) else {}
    return parse_color(p.get('fundament_farbe', DEFAULT_FUNDAMENT_FARBE), 0.0)


def doc_name():
    """Name des aktuellen Dokuments - die Merkliste gilt je Dokument."""
    for fn in ('GetFName', 'GetFPathName'):
        try:
            n = getattr(vs, fn)()
            if isinstance(n, (list, tuple)):
                n = n[0]
            if n:
                return os.path.basename(str(n))
        except Exception:
            continue
    return ''


def doc_key():
    """Stabile Dokumentkennung aus dem vollstaendigen Dateipfad."""
    try:
        pfad = vs.GetFPathName()
        if isinstance(pfad, (list, tuple)):
            pfad = pfad[0]
        if pfad:
            return os.path.normcase(os.path.normpath(str(pfad)))
    except Exception:
        pass
    return ''


def daten_gehoeren_zum_dokument(d):
    """Dokumentvergleich; alte Eintraege fallen auf den Dateinamen zurueck."""
    aktuell = doc_key()
    gespeichert = d.get('doc_key', '') if isinstance(d, dict) else ''
    if aktuell and gespeichert:
        return os.path.normcase(gespeichert) == os.path.normcase(aktuell)
    name = doc_name()
    alt = d.get('doc', '') if isinstance(d, dict) else ''
    return not (name and alt and alt != name)


def doc_dir():
    """Ordner der geoeffneten Zeichnung. Rueckfall: Anwenderordner
    (z. B. wenn das Dokument noch nie gesichert wurde)."""
    for fn in ('GetFPathName', 'GetFName'):
        try:
            pf = getattr(vs, fn)()
            if isinstance(pf, (list, tuple)):
                pf = pf[0]
            if pf:
                d = os.path.dirname(str(pf))
                if d and os.path.isdir(d):
                    return d
        except Exception:
            continue
    return settings_dir()


def doc_stem():
    """Dateiname der Zeichnung ohne Endung - fuer die Listennamen."""
    n = doc_name()
    if not n:
        return 'Zeichnung'
    stem = os.path.splitext(n)[0]
    for z in '\\/:*?"<>|':
        stem = stem.replace(z, '_')
    return stem or 'Zeichnung'


DATA_VERSION = 4


def _gueltiger_objektname(wert):
    text = str(wert or '').strip()
    return '' if text.lower() in ('none', '<none>', 'nil', 'null') else text


def migrate_data(data):
    """Alte Registry-/Record-Daten idempotent auf den aktuellen Stand bringen."""
    if not isinstance(data, dict):
        return None
    d = dict(data)
    try:
        old_version = int(d.get('schema_version', 0) or 0)
    except (TypeError, ValueError):
        old_version = 0
    for key in ('gruppe', 'uk_name', 'ok_name', 'pl_name', 'bez_name'):
        d[key] = _gueltiger_objektname(d.get(key))
    for feld in ('tab_names', 'ws_names'):
        namen = d.get(feld) or []
        if not isinstance(namen, (list, tuple)):
            namen = []
        d[feld] = [_gueltiger_objektname(n) for n in namen
                   if _gueltiger_objektname(n)]
    # Vorhandene Mauern behalten ihre gespeicherte Bezugslage. Nur neu
    # erzeugte Mauern erhalten die neue Initiallage am linken Maueranfang.
    if old_version < 4 and 'ref_anchor_initialized' not in d:
        d['ref_anchor_initialized'] = True
    d['schema_version'] = DATA_VERSION
    return d


def registry_path():
    return os.path.join(settings_dir(), REGISTRY_FILE)


def load_registry():
    try:
        f = registry_path()
        if os.path.isfile(f):
            with open(f, 'r', encoding='utf-8') as fp:
                d = json.load(fp)
            if isinstance(d, list):
                return [e for e in (migrate_data(x) for x in d) if e]
    except Exception:
        pass
    return []


def save_registry(eintraege):
    try:
        f = registry_path()
        tmp = f + '.tmp'
        sauber = [e for e in (migrate_data(x) for x in eintraege) if e]
        with open(tmp, 'w', encoding='utf-8') as fp:
            json.dump(sauber, fp, ensure_ascii=False)
        os.replace(tmp, f)
        return True
    except Exception:
        return False


def registry_add(eintrag):
    """Mauer merken - ersetzt einen vorhandenen Eintrag gleicher Kennung."""
    eintrag = migrate_data(eintrag)
    if not eintrag:
        return False
    wid = eintrag.get('wall_id')
    gruppe = eintrag.get('gruppe')

    def ist_derselbe(e):
        if e.get('wall_id') != wid:
            return False
        if str(wid or '').startswith(('MW-', 'GAB-')):
            return True
        return e.get('gruppe') == gruppe

    liste = [e for e in load_registry() if not ist_derselbe(e)]
    liste.append(eintrag)
    return save_registry(liste)


def katalog_vorgabe(typ=0):
    return DEFAULT_CATALOG_UN if int(typ) == 1 else DEFAULT_CATALOG


def katalog_schluessel(typ=0):
    return 'catalog_unarmiert' if int(typ) == 1 else 'catalog_armiert'


def katalog_custom_schluessel(typ=0):
    return katalog_schluessel(typ) + '_custom'


def load_catalog(typ=0, settings=None):
    """Winkelsteinkatalog aus Python-Vorgabe bzw. JSON-Einstellungen.

    CSV-Dateien sind nicht mehr erforderlich. Benutzeranpassungen werden mit
    den uebrigen Dialogeinstellungen in PD_MW_Einstellungen.json gespeichert.
    """
    daten = settings if isinstance(settings, dict) else load_settings()
    quelle = (daten.get(katalog_schluessel(typ))
              if daten and daten.get(katalog_custom_schluessel(typ))
              else None)
    if not isinstance(quelle, (list, tuple)) or not quelle:
        quelle = [(h, fu, col, 'Regelelement')
                  for h, fu, col in katalog_vorgabe(typ)]
    cat = []
    for eintrag in quelle:
        try:
            h, fu = float(eintrag[0]), float(eintrag[1])
        except Exception:
            continue
        if h <= 0 or fu <= 0:
            continue
        col = str(eintrag[2] or '') if len(eintrag) > 2 else ''
        bem = str(eintrag[3] or '') if len(eintrag) > 3 else 'Regelelement'
        cat.append((h, fu, col, bem))
    if not cat:
        cat = [(float(h), float(fu), col, 'Regelelement')
               for h, fu, col in katalog_vorgabe(typ)]
    return sorted(cat, key=lambda e: e[0])


# ---------------------------------------------------------------------------
# Einheiten
# ---------------------------------------------------------------------------

UNITS_PER_METER = {'m': 1.0, 'cm': 100.0, 'mm': 1000.0}


class U(object):
    """Umrechnung cm  ->  Zeichnungseinheiten."""
    factor = 1.0            # Zeichnungseinheiten je Meter

    @staticmethod
    def set(unit_name):
        U.factor = UNITS_PER_METER.get(unit_name, 1.0)

    @staticmethod
    def cm(value_cm):
        return float(value_cm) / 100.0 * U.factor

    @staticmethod
    def to_cm(value_units):
        return float(value_units) / U.factor * 100.0

    @staticmethod
    def to_m(value_units):
        return float(value_units) / U.factor


# ---------------------------------------------------------------------------
# Geometrie: Objekte lesen
# ---------------------------------------------------------------------------

T_LINE, T_RECT, T_POLYGON, T_POLYLINE = 2, 3, 5, 21


def get_type(h):
    """Objekttyp - je nach Version heisst die Funktion GetTypeN oder GetType."""
    if h is None:
        return -1
    for fn in ('GetTypeN', 'GetType'):
        try:
            t = getattr(vs, fn)(h)
            if t is not None:
                return int(t)
        except Exception:
            continue
    return -1


def type_name(h):
    return {T_LINE: 'Linie', T_RECT: 'Rechteck', T_POLYGON: 'Polygon',
            T_POLYLINE: 'Polylinie'}.get(get_type(h), 'Typ %d' % get_type(h))


EIGENE_KLASSEN = ('HILFE', 'TXT', 'BEM', 'TABELLE', 'FUSS', 'KOTE',
                  'FUNDAMENT', 'FUNDAMENT-BEM', 'UMRISS')


KLASSEN_PRAEFIXE = ('PD-MWL-', 'PD-MW-', 'PD-MA-GAB-')
AKTIVE_PRAEFIXE = set(KLASSEN_PRAEFIXE)


def register_prefix(prefix):
    prefix = str(prefix or '').strip()
    if prefix:
        AKTIVE_PRAEFIXE.add(prefix)


def ist_eigenes_objekt(h):
    """True, wenn das Objekt vom Werkzeug selbst erzeugt wurde."""
    try:
        c = vs.GetClass(h)
    except Exception:
        return False
    if not c:
        return False
    for pre in AKTIVE_PRAEFIXE:
        if c.startswith(pre):
            rest = c[len(pre):]
            if rest in EIGENE_KLASSEN or rest.isdigit():
                return True
    return False


def cleanup_helpers():
    """Liegengebliebene Hilfsobjekte aller bekannten Praefixe entfernen."""
    weg = []

    def cb(h):
        try:
            if vs.GetClass(h) in [pre + 'HILFE' for pre in AKTIVE_PRAEFIXE]:
                weg.append(h)
        except Exception:
            pass

    try:
        vs.ForEachObjectInLayer(cb, 0, 0, 2)
    except Exception:
        return 0
    n = 0
    for h in weg:
        try:
            vs.DelObject(h)
            n += 1
        except Exception:
            pass
    return n


_NIL = {'wert': None, 'init': False}


def nil_handle():
    """Ermittelt einmalig, was GetObject fuer einen nicht vorhandenen Namen
    liefert. Manche Installationen geben statt None ein NIL-Handle zurueck -
    jeder Zugriff darauf erzeugt sonst "Handle variable is NIL"."""
    if not _NIL['init']:
        _NIL['init'] = True
        try:
            _NIL['wert'] = vs.GetObject('PD-MW-###nicht-vorhanden###')
        except Exception:
            _NIL['wert'] = None
    return _NIL['wert']


def handle_valid(h):
    """True, wenn das Handle benutzbar ist."""
    if h is None:
        return False
    nv = nil_handle()
    if nv is not None:
        try:
            if h == nv:
                return False
        except Exception:
            pass
    try:
        return bool(h)
    except Exception:
        return True


def get_object(name):
    """GetObject mit Pruefung - liefert None statt eines NIL-Handles."""
    if not name:
        return None
    try:
        h = vs.GetObject(name)
    except Exception:
        return None
    return h if handle_valid(h) else None


def bbox_of(h):
    """Umschliessendes Rechteck eines Objekts als [x1, y1, x2, y2]."""
    if h is None:
        return None
    try:
        r = vs.GetBBox(h)
    except Exception:
        return None
    try:
        p1, p2 = r[0], r[1]
        werte = [float(p1[0]), float(p1[1]), float(p2[0]), float(p2[1])]
    except Exception:
        return None
    if any(v != v or abs(v) > 1.0e9 for v in werte):
        return None
    return werte


def sane_pts(pts):
    """Schutz vor ungueltigen Handles: unplausible Koordinaten verwerfen."""
    if not pts or len(pts) < 2:
        return False
    for q in pts:
        try:
            x, y = float(q[0]), float(q[1])
        except Exception:
            return False
        if x != x or y != y:            # NaN
            return False
        if abs(x) > 1.0e9 or abs(y) > 1.0e9:
            return False
    return poly_length(pts) > 1.0e-9


def obj_type_ok(h):
    """Geeignet ist jedes Objekt, aus dem sich mindestens zwei plausible
    Punkte auslesen lassen - unabhaengig von der Typnummer. Eigene
    Zeichenobjekte des Werkzeugs sind ausgeschlossen."""
    if h is None:
        return False
    try:
        if ist_eigenes_objekt(h):
            return False
        return sane_pts(get_vertices(h))
    except Exception:
        return False


def get_vertices(h):
    """Liefert die Stuetzpunkte eines Objekts als Liste [(x, y), ...].
    Bogensegmente von Polylinien werden ueber eine temporaere Polygon-
    Umwandlung aufgeloest (Sehnenzug). Unbekannte Typen werden generisch
    versucht - erst als Linienzug, dann als Strecke.
    """
    if h is None:
        return []
    t = get_type(h)

    if t == T_LINE:
        try:
            p1 = vs.GetSegPt1(h)
            p2 = vs.GetSegPt2(h)
            return [(p1[0], p1[1]), (p2[0], p2[1])]
        except Exception:
            return []

    if t == T_POLYGON:
        return _read_poly_points(h)

    if t == T_POLYLINE:
        raw = []
        has_arc = False
        try:
            n = vs.GetVertNum(h)
        except Exception:
            n = 0
        for i in range(1, (n or 0) + 1):
            try:
                res = vs.GetPolylineVertex(h, i)
                p = res[0]
                if res[1] != 0:
                    has_arc = True
                raw.append((p[0], p[1]))
            except Exception:
                try:
                    p = vs.GetPolyPt(h, i)
                    raw.append((p[0], p[1]))
                except Exception:
                    pass
        if has_arc:
            flat = flatten_polyline(h)
            if flat:
                return flat
        return raw

    # Unbekannter Typ: generisch versuchen
    pts = _read_poly_points(h)
    if len(pts) >= 2:
        return pts
    try:
        p1 = vs.GetSegPt1(h)
        p2 = vs.GetSegPt2(h)
        if p1 is not None and p2 is not None:
            return [(p1[0], p1[1]), (p2[0], p2[1])]
    except Exception:
        pass
    return []


def _read_poly_points(h):
    pts = []
    try:
        n = vs.GetVertNum(h)
    except Exception:
        return pts
    for i in range(1, (n or 0) + 1):
        try:
            p = vs.GetPolyPt(h, i)
            pts.append((p[0], p[1]))
        except Exception:
            try:
                res = vs.GetPolylineVertex(h, i)
                pts.append((res[0][0], res[0][1]))
            except Exception:
                pass
    return pts


def flatten_polyline(h):
    """Duplikat der Polylinie in ein Polygon wandeln und dessen Punkte lesen."""
    try:
        dup = vs.HDuplicate(h, 0, 0)
        if dup is None:
            return []
        newh = None
        try:
            newh = vs.ConvertToPolygon(dup, 0)
        except Exception:
            try:
                vs.ConvertToPolygon(dup)
                newh = vs.LNewObj()
            except Exception:
                newh = None
        target = newh if newh is not None else dup
        pts = []
        try:
            n = vs.GetVertNum(target)
            for i in range(1, n + 1):
                p = vs.GetPolyPt(target, i)
                pts.append((p[0], p[1]))
        except Exception:
            pts = []
        for x in (newh, dup):
            try:
                if x is not None:
                    vs.DelObject(x)
            except Exception:
                pass
        return pts
    except Exception:
        return []


def poly_length(pts):
    L = 0.0
    for i in range(len(pts) - 1):
        L += math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
    return L


def dist_point_poly(pts, p):
    """Kleinster Abstand eines Punktes zum Linienzug."""
    best = 1e18
    px, py = p[0], p[1]
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        dx, dy = x2 - x1, y2 - y1
        L2 = dx * dx + dy * dy
        if L2 < 1e-12:
            d = math.hypot(px - x1, py - y1)
        else:
            t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / L2))
            d = math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))
        best = min(best, d)
    return best


# ---------------------------------------------------------------------------
# Geometrie: Abwicklung (X = Laufmeter, Y = Hoehe)
# ---------------------------------------------------------------------------


def sort_by_x(pts):
    s = sorted(pts, key=lambda p: p[0])
    return s


def y_at(pts, x):
    """Lineare Interpolation der Hoehe an Station x (pts nach X sortiert)."""
    if not pts:
        return 0.0
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for i in range(len(pts) - 1):
        x1, y1 = pts[i]
        x2, y2 = pts[i + 1]
        if x1 <= x <= x2:
            if abs(x2 - x1) < 1e-12:
                return max(y1, y2)
            t = (x - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)
    return pts[-1][1]


def y_extremes(pts, x0, x1):
    """min/max Hoehe im Stationsbereich [x0, x1]."""
    vals = [y_at(pts, x0), y_at(pts, x1)]
    for p in pts:
        if x0 < p[0] < x1:
            vals.append(p[1])
    return min(vals), max(vals)


# ---------------------------------------------------------------------------
# Geometrie: Aufsichtslinie
# ---------------------------------------------------------------------------


def station_table(pts):
    """Kumulierte Laengen an den Stuetzpunkten."""
    st = [0.0]
    for i in range(len(pts) - 1):
        st.append(st[-1] + math.hypot(pts[i + 1][0] - pts[i][0],
                                      pts[i + 1][1] - pts[i][1]))
    return st


def corner_list(pts, min_angle_deg=1.0):
    """Knickpunkte als [{'s': Station, 'angle': Innenwinkel in Grad}, ...].
    angle = von den beiden Mauerschenkeln eingeschlossener Winkel
    (180 Grad = gerade, 90 Grad = rechtwinklige Ecke).
    """
    st = station_table(pts)
    out = []
    for i in range(1, len(pts) - 1):
        ax = pts[i][0] - pts[i - 1][0]
        ay = pts[i][1] - pts[i - 1][1]
        bx = pts[i + 1][0] - pts[i][0]
        by = pts[i + 1][1] - pts[i][1]
        la = math.hypot(ax, ay)
        lb = math.hypot(bx, by)
        if la < 1e-9 or lb < 1e-9:
            continue
        cosv = max(-1.0, min(1.0, (ax * bx + ay * by) / (la * lb)))
        abweichung = math.degrees(math.acos(cosv))      # Richtungsaenderung
        if abweichung > min_angle_deg:
            out.append({'s': st[i], 'angle': 180.0 - abweichung})
    return out


def point_at_station(pts, st_table, s):
    """Punkt und Richtungsvektor an Station s."""
    if s <= 0:
        i = 0
    elif s >= st_table[-1]:
        i = len(pts) - 2
    else:
        i = 0
        for k in range(len(st_table) - 1):
            if st_table[k] <= s <= st_table[k + 1]:
                i = k
                break
    x1, y1 = pts[i]
    x2, y2 = pts[i + 1]
    seg = st_table[i + 1] - st_table[i]
    t = 0.0 if seg < 1e-12 else (s - st_table[i]) / seg
    px = x1 + t * (x2 - x1)
    py = y1 + t * (y2 - y1)
    L = math.hypot(x2 - x1, y2 - y1)
    if L < 1e-12:
        dx, dy = 1.0, 0.0
    else:
        dx, dy = (x2 - x1) / L, (y2 - y1) / L
    return (px, py), (dx, dy)


# ---------------------------------------------------------------------------
# Auswahl der Referenzobjekte. Neue Mauern und Schnitte verwenden
# ausschliesslich die stabile Vorauswahl bestehender Objekte.
# ---------------------------------------------------------------------------


SCAN_INFO = {}

CRIT_TYPES = '((T=LINE) | (T=POLY) | (T=POLYLINE))'


def collect_by_layer_scan(objekt_option=0, limit=300):
    """Durchlauf ueber alle Ebenen. Die Bedeutung von objectOptions ist
    versionsabhaengig - deshalb werden mehrere Werte probiert und die
    Ergebnisse zusammengefuehrt (siehe all_candidates)."""
    out = []

    def cb(h):
        if len(out) < limit:
            out.append(h)

    try:
        vs.ForEachObjectInLayer(cb, objekt_option, 0, 2)
    except Exception:
        return []
    return out


def collect_by_criteria(crit, limit=300):
    """Objektsuche ueber ein Suchkriterium - unabhaengig von Klasse und Ebene."""
    out = []

    def cb(h):
        if len(out) < limit:
            out.append(h)

    try:
        vs.ForEachObject(cb, crit)
    except Exception:
        return []
    return out


def obj_signatur(h):
    """Kennzeichen zum Aussortieren doppelter Treffer aus mehreren Suchwegen."""
    pts = get_vertices(h)
    if not pts:
        return None
    # Zwei Polylinien koennen dieselben Endpunkte und dieselbe Punktzahl,
    # dazwischen aber einen voellig anderen Verlauf haben. Deshalb gehoeren
    # alle Stuetzpunkte zur Signatur.
    return tuple((round(q[0], 6), round(q[1], 6)) for q in pts)


def ist_ausgewaehlt(h):
    try:
        return bool(vs.Selected(h))
    except Exception:
        return False


def selected_objects():
    """Ausgewaehlte Bezugslinien - aus allen Kandidaten selbst gefiltert,
    weil sich der Auswahlfilter der Objektsuche versionsabhaengig verhaelt.
    """
    alle = all_candidates(500)
    sel = [h for h in alle if ist_ausgewaehlt(h)]
    SCAN_INFO['gefunden'] = len(alle)
    SCAN_INFO['ausgewaehlt'] = len(sel)
    return sel


def all_candidates(limit=300):
    """Alle geeigneten Linien des Dokuments - laengste zuerst.

    Es werden mehrere Suchwege zusammengefuehrt, weil sich die
    Vectorworks-Objektsuche je nach Version unterschiedlich verhaelt
    (z. B. nur Objekte der aktiven Klasse liefert).
    """
    SCAN_INFO.clear()
    treffer = []
    gesehen = set()
    wege = []

    quellen = [
        ('Kriteriensuche', lambda: collect_by_criteria(CRIT_TYPES, limit)),
        ('Ebenendurchlauf 0', lambda: collect_by_layer_scan(0, limit)),
        ('Ebenendurchlauf 2', lambda: collect_by_layer_scan(2, limit)),
        ('Ebenendurchlauf 3', lambda: collect_by_layer_scan(3, limit)),
    ]
    for name, holen in quellen:
        try:
            roh = holen()
        except Exception:
            roh = []
        neu_hier = 0
        for h in roh:
            if len(treffer) >= limit:
                break
            if not obj_type_ok(h):
                continue
            sig = obj_signatur(h)
            if sig is None or sig in gesehen:
                continue
            gesehen.add(sig)
            treffer.append(h)
            neu_hier += 1
        if neu_hier:
            wege.append('%s: %d' % (name, neu_hier))

    SCAN_INFO['quelle'] = ', '.join(wege) or '-'
    SCAN_INFO['objekte'] = len(treffer)
    treffer.sort(key=lambda h: -poly_length(get_vertices(h)))
    return treffer


def describe(h):
    pts = get_vertices(h)
    tname = type_name(h)
    nm = ''
    try:
        nm = vs.GetName(h) or ''
    except Exception:
        nm = ''
    lay = ''
    try:
        lay = vs.GetLName(vs.GetLayer(h)) or ''
    except Exception:
        lay = ''
    mark = ''
    try:
        mark = '* ' if vs.Selected(h) else '  '
    except Exception:
        mark = '  '
    txt = '%s%s %dP  L %.2f  X %.2f..%.2f  Y %.2f' % (
        mark, tname[:4], len(pts), poly_length(pts),
        min(q[0] for q in pts), max(q[0] for q in pts),
        sum(q[1] for q in pts) / float(len(pts)))
    if nm:
        txt += '  %s' % nm[:12]
    elif lay:
        txt += '  %s' % lay[:12]
    return txt


def assign_from_selection(sel, mit_aufsicht):
    """Schlaegt eine Zuordnung vor.
    1. Die beiden Kantenlinien sind das Paar mit der aehnlichsten
       X-Ausdehnung (und moeglichst grosser Ausdehnung).
    2. Die Aufsichtslinie ist von den uebrigen diejenige, deren abgewickelte
       Laenge dieser X-Ausdehnung am naechsten kommt.
    3. Von den beiden Kantenlinien ist die tiefer liegende die Unterkante.
    Rueckgabe: (h_uk, h_ok, h_pl) oder (None, None, None)
    """
    valid = [h for h in sel if sane_pts(get_vertices(h))]
    if len(valid) < 2:
        return None, None, None

    frame = PlanFrame.current(vs)
    info = {}
    for h in valid:
        pts = frame.local_points(get_vertices(h))
        info[h] = {
            'xext': max(q[0] for q in pts) - min(q[0] for q in pts),
            'len': poly_length(pts),
            'ymean': sum(q[1] for q in pts) / float(len(pts)),
        }

    bestes_paar, bester_wert = None, None
    for i in range(len(valid)):
        for j in range(i + 1, len(valid)):
            a, b = valid[i], valid[j]
            xa, xb = info[a]['xext'], info[b]['xext']
            if xa <= 0 or xb <= 0:
                continue
            wert = abs(xa - xb) - 0.05 * min(xa, xb)
            if bester_wert is None or wert < bester_wert:
                bester_wert, bestes_paar = wert, (a, b)
    if bestes_paar is None:
        bestes_paar = (valid[0], valid[1])

    kanten = sorted(bestes_paar, key=lambda h: info[h]['ymean'])
    h_uk, h_ok = kanten[0], kanten[-1]

    h_pl = None
    if mit_aufsicht:
        rest = [h for h in valid if h not in bestes_paar]
        if rest:
            ziel = (info[h_uk]['xext'] + info[h_ok]['xext']) / 2.0
            h_pl = min(rest, key=lambda h: abs(info[h]['len'] - ziel))
    return h_uk, h_ok, h_pl


def pts_equal(a, b, tol=None):
    """Vergleicht zwei Punktlisten (Toleranz relativ zur Laenge)."""
    if len(a) != len(b) or not a:
        return False
    if tol is None:
        tol = max(poly_length(a), 1.0) * 1e-6 + 1e-9
    for (x1, y1), (x2, y2) in zip(a, b):
        if abs(x1 - x2) > tol or abs(y1 - y2) > tol:
            return False
    return True


def find_by_pts(pts):
    """Sucht das Objekt, dessen Stuetzpunkte den gespeicherten entsprechen."""
    for h in all_candidates():
        if pts_equal(get_vertices(h), pts):
            return h
    return None


def unique_name(base):
    i = 1
    while i < 1000:
        nm = '%s%03d' % (base, i)
        if get_object(nm) is None:
            return nm
        i += 1
    return '%s%s' % (base, datetime.datetime.now().strftime('%H%M%S'))


def ensure_name(h, base):
    try:
        nm = _gueltiger_objektname(vs.GetName(h))
    except Exception:
        nm = ''
    if nm:
        return nm
    nm = unique_name(base)
    try:
        vs.SetName(h, nm)
    except Exception:
        return ''
    return nm


# ---------------------------------------------------------------------------
# Klassen / Attribute / Text
# ---------------------------------------------------------------------------


def class_name_for_height(prefix, h_cm):
    return '%s%03d' % (prefix, int(round(h_cm)))


def hsv_rgb(h, s, v):
    i = int(h * 6.0)
    f = h * 6.0 - i
    p = v * (1.0 - s)
    q = v * (1.0 - f * s)
    t = v * (1.0 - (1.0 - f) * s)
    i = i % 6
    r, g, b = [(v, t, p), (q, v, p), (p, v, t),
               (p, q, v), (t, p, v), (v, p, q)][i]
    return int(r * 65535), int(g * 65535), int(b * 65535)


def class_exists(name):
    try:
        for i in range(1, vs.ClassNum() + 1):
            if vs.ClassList(i) == name:
                return True
    except Exception:
        pass
    return False


CLASS_COLOR_INFO = {'wege': set(), 'ok': 0, 'fehl': 0}


def set_class_color(name, rgb, solid=True):
    """Klassenfarbe setzen und per Rueckleseprobe kontrollieren.
    Vorder- und Hintergrundfarbe werden gleich gesetzt, weil Vectorworks je
    nach Objektart die eine oder die andere fuer den Vollton verwendet.
    """
    if not rgb:
        return False

    def passt():
        try:
            cur = vs.GetClFillFore(name)
            if cur and len(cur) >= 3:
                return all(abs(int(cur[i]) - rgb[i]) < 700 for i in range(3))
        except Exception:
            pass
        return None            # nicht pruefbar

    # Weg 1: Klassenfunktionen
    for fn, args in (('SetClUseGraphic', (name, True)),
                      ('SetClFPat', (name, 1 if solid else 0)),
                      ('SetClFillFore', (name, tuple(rgb))),
                      ('SetClFillBack', (name, tuple(rgb))),
                      ('SetClPenFore', (name, (0, 0, 0))),
                      ('SetClPenBack', (name, (0, 0, 0))),
                      ('SetClLW', (name, 13))):
        try:
            getattr(vs, fn)(*args)
        except Exception:
            pass
    pr = passt()
    if pr is True:
        CLASS_COLOR_INFO['wege'].add('Klassenfunktionen')
        CLASS_COLOR_INFO['ok'] += 1
        return True

    # Weg 2: ueber das Handle der Klasse
    try:
        hc = get_object(name)
        if hc is not None:
            vs.SetFPat(hc, 1 if solid else 0)
            vs.SetFillFore(hc, tuple(rgb))
            vs.SetFillBack(hc, tuple(rgb))
            try:
                vs.SetPenFore(hc, (0, 0, 0))
                vs.SetPenBack(hc, (0, 0, 0))
                vs.SetLW(hc, 13)
            except Exception:
                pass
            pr = passt()
            if pr is True:
                CLASS_COLOR_INFO['wege'].add('Klassenhandle')
                CLASS_COLOR_INFO['ok'] += 1
                return True
    except Exception:
        pass

    if pr is None:
        # Beide Schreibwege wurden versucht; diese API-Version erlaubt nur
        # keine Rueckleseprobe.
        CLASS_COLOR_INFO['wege'].add('beide Wege (ungeprueft)')
        CLASS_COLOR_INFO['ok'] += 1
        return True
    CLASS_COLOR_INFO['wege'].add('nicht uebernommen')
    CLASS_COLOR_INFO['fehl'] += 1
    return False


def ensure_class(name, rgb=None, solid=True, force=False):
    """Klasse anlegen (falls nicht vorhanden) und Attribute setzen.
    Bei einer bereits vorhandenen Klasse bleiben die Attribute unangetastet,
    sofern force nicht gesetzt ist.
    """
    exists = class_exists(name)
    active = vs.ActiveClass()
    try:
        vs.NameClass(name)
    except Exception:
        pass
    if ((not exists) or force) and rgb is not None:
        set_class_color(name, rgb, solid)
    try:
        vs.NameClass(active)
    except Exception:
        pass


def verlauf_farbe(index, anzahl, modus):
    """Abgestufte Farbe fuer die Hoehenstufe index von anzahl.
    Die niedrigste Stufe bekommt die hellste, die hoechste die kraeftigste
    Farbe - dadurch sind die Winkelsteine grafisch unterscheidbar."""
    t = 0.0 if anzahl <= 1 else float(index) / float(anzahl - 1)
    if modus == 1:                       # gruen -> gelb -> rot
        return hsv_rgb(0.33 * (1.0 - t), 0.55, 0.95 - 0.12 * t)
    if modus == 2:                       # einfarbig hell -> dunkel
        return hsv_rgb(0.58, 0.18 + 0.55 * t, 0.97 - 0.42 * t)
    if modus == 3:                       # Graustufen
        w = int((0.88 - 0.52 * t) * 65535)
        return (w, w, w)
    return hsv_rgb(0.58 - 0.58 * t, 0.45, 0.92)


def prepare_classes(prefix, heights, colors_cfg=None, force=False,
                    transparenz=0.0, farb_modus=0,
                    fundament_cfg=DEFAULT_FUNDAMENT_FARBE):
    """Alle benoetigten Hoehenklassen und die Textklasse anlegen.
    Die Farbe je Mauerwinkeltyp kommt aus dem Katalog (Spalte Farbe);
    fehlt sie, wird ein aus der Hoehe abgeleiteter, konstanter Farbton benutzt.
    """
    colors_cfg = colors_cfg or {}
    colors = {}
    sortiert = sorted(heights)
    for idx, h in enumerate(sortiert):
        key = int(round(h))
        if farb_modus:
            rgb = verlauf_farbe(idx, len(sortiert), farb_modus)
        else:
            rgb = parse_color(colors_cfg.get(str(key), ''), h)
        cn = class_name_for_height(prefix, h)
        ensure_class(cn, rgb, True, force)
        set_class_opacity(cn, max(0.0, 100.0 - transparenz))
        colors[key] = rgb
    # Beschriftungen, Bemassungen und reine Linienklassen sind immer schwarz,
    # auch wenn die Klassen in einem bestehenden Dokument anders formatiert
    # wurden. Nur die Flaechenklassen erhalten Typfarben.
    ensure_class(prefix + 'TXT', (0, 0, 0), False, True)
    ensure_class(prefix + 'TABELLE', (0, 0, 0), False, True)
    ensure_class(prefix + 'BEM', (0, 0, 0), False, True)
    ensure_class(prefix + 'FUNDAMENT-BEM', (0, 0, 0), False, True)
    ensure_class(prefix + 'KOTE', (0, 0, 0), False, True)
    ensure_class(prefix + 'FUSS', (0, 0, 0), False, True)
    ensure_class(prefix + 'FUNDAMENT', parse_color(fundament_cfg, 0.0),
                 True, True)
    set_class_opacity(prefix + 'FUNDAMENT',
                      max(0.0, 100.0 - transparenz))
    return colors


def set_new_line_style(name):
    """Linientyp fuer die naechsten Objekte setzen (ohne Handle).
    Leerer Name = wieder durchgezogen."""
    if not name:
        try:
            vs.PenPatN(2)       # dokumentierter Vollstrich
        except Exception:
            pass
        return
    try:
        idx = int(vs.Name2Index(name))
        if idx > 0:
            vs.PenPatN(-idx)    # negative Indizes bezeichnen Linientypen
            return
    except Exception:
        pass
    try:
        vs.PenPatN(4)           # Rueckfall: gestricheltes Stiftmuster
    except Exception:
        pass


TEXT_FONT = 'Arial'
TEXT_DEFAULT_SIZE = 8.0


def normalized_font_size(value):
    """Gueltige Papier-Schriftgroesse in Punkt; Vorgabe ist Arial 8 pt."""
    try:
        size_pt = float(value)
    except Exception:
        size_pt = TEXT_DEFAULT_SIZE
    if not math.isfinite(size_pt) or size_pt <= 0:
        size_pt = TEXT_DEFAULT_SIZE
    return min(size_pt, 72.0)


def set_text_style(font, size_pt):
    # Die Werkzeugbeschriftung bleibt bewusst einheitlich in Arial. Die
    # Schriftgroesse ist weiterhin einstellbar und wird als Papiermass in pt
    # behandelt; Text- und Bemassungsgeometrie skalieren ueber text_metrics.
    font = TEXT_FONT
    size_pt = normalized_font_size(size_pt)
    try:
        fid = vs.GetFontID(font)
        if fid is not None and fid >= 0:
            vs.TextFont(fid)
    except Exception:
        pass
    try:
        vs.TextSize(size_pt)
    except Exception:
        pass
    TEXT_STIL['groesse'] = size_pt
    # Kein TextFace-Aufruf: Der Python-Callback von Vectorworks 2026 nimmt
    # die VectorScript-Mengen-Syntax [] nicht an. Der normale Schriftschnitt
    # wird nach der Erzeugung mit SetTextStyle direkt am Textobjekt gesetzt.


HANDLES_USABLE = None       # wird beim ersten erzeugten Objekt ermittelt
OPACITY_INFO = {'klasse': False, 'objekt': False}
NEW_OBJS = []


def apply_attrs(cls, rgb=None, solid=False, lw=13, pen=(0, 0, 0)):
    """Setzt Klasse und Attribute fuer die NAECHSTEN erzeugten Objekte.
    Dieser Weg braucht kein Handle und funktioniert deshalb immer.

    Wichtig: Vectorworks nimmt fuer eine Volltonfuellung je nach Objektart
    einmal die Vorder-, einmal die Hintergrundfarbe. Deshalb werden BEIDE
    auf dieselbe Farbe gesetzt - dann stimmt sie in jedem Fall.
    """
    # Vorgabe fuer das gesamte Werkzeug: Linien und Konturen sind schwarz.
    # Der Parameter bleibt aus Kompatibilitaetsgruenden bestehen, wird aber
    # absichtlich nicht als farbiger Stift uebernommen.
    _ = pen
    for fn, args in (('NameClass', (cls,)),
                     ('FillPat', (1 if solid else 0,)),
                     ('FillFore', (tuple(rgb),) if rgb is not None else None),
                     ('FillBack', (tuple(rgb),) if rgb is not None else None),
                     ('PenFore', ((0, 0, 0),)),
                     ('PenBack', ((0, 0, 0),)),
                     ('PenSize', (lw,))):
        if args is None:
            continue
        try:
            getattr(vs, fn)(*args)
        except Exception:
            pass


def set_class_opacity(cls, opacity_pct):
    """Deckkraft einer Klasse setzen (Funktionsname je nach Version)."""
    for fn in ('SetClOpacity', 'SetClassOpacity'):
        try:
            getattr(vs, fn)(cls, opacity_pct)
            OPACITY_INFO['klasse'] = True
            return True
        except Exception:
            continue
    return False


def set_obj_opacity(h, opacity_pct):
    if not HANDLES_USABLE or h is None:
        return False
    try:
        vs.SetOpacity(h, opacity_pct)
        OPACITY_INFO['objekt'] = True
        return True
    except Exception:
        return False


def _reg(h):
    """Gueltiges erzeugtes Objekt merken und unmittelbar schwarz setzen."""
    global HANDLES_USABLE
    try:
        gueltig = handle_valid(h) and get_type(h) > 0
    except Exception:
        gueltig = False
    if gueltig:
        HANDLES_USABLE = True
        NEW_OBJS.append(h)
        # Aktive Attribute reichen nach einem Neuaufbau nicht immer aus:
        # Vectorworks kann dabei die zuvor aktive (z. B. weisse) Stiftfarbe
        # auf das neue Objekt uebertragen. Darum den Stift unmittelbar am
        # erzeugten Objekt nochmals auf Schwarz setzen.
        for fn in ('SetPenFore', 'SetPenBack'):
            try:
                getattr(vs, fn)(h, (0, 0, 0))
            except Exception:
                pass
    elif HANDLES_USABLE is None:
        HANDLES_USABLE = False
    return h


TEXT_BOXES = []              # bereits belegte Textflaechen (Weltkoordinaten)
TEXT_STIL = {'font': TEXT_FONT, 'groesse': TEXT_DEFAULT_SIZE, 'massstab': 0.0}


def text_hoehe_units():
    """Schrifthoehe der zuletzt gesetzten Textgroesse in Zeichnungseinheiten.
    Nutzt denselben Massstab wie text_metrics."""
    sc = TEXT_STIL.get('massstab', 0.0)
    if sc <= 0:
        sc = layer_scale() or 100.0
    mm = normalized_font_size(TEXT_STIL.get('groesse')) * 25.4 / 72.0 * sc
    th = mm / 1000.0 * U.factor
    return th if th > 0 else U.cm(20.0)


def _text_box(txt, x, y, rot_deg, just, valign, th):
    """Umschliessendes (gedrehtes) Rechteck eines Textes."""
    w = max(len(txt), 1) * th * 0.60
    h = th * 1.2
    if just == 2:
        x0, x1 = -w / 2.0, w / 2.0
    elif just == 3:
        x0, x1 = -w, 0.0
    else:
        x0, x1 = 0.0, w
    if valign == 1:
        y0, y1 = -h, 0.0
    elif valign == 2:
        y0, y1 = -h / 2.0, h / 2.0
    elif valign == 3:
        y0, y1 = -h * 0.25, h * 0.75
    else:
        y0, y1 = 0.0, h
    a = math.radians(rot_deg)
    ca, sa = math.cos(a), math.sin(a)
    return [(x + px * ca - py * sa, y + px * sa + py * ca)
            for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]


def _aabb(box):
    xs = [q[0] for q in box]
    ys = [q[1] for q in box]
    return (min(xs), min(ys), max(xs), max(ys))


def _aabb_trennt(a, b):
    return (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _ueberlappt(A, B):
    """Trennachsentest fuer zwei gedrehte Rechtecke."""
    for poly in (A, B):
        for i in range(len(poly)):
            x1, y1 = poly[i]
            x2, y2 = poly[(i + 1) % len(poly)]
            ax, ay = -(y2 - y1), (x2 - x1)
            L = math.hypot(ax, ay)
            if L < 1e-12:
                continue
            ax, ay = ax / L, ay / L
            pa = [q[0] * ax + q[1] * ay for q in A]
            pb = [q[0] * ax + q[1] * ay for q in B]
            if max(pa) <= min(pb) + 1e-9 or max(pb) <= min(pa) + 1e-9:
                return False
    return True


def freie_lage(txt, x, y, rot_deg, just, valign, th):
    """Sucht eine ueberlappungsfreie Lage. Zuerst quer zur Leserichtung
    (dort stoert die Verschiebung am wenigsten), danach zusaetzlich laengs.
    Rueckgabe: (x, y, box, verschoben)."""
    a = math.radians(rot_deg)
    lx, ly = math.cos(a), math.sin(a)          # Leserichtung
    qx, qy = -math.sin(a), math.cos(a)         # quer dazu
    umkreis = th * 42.0
    nah = [b for b in TEXT_BOXES
           if abs(b[0][0] - x) < umkreis and abs(b[0][1] - y) < umkreis]

    def frei(nx, ny):
        box = _text_box(txt, nx, ny, rot_deg, just, valign, th)
        kasten = _aabb(box)
        for b in nah:
            if _aabb_trennt(kasten, b[2]):
                continue          # weit auseinander - kein Feintest noetig
            if _ueberlappt(box, b[1]):
                return None
        return box

    box = frei(x, y)
    if box is not None:
        return x, y, box, False

    schrittweite = th * 1.15
    versatz = [(0.0, 0.0)]
    for i in range(1, 20):
        versatz.append((i, 0.0))
        versatz.append((-i, 0.0))
    for j in range(1, 8):
        for i in range(0, 15):
            versatz.append((i, j))
            versatz.append((-i, j))
            versatz.append((i, -j))
            versatz.append((-i, -j))

    for dq, dl in versatz[1:]:
        nx = x + qx * dq * schrittweite + lx * dl * schrittweite * 1.6
        ny = y + qy * dq * schrittweite + ly * dl * schrittweite * 1.6
        box = frei(nx, ny)
        if box is not None:
            return nx, ny, box, True

    return x, y, _text_box(txt, x, y, rot_deg, just, valign, th), False


def make_text(txt, x, y, rot_deg, just, valign, cls, rgb=None,
              kollision=True):
    """Textobjekt erzeugen - Klasse, Ausrichtung und Drehung ueber den
    Zeichenzustand. Die Textfarbe ist die Fuellfarbe des Textobjekts,
    deshalb wird sie auf allen Kanaelen gesetzt (Vorgabe schwarz)."""
    _ = rgb
    farbe = (0, 0, 0)
    if kollision and txt:
        th = text_hoehe_units()
        x, y, box, _verschoben = freie_lage(
            txt, x, y, rot_deg, just, valign, th)
        TEXT_BOXES.append(((x, y), box, _aabb(box)))
    # solid=False: eine Volltonfuellung wuerde Vectorworks als gefuelltes
    # Rechteck ueber den Text zeichnen.
    apply_attrs(cls, farbe, False, 13, farbe)
    set_text_style(TEXT_FONT, TEXT_STIL.get('groesse', TEXT_DEFAULT_SIZE))
    # Interne Werte bleiben abwaertskompatibel: 2 bedeutete im Werkzeug
    # immer Mitte, 3 Grundlinie und 4 Unterkante. Vectorworks erwartet dafuer
    # die dokumentierten Werte 3, 4 und 5.
    vw_valign = {1: 1, 2: 3, 3: 4, 4: 5}.get(valign, 3)
    try:
        vs.TextJust(just)             # 1 links, 2 zentriert, 3 rechts
        vs.TextVerticalAlign(vw_valign)
    except Exception:
        pass
    try:
        vs.TextRotate(rot_deg)
    except Exception:
        pass
    vs.TextOrigin(x, y)
    vs.CreateText(txt)
    h = _reg(vs.LNewObj())
    force_attrs(h, cls, farbe, False)
    force_text_style(h, txt, TEXT_STIL.get('groesse', TEXT_DEFAULT_SIZE))
    if HANDLES_USABLE and h is not None:
        try:
            vs.SetTextVertAlignN(h, vw_valign)
        except Exception:
            pass
    try:
        vs.TextRotate(0.0)
    except Exception:
        pass
    return h


def ebene_vorbereiten(p):
    """Legt die Zeichenebene fuer die Mauer an (falls noetig), stellt ihren
    Massstab ein und macht sie aktiv. Rueckgabe: Name der vorher aktiven
    Ebene (fuer eine spaetere Rueckkehr)."""
    if not p.get('ebene_aktiv', True):
        return None
    name = (p.get('ebene_name') or 'Winkelstützmauer').strip()
    if not name:
        return None
    vorher = ''
    try:
        vorher = vs.GetLName(vs.ActLayer()) or ''
    except Exception:
        vorher = ''
    try:
        vs.Layer(name)              # legt die Ebene an, wenn es sie nicht gibt
    except Exception:
        return vorher

    h = None
    try:
        h = vs.ActLayer()
    except Exception:
        h = None
    massstab = float(p.get('ebene_massstab', 25.0) or 25.0)
    if h is not None and massstab > 0:
        for fn in ('SetLScale', 'SetLayerScale'):
            try:
                getattr(vs, fn)(h, massstab)
                break
            except Exception:
                continue
    return vorher


def ebene_wiederherstellen(name):
    """Aktiviert nach dem Zeichnen wieder die zuvor verwendete Ebene."""
    if not name:
        return
    try:
        vs.Layer(name)
    except Exception:
        pass


def layer_scale():
    """Massstab der aktiven Konstruktionsebene (z. B. 100 bei 1:100).
    Der Rueckgabewert von GetLScale ist versionsabhaengig, deshalb werden
    mehrere Aufrufformen probiert und das Ergebnis auf Plausibilitaet
    geprueft. 0.0 heisst: nicht ermittelbar."""
    versuche = []
    try:
        h = vs.ActLayer()
        versuche.append(lambda: vs.GetLScale(h))
        try:
            nm = vs.GetLName(h)
            if nm:
                versuche.append(lambda: vs.GetLScale(nm))
        except Exception:
            pass
    except Exception:
        pass
    versuche.append(lambda: vs.GetLScale(vs.FLayer()))
    for holen in versuche:
        try:
            sc = holen()
            if isinstance(sc, (list, tuple)):
                sc = sc[0]
            sc = float(sc)
        except Exception:
            continue
        if 0.02 <= sc <= 20000.0:
            return sc
    return 0.0


def text_metrics(p):
    """(Schrifthoehe, Zeilenabstand, Zeichenbreite) in Zeichnungseinheiten.

    Die Schriftgroesse ist in Punkt auf dem Papier - in der Zeichnung waechst
    sie mit dem Ebenenmassstab. Massgebend ist immer der tatsaechlich aktive
    Ebenenmassstab. Der Dialogwert dient nur als Rueckfall, falls Vectorworks
    den aktiven Massstab nicht auslesen kann.
    """
    try:
        eingestellt = float(p.get('ebene_massstab', 0.0) or 0.0)
    except Exception:
        eingestellt = 0.0
    sc = layer_scale()
    if sc <= 0:
        sc = eingestellt if eingestellt > 0 else 100.0
    TEXT_STIL['massstab'] = sc
    size_pt = normalized_font_size(p.get('font_size', TEXT_DEFAULT_SIZE))
    TEXT_STIL['groesse'] = size_pt
    mm = size_pt * 25.4 / 72.0 * sc
    th = mm / 1000.0 * U.factor
    if th <= 0:
        th = U.cm(20.0)
    return th, th * 1.8, th * 0.62


def dim_abstand_units(p):
    """Bemassungsabstand mit textabhaengiger Mindestgroesse.

    Der Dialogwert bleibt das gewuenschte Mindestmass in cm. Bei groesserer
    Schrift oder groesserem Ebenenmassstab waechst der Abstand automatisch,
    damit Masszahl, Hilfslinien und Geometrie nicht kollidieren.
    """
    try:
        vorgabe = max(0.0, float(p.get('dim_abstand', 60.0)))
    except Exception:
        vorgabe = 60.0
    th = text_metrics(p)[0]
    return max(U.cm(vorgabe), th * 2.5)


def fmt_cm(v):
    """Masszahl in cm, ohne Einheit."""
    return ('%.0f' % v) if abs(v - round(v)) < 0.05 else ('%.1f' % v)


def _dline(x1, y1, x2, y2, cls):
    apply_attrs(cls, None, False)
    vs.MoveTo(x1, y1)
    vs.LineTo(x2, y2)
    h = _reg(vs.LNewObj())
    force_attrs(h, cls, None, False)
    return h


def dim_between(p1, p2, off, text, cls, p, kurz=False):
    """Massketten-Element aus Zeichnungsgeometrie:
    Masshilfslinien, Masslinie, Schraegstriche und Masszahl.
    off = senkrechter Abstand der Masslinie (Vorzeichen = Seite).
    """
    x1, y1 = p1[0], p1[1]
    x2, y2 = p2[0], p2[1]
    dx, dy = x2 - x1, y2 - y1
    L = math.hypot(dx, dy)
    if L < 1e-9:
        return
    ux, uy = dx / L, dy / L
    nx, ny = -uy, ux
    ax, ay = x1 + nx * off, y1 + ny * off
    bx, by = x2 + nx * off, y2 + ny * off

    th, _lh, _cw = text_metrics(p)
    s = 1.0 if off >= 0 else -1.0
    if kurz:
        # nur kurze Hilfslinien beidseits der Masslinie
        stub = th * 0.5
        _dline(ax - nx * stub, ay - ny * stub, ax + nx * stub, ay + ny * stub, cls)
        _dline(bx - nx * stub, by - ny * stub, bx + nx * stub, by + ny * stub, cls)
    else:
        gap = th * 0.15 * s
        over = th * 0.5 * s
        _dline(x1 + nx * gap, y1 + ny * gap, ax + nx * over, ay + ny * over, cls)
        _dline(x2 + nx * gap, y2 + ny * gap, bx + nx * over, by + ny * over, cls)
    _dline(ax, ay, bx, by, cls)

    t = th * 0.45
    for qx, qy in ((ax, ay), (bx, by)):
        _dline(qx - (ux + nx) * t / 2.0, qy - (uy + ny) * t / 2.0,
               qx + (ux + nx) * t / 2.0, qy + (uy + ny) * t / 2.0, cls)

    ang = math.degrees(math.atan2(uy, ux))
    if ang > 90.0:
        ang -= 180.0
    if ang < -90.0:
        ang += 180.0
    tx = (ax + bx) / 2.0 + nx * th * 0.25 * s
    ty = (ay + by) / 2.0 + ny * th * 0.25 * s
    set_text_style(p['font'], p['font_size'])
    make_text(text, tx, ty, ang, 2, 4 if s > 0 else 1, cls)


def fundament_masswerte(fundamente):
    """Fundamentdicke d und Sohlentiefe T an allen Profilstuetzstellen."""
    werte = []
    gesehen = set()
    for fund in fundamente or []:
        basis = fund.get('basis_pts') or []
        oben = fund.get('top_pts') or []
        gel = fund.get('gel_pts') or []
        if len(basis) < 2 or len(oben) < 2:
            continue
        xs = sorted(set(round(float(q[0]), 9)
                        for profil in (basis, oben, gel)
                        for q in profil))
        for x in xs:
            y_basis = y_at(basis, x)
            y_oben = y_at(oben, x)
            y_gel = y_at(gel, x) if len(gel) >= 2 else y_oben
            staerke_cm = U.to_cm(y_oben - y_basis)
            tiefe_cm = U.to_cm(y_gel - y_basis)
            if staerke_cm <= 1e-6 or tiefe_cm <= 1e-6:
                continue
            schluessel = (round(x, 8), round(staerke_cm, 3),
                           round(tiefe_cm, 3))
            if schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            werte.append({
                'x': x, 'basis': y_basis, 'oben': y_oben, 'gel': y_gel,
                'd_cm': staerke_cm, 't_cm': tiefe_cm,
            })
    return werte


def draw_fundament_staerken(fundamente, p, cls):
    """Fundamentbemaßung der Ansicht ohne Wiederholungen.

    Konstante Werte werden einmal angegeben. Veraendert sich Dicke oder
    Sohlentiefe entlang der Mauer, werden nur Minimum und Maximum an ihren
    tatsaechlichen Profilstellen ausgewertet. Die Masslinien liegen gesammelt
    links bzw. rechts ausserhalb der Ansicht. Rueckgabe: gezeichnete Masstexte.
    """
    werte = fundament_masswerte(fundamente)
    if not werte:
        return []
    x_min = min(w['x'] for w in werte)
    x_max = max(w['x'] for w in werte)
    x_mitte = (x_min + x_max) / 2.0
    abstand = dim_abstand_units(p)
    plaetze = {'links': 0, 'rechts': 0}
    gezeichnet = []

    def mass(w, ende, text, seite):
        platz = plaetze[seite]
        plaetze[seite] += 1
        off = abstand * (0.65 + platz * 0.95)
        if seite == 'rechts':
            off = -off
        # Das Mass bleibt vertikal korrekt, wird aber aus dem dicht belegten
        # Wandfeld an den jeweiligen Aussenrand projiziert.
        x_mass = x_min if seite == 'links' else x_max
        dim_between((x_mass, w['basis']), (x_mass, w[ende]), off,
                    text, cls, p)
        gezeichnet.append(text)

    def charakteristisch(key, ende, symbol, standardseite):
        kandidaten = [w for w in werte if w[key] > 1e-6]
        if not kandidaten:
            return
        klein = min(kandidaten, key=lambda w: w[key])
        gross = max(kandidaten, key=lambda w: w[key])
        if gross[key] - klein[key] <= 0.5:
            # Einen konstanten Wert am aeusseren Rand antragen.
            w = (min(kandidaten, key=lambda q: q['x'])
                 if standardseite == 'links' else
                 max(kandidaten, key=lambda q: q['x']))
            mass(w, ende, '%s = %s cm' % (symbol, fmt_cm(w[key])),
                 standardseite)
            return
        for zusatz, w in (('min', klein), ('max', gross)):
            seite = 'links' if w['x'] <= x_mitte else 'rechts'
            mass(w, ende, '%s %s = %s cm' % (
                symbol, zusatz, fmt_cm(w[key])), seite)

    # T links, d rechts: getrennte Massgassen verhindern Textkollisionen.
    charakteristisch('t_cm', 'gel', 'T', 'links')
    charakteristisch('d_cm', 'oben', 'd', 'rechts')
    return gezeichnet


def eindeutige_fundament_quermasse(masse):
    """Je Fundamentbreite nur ein Quermass in der Aufsicht ausgeben."""
    ausgabe = []
    gesehen = set()
    for pa, pb, breite_cm in masse:
        schluessel = round(float(breite_cm), 1)
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        ausgabe.append((pa, pb, breite_cm))
    return ausgabe


def draw_winkelmass(pa, pe, pb, cls, p):
    """Winkelbogen mit Masszahl an einem Knick der Aufsichtslinie."""
    ax, ay = pa[0] - pe[0], pa[1] - pe[1]
    bx, by = pb[0] - pe[0], pb[1] - pe[1]
    la, lb = math.hypot(ax, ay), math.hypot(bx, by)
    if la < 1e-9 or lb < 1e-9:
        return
    a1 = math.atan2(ay, ax)
    a2 = math.atan2(by, bx)
    delta = (a2 - a1 + math.pi) % (2.0 * math.pi) - math.pi
    winkel = abs(math.degrees(delta))
    if winkel >= 179.0 or winkel <= 1.0:
        return

    th = text_metrics(p)[0]
    radius = min(max(th * 1.8, U.cm(25.0)), min(la, lb) * 0.32)
    if radius <= th * 0.8:
        return
    schritte = max(6, int(winkel / 12.0) + 1)
    punkte = []
    for i in range(schritte + 1):
        a = a1 + delta * float(i) / float(schritte)
        punkte.append((pe[0] + math.cos(a) * radius,
                       pe[1] + math.sin(a) * radius))
    for q1, q2 in zip(punkte, punkte[1:]):
        _dline(q1[0], q1[1], q2[0], q2[1], cls)

    # Kurze Begrenzungsstriche an den Enden des Winkelbogens.
    for a in (a1, a1 + delta):
        _dline(pe[0] + math.cos(a) * radius * 0.82,
               pe[1] + math.sin(a) * radius * 0.82,
               pe[0] + math.cos(a) * radius * 1.12,
               pe[1] + math.sin(a) * radius * 1.12, cls)
    mitte = a1 + delta / 2.0
    txt = fmt_cm(winkel) + chr(176)
    make_text(txt,
              pe[0] + math.cos(mitte) * (radius + th * 0.75),
              pe[1] + math.sin(mitte) * (radius + th * 0.75),
              0.0, 2, 2, cls)


def gab_fund_ueberstand_cm(p):
    """Nicht negativer Gabionen-Fundamentueberstand auf allen Seiten."""
    try:
        wert = float((p or {}).get(
            'gab_fund_ueberstand', GAB_FUND_UEBERSTAND_CM))
        return max(0.0, wert) if math.isfinite(wert) else GAB_FUND_UEBERSTAND_CM
    except Exception:
        return GAB_FUND_UEBERSTAND_CM


def draw_gab_aufsicht_stationsmasse(pl_pts, p, sign):
    """Teilmasse zwischen den Knicken und Winkelmasse in der Aufsicht."""
    if len(pl_pts) < 2:
        return
    st = station_table(pl_pts)
    ecken = corner_list(pl_pts)
    grenzen = [0.0] + [e['s'] for e in ecken] + [st[-1]]
    abstand = -sign * (U.cm(gab_fund_ueberstand_cm(p)) +
                       dim_abstand_units(p))
    cls = p['gab_prefix'] + 'BEM'
    for sa, sb in zip(grenzen, grenzen[1:]):
        if sb - sa <= 1e-9:
            continue
        pa, _ = point_at_station(pl_pts, st, sa)
        pb, _ = point_at_station(pl_pts, st, sb)
        dim_between(pa, pb, abstand,
                    'L = %.2f m' % U.to_m(sb - sa), cls, p)
    for i in range(1, len(pl_pts) - 1):
        draw_winkelmass(pl_pts[i - 1], pl_pts[i], pl_pts[i + 1], cls, p)


def kote_text(p, y_units):
    """Absolute Hoehe: Bezugshoehe + Abstand zum Bezugshoehenpunkt."""
    return '%.2f' % (p.get('ref_hoehe', 0.0)
                     + U.to_m(y_units - p.get('ref_y', 0.0)))


def bezugspunkt_ankern(p, elements):
    """Initiallage am linken Wandkopf setzen, spaetere Y-Lage bewahren."""
    if not p.get('ref_aktiv'):
        return None
    x, top_y = wall_reference.left_wall_top(elements)
    if not p.get('ref_anchor_initialized', False):
        p['ref_y'] = top_y
        p['ref_anchor_initialized'] = True
    return x, float(p.get('ref_y', top_y))


def draw_bezugspunkt(p, x, y):
    """Zeichnet den Bezugshoehenpunkt: waagerechte Bezugslinie mit Dreieck
    und Beschriftung. Er kann in der Zeichnung frei verschoben werden -
    beim Aktualisieren richtet sich die Kote nach seiner neuen Hoehe.
    Rueckgabe: Punkte der Bezugslinie (zum Wiederfinden)."""
    cls = p['prefix'] + 'KOTE'
    th = text_metrics(p)[0]
    laenge = th * 7.0
    x1 = x - laenge
    apply_attrs(cls, (0, 0, 0), False)
    _dline(x1, y, x, y, cls)
    # Die Dreiecksspitze liegt exakt am linken Wandkopf.
    d = th * 0.55
    make_filled_poly([(x - d, y + d), (x + d, y + d), (x, y)],
                     cls, (0, 0, 0))
    set_text_style(p['font'], p['font_size'])
    # rechtsbuendig am Linienende - so waechst der Text nach links und
    # ueberlagert die Ansicht nicht.
    make_text('BEZUGSHOEHE %.2f' % p.get('ref_hoehe', 0.0),
              x, y + th * 0.35, 0, 3, 4, cls)
    make_text('(verschieben und Mauer aktualisieren)',
              x, y - th * 0.45, 0, 3, 1, cls)
    return [(x1, y), (x, y)]


def draw_koten_abwicklung(elements, p):
    """OK und UK passend zur Parallel- oder Treppenform antragen."""
    cls = p['prefix'] + 'KOTE'
    th = text_metrics(p)[0]
    set_text_style(p['font'], p['font_size'])
    for e in elements:
        top = e.get('top_pts') or [(e['x0'], e['ytop']),
                                   (e['x1'], e['ytop'])]
        x = (e['x0'] + e['x1']) / 2.0
        y_top = y_on_top(top, x)
        # Abgetreppt: OK unmittelbar ueber der jeweiligen Stufenoberkante.
        # Parallel: bestehende kompakte Anordnung im unteren Wandfeld.
        y_ok = (e['ybot'] + th * 0.65 if e.get('parallel') else
                y_top + th * 0.55)
        y_uk = e['ybot'] - th * 0.75
        make_text('OK ' + kote_text(p, y_top),
                  x, y_ok, 0.0, 2, 2, cls, kollision=True)
        make_text('UK ' + kote_text(p, e['ybot']),
                  x, y_uk, 0.0, 2, 2, cls, kollision=True)


def draw_dims_abwicklung(elements, p):
    """Breiten als Masskette, Gesamtlaenge, Hoehe je Element."""
    cls = p['prefix'] + 'BEM'
    d = dim_abstand_units(p)
    fundamente = winkel_fundamente(elements, p)
    y_fund = min(q[1] for f in fundamente for q in f['basis_pts'])

    # Breite direkt IM zugehoerigen Element, ohne Masslinien
    th0 = text_metrics(p)[0]
    for e in elements:
        if e.get('sc') is not None and e['s0'] < e['sc'] < e['s1']:
            xc = e['x0'] + (e['sc'] - e['s0'])
            stuecke = ((e['x0'], xc), (xc, e['x1']))
        else:
            stuecke = ((e['x0'], e['x1']),)
        for xa, xb in stuecke:
            make_text('-%s-' % fmt_cm(U.to_cm(xb - xa)),
                      (xa + xb) / 2.0, e['ybot'] + th0 * 0.55, 0, 2, 2, cls)

    x_a = elements[0]['x0']
    x_b = elements[-1]['x1']
    # Die Laengenmasskette liegt vollstaendig unter der Fundamentsohle.
    dim_between((x_a, y_fund), (x_b, y_fund), -d,
                'L = %.2f m' % U.to_m(x_b - x_a), cls, p)

    # Fundamenttiefe und -dicke kompakt ausserhalb der Ansicht antragen.
    draw_fundament_staerken(fundamente, p,
                            p['prefix'] + 'FUNDAMENT-BEM')

    # Hoehe im Winkelstein: ohne Masslinien, dicht an der Kante,
    # zur Kenntlichmachung je ein Bindestrich davor und dahinter.
    th = text_metrics(p)[0]
    for e in elements:
        top = e.get('top_pts') or [(e['x0'], e['ytop']), (e['x1'], e['ytop'])]
        if e.get('parallel'):
            # Nur an der linken Kante - am Anschluss zum naechsten Element
            # ist die Hoehe dieselbe, es genuegt eine Angabe.
            paare = [(e['x0'] + th * 0.45, top[0][1], e.get('h_links_cm', 0))]
            if e is elements[-1]:
                paare.append((e['x1'] - th * 0.45, top[-1][1],
                              e.get('h_rechts_cm', 0)))
        else:
            # Nicht parallel: die tatsaechliche Ansichtshoehe des Gelaendes
            # bemassen, nicht die Bauhoehe des Winkelsteins.
            paare = ((e['x0'] + th * 0.45, e['ytop'],
                      e.get('gelaende_links_cm', e['h_cm'])),)
        for xs, yo, wert in paare:
            ym = (e['ybot'] + yo) / 2.0
            make_text('-%s-' % fmt_cm(wert), xs, ym, 90.0, 2, 2, cls)


def draw_dims_aufsicht_element(e, pa, pb, ux, uy, sign, p, erste_im_lauf,
                               erste_dieser_hoehe, laenge_cm=None):
    """Bemassung eines Elements (bzw. eines Eckschenkels) in der Aufsicht."""
    cls = p['prefix'] + 'BEM'
    nx, ny = -uy, ux

    # Laenge direkt IM zugehoerigen Element, dicht an die hintere Kante
    # der Fussflaeche geschoben - dort stoert sie die Quermasse nicht.
    th = text_metrics(p)[0]
    f_tiefe = U.cm(e.get('fuss_cm', 0.0))
    d_wand = U.cm(p['dicke_cm'])
    if f_tiefe > d_wand + th:
        tiefe = f_tiefe - th * 0.6
    else:
        tiefe = max(f_tiefe, d_wand) + th * 0.6
    mx = (pa[0] + pb[0]) / 2.0 + nx * sign * tiefe
    my = (pa[1] + pb[1]) / 2.0 + ny * sign * tiefe
    ang = math.degrees(math.atan2(uy, ux))
    if ang > 90.0:
        ang -= 180.0
    if ang < -90.0:
        ang += 180.0
    make_text('-%s-' % fmt_cm(laenge_cm if laenge_cm is not None
                              else e['width_cm']),
              mx, my, ang, 2, 2, cls)

    # Quermasse (Dicke, Fusslaenge) ebenfalls IM Bezugsobjekt, quer
    # zur Mauer geschrieben - ohne Masslinien.
    ang_n = math.degrees(math.atan2(ny * sign, nx * sign))
    if -90.0 <= ang_n <= 90.0:
        just_q, ang_q = 2, ang_n
    else:
        just_q = 2
        ang_q = ang_n - 180.0 if ang_n > 0 else ang_n + 180.0

    def quer(tiefe, wert, laengs):
        px = (pa[0] + ux * laengs + nx * sign * tiefe)
        py = (pa[1] + uy * laengs + ny * sign * tiefe)
        make_text('-%s-' % fmt_cm(wert), px, py, ang_q, just_q, 2, cls)

    # Mauerdicke im Mauerkoerper, dicht an der Anfangskante
    if erste_im_lauf:
        quer(U.cm(p['dicke_cm']) / 2.0, p['dicke_cm'], th * 0.35)

    # Fusslaenge auf der Fussflaeche, dicht an der Anfangskante daneben
    f_cm = e.get('fuss_cm', 0.0)
    if erste_dieser_hoehe and p.get('fuss_zeichnen') and f_cm > 0:
        # mittig im Fussbereich HINTER dem Mauerkoerper - so laeuft der Text
        # nicht durch die Elementbeschriftung im Mauerband.
        quer((d_wand + U.cm(f_cm)) / 2.0, f_cm, th * 1.15)


def force_attrs(h, cls, rgb=None, solid=False, lw=13):
    """Attribute am soeben erzeugten Objekt absichern.

    Der Zugriff erfolgt nur nach einer erfolgreichen Handle-Pruefung. Damit
    bleibt der Schutz gegen "Handle variable is NIL" erhalten, waehrend ein
    Neuaufbau keine aktive weisse Stift-/Textfarbe mehr uebernehmen kann.
    """
    if not HANDLES_USABLE or h is None:
        return False
    try:
        if not bool(h) or get_type(h) <= 0:
            return False
    except Exception:
        return False

    object_type = get_type(h)
    aufrufe = [('SetClass', (h, cls)),
               ('SetPenFore', (h, (0, 0, 0))),
               ('SetPenBack', (h, (0, 0, 0)))]
    # Meshes inherit their solid fill and pen weight from apply_attrs. The
    # object-level 2D calls below are invalid for type 40 and otherwise write
    # repeated errors into Vectorworks' Error Output document.
    if object_type != 40:
        aufrufe.extend([('SetFPat', (h, 1 if solid else 0)),
                        ('SetLW', (h, lw))])
    if rgb is not None:
        aufrufe.extend([('SetFillFore', (h, tuple(rgb))),
                        ('SetFillBack', (h, tuple(rgb)))])
    for fn, args in aufrufe:
        try:
            getattr(vs, fn)(*args)
        except Exception:
            pass
    return True


def force_text_style(h, txt, size_pt):
    """Arial und Punktgroesse am fertigen Textobjekt festschreiben.

    Die Objektformatierung erfolgt nach der Klassenzuweisung, damit eine
    vorhandene Klassen-Textformatierung die gewuenschten 8 pt nicht wieder
    ueberschreibt.
    """
    if not HANDLES_USABLE or h is None:
        return False
    try:
        if not bool(h) or get_type(h) <= 0:
            return False
    except Exception:
        return False
    anzahl = len(str(txt))
    if anzahl <= 0:
        return False
    size_pt = normalized_font_size(size_pt)
    try:
        vs.SetTextStyleRef(h, 0)       # Klassen-/Ressourcen-Textstil loesen
    except Exception:
        pass
    try:
        font_id = vs.GetFontID(TEXT_FONT)
    except Exception:
        font_id = None
    if font_id is not None and font_id >= 0:
        try:
            vs.SetTextFont(h, 0, anzahl, font_id)
        except Exception:
            pass
    try:
        vs.SetTextSize(h, 0, anzahl, size_pt)
    except Exception:
        return False
    try:
        vs.SetTextStyle(h, 0, anzahl, 0)  # Arial normal, nicht fett/kursiv
    except Exception:
        pass
    return True


def make_filled_poly(points, cls, rgb, opacity=None):
    """Geschlossenes, gefuelltes Polygon - Attribute ueber den Zeichenzustand
    und, falls moeglich, zusaetzlich ueber das Handle."""
    apply_attrs(cls, rgb, True)
    vs.ClosePoly()
    vs.Poly(*[c for p in points for c in p])
    h = _reg(vs.LNewObj())
    force_attrs(h, cls, rgb, True)
    if opacity is not None:
        set_obj_opacity(h, opacity)
    return h


def _klasse_3d(cls):
    return str(cls).rstrip('-') + '_3D'


def _layer_z_units():
    """Active design-layer elevation in the current drawing units."""
    try:
        millimetres = float(vs.GetLayerElevation(vs.ActLayer())[0])
    except Exception as exc:
        raise ValueError('Die Ebenenhoehe fuer den 3D-Koerper ist nicht lesbar.') from exc
    value = millimetres / 1000.0 * U.factor
    if not math.isfinite(value):
        raise ValueError('Die Ebenenhoehe fuer den 3D-Koerper ist ungueltig.')
    return value


def _z3d(p, y_units):
    """Elevation-profile ordinate to local Vectorworks layer Z."""
    y_units = float(y_units)
    if p.get('ref_aktiv'):
        absolute = (float(p.get('ref_hoehe', 0.0)) * U.factor +
                    y_units - float(p.get('ref_y', 0.0)))
    else:
        absolute = y_units
    return absolute - _layer_z_units()


def make_chamfered_mesh(points, z_bottom, z_top, cls, rgb, opacity=None,
                        profile=None):
    """Create one closed native mesh with a 5×5 mm chamfer on every edge.

    ``profile`` optionally supplies ``(line_a, line_b, bottom_a, bottom_b,
    top_a, top_b)``. This maps the already chamfered prism onto a linear
    sloping wall/foundation profile without changing its plan footprint.
    """
    chamfer = U.cm(CHAMFER_CM)
    nominal_bottom, nominal_top = float(z_bottom), float(z_top)
    faces = pd_chamfer.prism_faces(points, nominal_bottom, nominal_top, chamfer)
    if profile is not None:
        line_a, line_b, bottom_a, bottom_b, top_a, top_b = profile
        dx, dy = line_b[0] - line_a[0], line_b[1] - line_a[1]
        length2 = dx * dx + dy * dy
        if length2 <= 1e-12:
            raise ValueError('Ein 3D-Wandabschnitt besitzt keine Laenge.')
        height = nominal_top - nominal_bottom
        transformed = []
        for face in faces:
            changed = []
            for x, y, z in face:
                station = max(0.0, min(1.0,
                    ((x - line_a[0]) * dx + (y - line_a[1]) * dy) / length2))
                bottom = bottom_a + (bottom_b - bottom_a) * station
                top = top_a + (top_b - top_a) * station
                fraction = (z - nominal_bottom) / height
                changed.append((x, y, bottom + (top - bottom) * fraction))
            transformed.append(tuple(changed))
        faces = tuple(transformed)
    apply_attrs(cls, rgb, True)
    h = pd_chamfer.create_mesh(vs, faces)
    _reg(h)
    force_attrs(h, cls, rgb, True)
    if opacity is not None:
        set_obj_opacity(h, opacity)
    return h


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

# Item-IDs
I_OK, I_CANCEL = 1, 2
(I_ACTION_L, I_ACTION, I_UNIT_L, I_UNIT, I_UO_L, I_UO, I_UU_L, I_UU,
 I_BR_L, I_BR, I_BRF, I_PMIN_L, I_PMIN, I_PLAGE_L, I_PLAGE,
 I_HMODE_L, I_HMODE, I_SEP1, I_DICKE_L, I_DICKE, I_DICKEF,
 I_SEITE_L, I_SEITE, I_AUFS, I_REV, I_REF, I_REFV, I_SEP2,
 I_FONT_L, I_FONT, I_FSIZE_L, I_FSIZE, I_ROT, I_SEP3,
 I_PREFIX_L, I_PREFIX, I_TOL_L, I_TOL, I_HEIGHTS_L, I_HEIGHTS,
 I_WS, I_TAB, I_HINT, I_FUSS, I_FUSSLS_L, I_FUSSLS, I_FARBEN,
 I_BEM, I_BEMD_L, I_BEMD, I_TRANS_L, I_TRANS,
 I_ECK_L, I_ECK, I_OKA_L, I_OKA, I_EINZEL,
 I_LUK_L, I_LUK, I_LOK_L, I_LOK, I_LPL_L, I_LPL, I_KLICK,
 I_REFSEL, I_ECKST, I_REFHINT, I_TYP_L, I_TYP,
 I_EBENE, I_EBNAME_L, I_EBNAME, I_EBMST_L, I_EBMST,
 I_FARBM_L, I_FARBM, I_STUFE_L, I_STUFE,
 I_SEPA, I_SEPB, I_SEPC, I_SEPD, I_TITEL,
 I_SEPG, I_GLEN_L, I_GLEN, I_GLAG_L, I_GLAG, I_GEIN_L, I_GEIN,
 I_GUEB_L, I_GUEB, I_GSTAF_L, I_GSTAF, I_GBR_L, I_GBR,
 I_GSCH_L, I_GSCH, I_GMIN_L, I_GMIN, I_SEPK,
 I_WFUND_U_L, I_WFUND_U, I_WFUND_T_L, I_WFUND_T) = range(10, 115)
I_LOGO, I_GFUND_T_L, I_GFUND_T, I_FUSS_ST_L, I_FUSS_ST = range(115, 120)
(I_KAT_H_L, I_KAT_H, I_KAT_F_L, I_KAT_F,
 I_KAT_ADD, I_KAT_CHANGE, I_KAT_DEL) = range(120, 127)
(I_GAB_B_L, I_GAB_B, I_GAB_ADD,
 I_GAB_CHANGE, I_GAB_DEL) = range(127, 132)
(I_TABS, I_TAB_GRUND, I_TAB_WINKEL,
 I_TAB_GABIONE, I_TAB_AUSGABE) = range(132, 137)
I_REFV_L = 137
I_GFUND_U_L, I_GFUND_U = range(138, 140)
(I_KAT_C_L, I_KAT_C, I_GAB_C_L, I_GAB_C,
 I_FUND_C_L, I_FUND_C) = range(140, 146)
I_DRAW_3D = 146

_dlg_values = {}
_dlg_settings = {}
_pd_choices = {}          # Item-ID -> Liste der Auswahleintraege
_ref_liste = []           # zuletzt benutzte Bezugshoehen
_kataloge = {}            # Typ -> Katalogliste (fuer die Umschaltung)

AKTIONEN_WINKEL = [
    'Neue Mauer aus zuvor ausgewaehlten Linien',
    'Ausgewaehlte Mauer aktualisieren',
    'Alle Mauern aktualisieren',
    'Nur Bezugshoehe aendern (Auswahl)',
    'Nur Bezugshoehe aendern (alle Mauern)',
    'Winkelstein-Einzelschnitt an Station',
    'Winkelstein-Systemschnitte bei Bauweisenwechsel',
]
AKTIONEN_GABIONE = [
    'Neue Mauer aus zuvor ausgewaehlten Linien',
    'Ausgewaehlte Mauer aktualisieren',
    'Alle Mauern aktualisieren',
    'Nur Bezugshoehe aendern (Auswahl)',
    'Nur Bezugshoehe aendern (alle Mauern)',
    'Gabionen-Einzelschnitt an Station',
    'Gabionen-Systemschnitte bei Bauweisenwechsel',
]


def dialog_actionen_setzen(dlg, typ):
    """Eigenes Aktionsmenue fuer Winkelsteine bzw. Gabionen."""
    try:
        for _i in range(10):
            vs.RemoveChoice(dlg, I_ACTION, 0)
        for i, text in enumerate(AKTIONEN_GABIONE if typ == TYP_GABIONE
                                 else AKTIONEN_WINKEL):
            vs.AddChoice(dlg, I_ACTION, text, i)
        vs.SelectChoice(dlg, I_ACTION, 0, True)
        dialog_schnittfeld_setzen(dlg, 0)
    except Exception:
        pass


def dialog_schnittfeld_setzen(dlg, action):
    """Numerische Station nur beim Einzelschnitt aktivieren."""
    for iid in (I_GSCH_L, I_GSCH):
        try:
            vs.EnableItem(dlg, iid, int(action) == 5)
        except Exception:
            pass


def dialog_auswahl(dlg, item, fallback=0):
    try:
        wert = vs.GetSelectedChoiceIndex(dlg, item, 0)
    except Exception:
        return fallback
    return fallback if wert is None or wert < 0 else int(wert)


def dialog_tab_anzeigen(dlg, nummer):
    """Einen der vier Reiter anzeigen; Nummerierung ist 1-basiert."""
    try:
        vs.DisplayTabPane(dlg, I_TABS, int(nummer))
    except Exception:
        pass


def dialog_abhaengigkeiten_setzen(dlg):
    """Nur Eingaben aktivieren, die mit der aktuellen Auswahl wirksam sind."""
    typ = dialog_auswahl(dlg, I_TYP, 0)
    action = dialog_auswahl(dlg, I_ACTION, 0)
    winkel = typ != TYP_GABIONE
    aufsicht = bool(vs.GetBooleanItem(dlg, I_AUFS))

    zustand = {
        I_GSCH_L: action == 5,
        I_GSCH: action == 5,
        I_BRF: winkel and dialog_auswahl(dlg, I_BR, 0) == 2,
        I_SEITE_L: aufsicht,
        I_SEITE: aufsicht,
        I_REV: aufsicht,
        I_DICKE_L: winkel and aufsicht,
        I_DICKE: winkel and aufsicht,
        I_DICKEF: (winkel and aufsicht and
                   dialog_auswahl(dlg, I_DICKE, 2) == 4),
        I_DRAW_3D: aufsicht,
        I_OKA_L: winkel and dialog_auswahl(dlg, I_HMODE, 0) == 3,
        I_OKA: winkel and dialog_auswahl(dlg, I_HMODE, 0) == 3,
        I_FUSS: winkel and aufsicht,
        I_FUSSLS_L: (winkel and aufsicht and
                     bool(vs.GetBooleanItem(dlg, I_FUSS))),
        I_FUSSLS: (winkel and aufsicht and
                   bool(vs.GetBooleanItem(dlg, I_FUSS))),
        I_BEMD_L: bool(vs.GetBooleanItem(dlg, I_BEM)),
        I_BEMD: bool(vs.GetBooleanItem(dlg, I_BEM)),
        I_EBNAME_L: bool(vs.GetBooleanItem(dlg, I_EBENE)),
        I_EBNAME: bool(vs.GetBooleanItem(dlg, I_EBENE)),
        I_EBMST_L: bool(vs.GetBooleanItem(dlg, I_EBENE)),
        I_EBMST: bool(vs.GetBooleanItem(dlg, I_EBENE)),
    }
    bezug = bool(vs.GetBooleanItem(dlg, I_REF)) or action in (3, 4)
    for iid in (I_SEP2, I_REFV_L, I_REFV, I_REFSEL, I_REFHINT):
        zustand[iid] = bezug
    for iid, aktiv in zustand.items():
        try:
            vs.EnableItem(dlg, iid, aktiv)
        except Exception:
            pass


def dialog_eingaben_pruefen(dlg, typ, action):
    """Aktionsbezogene Zahlenpruefung mit einer konkreten Korrekturmeldung."""
    def pruefe(item, bezeichnung, minimum=None, null_erlaubt=True,
               maximum=None):
        try:
            text = vs.GetItemText(dlg, item).strip().replace(',', '.')
            wert = float(text)
        except Exception:
            wert = float('nan')
        falsch = not math.isfinite(wert)
        if minimum is not None:
            falsch = falsch or wert < minimum
            if not null_erlaubt:
                falsch = falsch or wert <= minimum
        if maximum is not None:
            falsch = falsch or wert > maximum
        if not falsch:
            return True
        grenze = ''
        if minimum is not None:
            grenze = (' (mindestens %g)' if null_erlaubt else
                      ' (groesser als %g)') % minimum
        if maximum is not None:
            grenze += ' (hoechstens %g)' % maximum
        vs.AlrtDialog('Eingabe pruefen:\n\n%s muss eine gueltige Zahl sein%s.' %
                      (bezeichnung, grenze))
        try:
            vs.SelectEditText(dlg, item)
        except Exception:
            pass
        return False

    # Bezugshoehenaktionen benoetigen keine Geometrieparameter.
    if action in (3, 4):
        return pruefe(I_REFV, 'Bezugshoehe [m]')
    if action == 5 and not pruefe(
            I_GSCH, 'Schnitt-Station [m]', 0.0, False):
        return False

    if vs.GetBooleanItem(dlg, I_BEM) and not pruefe(
            I_BEMD, 'Abstand der Masslinie [cm]', 0.0):
        return False
    if not pruefe(I_FSIZE, 'Schrifthoehe [pt]', 0.0, False):
        return False
    if not pruefe(I_TRANS, 'Transparenz Fuellung [%]', 0.0, True, 100.0):
        return False

    # Update- und Schnittaktionen verwenden die Geometrie des Bestands.
    if action != 0:
        return True
    if vs.GetBooleanItem(dlg, I_EBENE) and not pruefe(
            I_EBMST, 'Massstab der Konstruktionsebene', 0.0, False):
        return False

    if typ == TYP_GABIONE:
        felder = (
            (I_GLEN, 'Regellaenge einer Gabione [m]', 0.0, False),
            (I_GLAG, 'Hoehe einer Gabionenlage [m]', 0.0, False),
            (I_GEIN, 'Einbindetiefe unter UK [m]', 0.0, True),
            (I_GUEB, 'Ueberstand ueber Gelaende [m]', 0.0, True),
            (I_GSTAF, 'Mindest-Abstaffelung OK [m]', 0.0, True),
            (I_GMIN, 'Mindesthoehe unterste Lage [m]', 0.0, True),
            (I_GFUND_U, 'Fundamentueberstand [cm]', 0.0, True),
            (I_GFUND_T, 'Fundamentsohle unter UK Gelaende [cm]', 0.0, False),
        )
        for item, name, minimum, null_erlaubt in felder:
            if not pruefe(item, name, minimum, null_erlaubt):
                return False
        if _f(dlg, I_GMIN, 0.0) > _f(dlg, I_GLAG, 0.0):
            vs.AlrtDialog('Eingabe pruefen:\n\nDie Mindesthoehe der untersten '
                          'Lage darf nicht groesser als die Hoehe einer '
                          'Gabionenlage sein.')
            return False
        return True

    felder = (
        (I_UO, 'Ueberstand ueber OK [cm]', 0.0, True),
        (I_UU, 'Tiefe unter UK [cm]', 0.0, True),
        (I_PMIN, 'Mindestbreite Pass [cm]', 0.0, False),
        (I_TOL, 'Laengentoleranz [cm]', 0.0, True),
        (I_ECK, 'Eckschenkel je Seite [cm]', 0.0, False),
        (I_WFUND_U, 'Fundament-Ueberstand v/h [cm]', 0.0, True),
        (I_WFUND_T, 'Fundamentsohle unter UK Gelaende [cm]', 0.0, False),
        (I_FUSS_ST, 'Staerke Winkelsteinfuss [cm]', 0.0, False),
    )
    for item, name, minimum, null_erlaubt in felder:
        if not pruefe(item, name, minimum, null_erlaubt):
            return False
    if dialog_auswahl(dlg, I_BR, 0) == 2 and not pruefe(
            I_BRF, 'Freie Elementlaenge [cm]', 0.0, False):
        return False
    if dialog_auswahl(dlg, I_DICKE, 2) == 4 and not pruefe(
            I_DICKEF, 'Freie Mauerdicke [cm]', 0.0, False):
        return False
    if dialog_auswahl(dlg, I_HMODE, 0) == 3 and not pruefe(
            I_OKA, 'Parallelabstand zur OK [cm]', 0.0, True):
        return False
    return True


def _f(dlg, item, default=0.0):
    """Zahl aus einem Eingabefeld lesen (Komma erlaubt)."""
    try:
        t = vs.GetItemText(dlg, item).strip().replace(',', '.')
        return float(t)
    except Exception:
        return default


def katalog_normalisieren(katalog):
    """Katalogzeilen vereinheitlichen und Hoehen eindeutig sortieren."""
    zeilen = {}
    for eintrag in katalog or []:
        try:
            h = float(eintrag[0])
            fuss = float(eintrag[1])
        except Exception:
            continue
        if not math.isfinite(h) or not math.isfinite(fuss) or h <= 0:
            continue
        farbe = str(eintrag[2] or '') if len(eintrag) > 2 else ''
        bemerkung = str(eintrag[3] or '') if len(eintrag) > 3 else ''
        zeilen[round(h, 6)] = (h, fuss, farbe, bemerkung)
    return sorted(zeilen.values(), key=lambda e: e[0])


def dialog_katalog_holen(typ):
    """Dialogkopie des typgetrennten Winkelstein-Katalogs liefern."""
    typ = int(typ)
    kataloge = _dlg_values.setdefault('catalogs', {})
    if typ not in kataloge:
        kataloge[typ] = katalog_normalisieren(
            _kataloge.get(typ) or load_catalog(typ, _dlg_settings))
    return kataloge[typ]


def dialog_katalog_spalten(dlg):
    """Die drei Spalten des Katalog-List-Browsers einmalig einrichten."""
    if _dlg_values.get('catalog_columns'):
        return
    try:
        vs.InsertLBColumn(dlg, I_HEIGHTS, 0, 'Hoehe [cm]', 85)
        vs.InsertLBColumn(dlg, I_HEIGHTS, 1, 'Fusslaenge [cm]', 115)
        vs.InsertLBColumn(dlg, I_HEIGHTS, 2, 'Farbe', 82)
        for spalte in (0, 1, 2):
            vs.SetLBControlType(dlg, I_HEIGHTS, spalte, 1)  # Nur Anzeige
            vs.SetLBItemDisplayType(dlg, I_HEIGHTS, spalte, 0)
        vs.EnableLBColumnLines(dlg, I_HEIGHTS, True)
        vs.EnableLBSingleLineSelection(dlg, I_HEIGHTS, True)
        vs.EnableLBSorting(dlg, I_HEIGHTS, False)
    except Exception:
        pass
    _dlg_values['catalog_columns'] = True


def dialog_katalog_anzeigen(dlg, typ, auswahl=None):
    """Katalog eines Winkelsteintyps in die dreispaltige Tabelle laden."""
    katalog = dialog_katalog_holen(typ)
    try:
        vs.EnableLBUpdates(dlg, I_HEIGHTS, False)
        vs.DeleteAllLBItems(dlg, I_HEIGHTS)
        for nr, (h, fuss, farbe, _bemerkung) in enumerate(katalog):
            zeile = vs.InsertLBItem(dlg, I_HEIGHTS, nr, '%g' % h)
            if not isinstance(zeile, int) or zeile < 0:
                zeile = nr
            vs.SetLBItemInfo(dlg, I_HEIGHTS, zeile, 1, '%g' % fuss, -1)
            vs.SetLBItemInfo(dlg, I_HEIGHTS, zeile, 2,
                             color_token(farbe, h), -1)
        if auswahl is not None and 0 <= auswahl < len(katalog):
            vs.SetLBSelection(dlg, I_HEIGHTS, auswahl, auswahl, True)
            vs.EnsureLBItemIsVisible(dlg, I_HEIGHTS, auswahl)
        vs.EnableLBUpdates(dlg, I_HEIGHTS, True)
    except Exception:
        try:
            vs.EnableLBUpdates(dlg, I_HEIGHTS, True)
        except Exception:
            pass
    _dlg_values['catalog_typ'] = int(typ)


def dialog_katalog_auswahl(dlg, typ):
    """Index der ausgewaehlten Katalogzeile oder None."""
    for nr in range(len(dialog_katalog_holen(typ))):
        try:
            if vs.IsLBItemSelected(dlg, I_HEIGHTS, nr):
                return nr
        except Exception:
            break
    return None


def dialog_katalog_eingabe(dlg):
    """Positive Hoehe und Fusslaenge aus den Katalogfeldern lesen."""
    h = _f(dlg, I_KAT_H, -1.0)
    fuss = _f(dlg, I_KAT_F, -1.0)
    if (not math.isfinite(h) or not math.isfinite(fuss) or
            h <= 0 or fuss <= 0):
        vs.AlrtDialog('Bitte fuer Hoehe und Fusslaenge positive Zahlen '
                      'in Zentimetern eingeben.')
        return None
    return h, fuss


def dialog_katalog_markieren(dlg, typ, h):
    """Tabelle neu laden und die Zeile der angegebenen Hoehe markieren."""
    katalog = dialog_katalog_holen(typ)
    nr = next((i for i, e in enumerate(katalog)
               if abs(e[0] - h) <= 1e-6), None)
    dialog_katalog_anzeigen(dlg, typ, nr)


def dialog_katalog_hinzufuegen(dlg, typ):
    werte = dialog_katalog_eingabe(dlg)
    if werte is None:
        return
    h, fuss = werte
    katalog = dialog_katalog_holen(typ)
    if any(abs(e[0] - h) <= 1e-6 for e in katalog):
        vs.AlrtDialog('Die Hoehe %g cm ist bereits vorhanden.\n\n'
                      'Bitte die vorhandene Zeile markieren und '
                      '"Auswahl aendern" verwenden.' % h)
        return
    vorgaben = dict((float(vh), farbe)
                    for vh, _vf, farbe in katalog_vorgabe(typ))
    farbe = dialog_farbe_lesen(
        dlg, I_KAT_C, vorgaben.get(float(h), ''), h)
    katalog.append((h, fuss, farbe,
                     'Benutzerdefiniert'))
    katalog[:] = katalog_normalisieren(katalog)
    _kataloge[int(typ)] = list(katalog)
    _dlg_values.setdefault('catalog_dirty', set()).add(int(typ))
    dialog_katalog_markieren(dlg, typ, h)


def dialog_katalog_aendern(dlg, typ):
    nr = dialog_katalog_auswahl(dlg, typ)
    if nr is None:
        vs.AlrtDialog('Bitte zuerst eine Katalogzeile markieren.')
        return
    werte = dialog_katalog_eingabe(dlg)
    if werte is None:
        return
    h, fuss = werte
    katalog = dialog_katalog_holen(typ)
    if any(i != nr and abs(e[0] - h) <= 1e-6
           for i, e in enumerate(katalog)):
        vs.AlrtDialog('Die Hoehe %g cm ist bereits vorhanden.' % h)
        return
    _alt_h, _alt_fuss, farbe, bemerkung = katalog[nr]
    farbe = dialog_farbe_lesen(dlg, I_KAT_C, farbe, h)
    katalog[nr] = (h, fuss, farbe, bemerkung or 'Benutzerdefiniert')
    katalog[:] = katalog_normalisieren(katalog)
    _kataloge[int(typ)] = list(katalog)
    _dlg_values.setdefault('catalog_dirty', set()).add(int(typ))
    dialog_katalog_markieren(dlg, typ, h)


def dialog_katalog_entfernen(dlg, typ):
    nr = dialog_katalog_auswahl(dlg, typ)
    if nr is None:
        vs.AlrtDialog('Bitte zuerst eine Katalogzeile markieren.')
        return
    katalog = dialog_katalog_holen(typ)
    if len(katalog) <= 1:
        vs.AlrtDialog('Mindestens eine Winkelsteingroesse muss im Katalog '
                      'verbleiben.')
        return
    del katalog[nr]
    _kataloge[int(typ)] = list(katalog)
    _dlg_values.setdefault('catalog_dirty', set()).add(int(typ))
    vs.SetItemText(dlg, I_KAT_H, '')
    vs.SetItemText(dlg, I_KAT_F, '')
    dialog_farbe_setzen(dlg, I_KAT_C, '#808080')
    dialog_katalog_anzeigen(dlg, typ, min(nr, len(katalog) - 1))


def dialog_gab_breiten_holen():
    """Dialogkopie der Gabionenbreiten von oben nach unten liefern."""
    if 'gab_breiten_liste' not in _dlg_values:
        text = (_dlg_settings.get('gab_breiten', '')
                if _dlg_settings.get('gab_catalog_custom')
                else DEFAULTS['gab_breiten'])
        werte = gab_tabelle(text)
        if not werte:
            werte = gab_breiten_laden(_dlg_settings)
        _dlg_values['gab_breiten_liste'] = [float(v) for v in werte]
    return _dlg_values['gab_breiten_liste']


def dialog_gab_farben_holen():
    """Manuelle Gabionenfarben, nach Breite in Zentimetern geordnet."""
    if 'gab_colors' not in _dlg_values:
        quelle = (_dlg_settings.get('gab_colors', DEFAULT_GAB_COLORS)
                  if _dlg_settings.get('gab_catalog_custom')
                  else DEFAULT_GAB_COLORS)
        quelle = quelle if isinstance(quelle, dict) else {}
        farben = {}
        for nr, breite in enumerate(dialog_gab_breiten_holen()):
            key = str(int(round(breite)))
            fallback = DEFAULT_GAB_COLORS.get(key)
            if not fallback:
                fallback = color_hex(hsv_rgb(
                    (0.61803398875 * nr) % 1.0, 0.62, 0.88))
            farben[key] = color_token(quelle.get(key, fallback), breite)
        _dlg_values['gab_colors'] = farben
    return _dlg_values['gab_colors']


def dialog_gab_spalten(dlg):
    """Spalten der Gabionen-Lagentabelle einmalig einrichten."""
    if _dlg_values.get('gab_columns'):
        return
    try:
        vs.InsertLBColumn(dlg, I_GBR, 0, 'Lage', 45)
        vs.InsertLBColumn(dlg, I_GBR, 1, 'Hoehenbereich [m]', 110)
        vs.InsertLBColumn(dlg, I_GBR, 2, 'Breite [cm]', 80)
        vs.InsertLBColumn(dlg, I_GBR, 3, 'Farbe', 82)
        for spalte in (0, 1, 2, 3):
            vs.SetLBControlType(dlg, I_GBR, spalte, 1)  # Nur Anzeige
            vs.SetLBItemDisplayType(dlg, I_GBR, spalte, 0)
        vs.EnableLBColumnLines(dlg, I_GBR, True)
        vs.EnableLBSingleLineSelection(dlg, I_GBR, True)
        vs.EnableLBSorting(dlg, I_GBR, False)
    except Exception:
        pass
    _dlg_values['gab_columns'] = True


def dialog_gab_tabelle_anzeigen(dlg, lagenhoehe=None, auswahl=None):
    """Breiten und die aus der Lagenhoehe berechneten Bereiche anzeigen."""
    breiten = dialog_gab_breiten_holen()
    farben = dialog_gab_farben_holen()
    if lagenhoehe is None:
        lagenhoehe = _f(dlg, I_GLAG, 0.5)
    lagenhoehe = max(0.0, float(lagenhoehe))
    try:
        vs.EnableLBUpdates(dlg, I_GBR, False)
        vs.DeleteAllLBItems(dlg, I_GBR)
        for nr, breite in enumerate(breiten):
            zeile = vs.InsertLBItem(dlg, I_GBR, nr, str(nr + 1))
            if not isinstance(zeile, int) or zeile < 0:
                zeile = nr
            von = nr * lagenhoehe
            bis = (nr + 1) * lagenhoehe
            vs.SetLBItemInfo(dlg, I_GBR, zeile, 1,
                             '%.2f - %.2f' % (von, bis), -1)
            vs.SetLBItemInfo(dlg, I_GBR, zeile, 2, '%g' % breite, -1)
            vs.SetLBItemInfo(dlg, I_GBR, zeile, 3,
                             farben.get(str(int(round(breite))), '#808080'),
                             -1)
        if auswahl is not None and 0 <= auswahl < len(breiten):
            vs.SetLBSelection(dlg, I_GBR, auswahl, auswahl, True)
            vs.EnsureLBItemIsVisible(dlg, I_GBR, auswahl)
        vs.EnableLBUpdates(dlg, I_GBR, True)
    except Exception:
        try:
            vs.EnableLBUpdates(dlg, I_GBR, True)
        except Exception:
            pass


def dialog_gab_auswahl(dlg):
    """Index der ausgewaehlten Gabionenlage oder None."""
    for nr in range(len(dialog_gab_breiten_holen())):
        try:
            if vs.IsLBItemSelected(dlg, I_GBR, nr):
                return nr
        except Exception:
            break
    return None


def dialog_gab_breite_eingabe(dlg):
    breite = _f(dlg, I_GAB_B, -1.0)
    if not math.isfinite(breite) or breite <= 0:
        vs.AlrtDialog('Bitte eine positive Gabionenbreite in Zentimetern '
                      'eingeben.')
        return None
    return breite


def dialog_gab_hinzufuegen(dlg):
    breite = dialog_gab_breite_eingabe(dlg)
    if breite is None:
        return
    breiten = dialog_gab_breiten_holen()
    nr = dialog_gab_auswahl(dlg)
    nr = len(breiten) if nr is None else nr + 1
    breiten.insert(nr, breite)
    key = str(int(round(breite)))
    farben = dialog_gab_farben_holen()
    farben[key] = dialog_farbe_lesen(
        dlg, I_GAB_C, farben.get(key, '#808080'), breite)
    _dlg_values['gab_dirty'] = True
    dialog_gab_tabelle_anzeigen(dlg, auswahl=nr)


def dialog_gab_aendern(dlg):
    nr = dialog_gab_auswahl(dlg)
    if nr is None:
        vs.AlrtDialog('Bitte zuerst eine Gabionenlage markieren.')
        return
    breite = dialog_gab_breite_eingabe(dlg)
    if breite is None:
        return
    alt = dialog_gab_breiten_holen()[nr]
    dialog_gab_breiten_holen()[nr] = breite
    farben = dialog_gab_farben_holen()
    alt_key = str(int(round(alt)))
    key = str(int(round(breite)))
    farben[key] = dialog_farbe_lesen(
        dlg, I_GAB_C, farben.get(alt_key, '#808080'), breite)
    _dlg_values['gab_dirty'] = True
    dialog_gab_tabelle_anzeigen(dlg, auswahl=nr)


def dialog_gab_entfernen(dlg):
    nr = dialog_gab_auswahl(dlg)
    if nr is None:
        vs.AlrtDialog('Bitte zuerst eine Gabionenlage markieren.')
        return
    breiten = dialog_gab_breiten_holen()
    if len(breiten) <= 1:
        vs.AlrtDialog('Mindestens eine Gabionenlage muss in der Tabelle '
                      'verbleiben.')
        return
    del breiten[nr]
    _dlg_values['gab_dirty'] = True
    vs.SetItemText(dlg, I_GAB_B, '')
    dialog_farbe_setzen(dlg, I_GAB_C, '#808080')
    dialog_gab_tabelle_anzeigen(dlg, auswahl=min(nr, len(breiten) - 1))


def dialog_handler(item, data):
    dlg = _dlg_values.get('dlg')
    s = _dlg_settings

    if item == 12255:                              # Dialog initialisieren
        # WICHTIG: Klappmenues muessen im Setup-Ereignis gefuellt werden.
        # Vor RunLayoutDialog hinzugefuegte Eintraege werden verworfen.
        for iid, choices in _pd_choices.items():
            for k, c in enumerate(choices):
                try:
                    vs.AddChoice(dlg, iid, c, k)
                except Exception:
                    pass
        try:
            pfad = logo_pfad()
            if pfad:
                vs.UpdateImageControl3(dlg, I_LOGO, pfad)
        except Exception:
            pass
        for iid, stil in ((I_TITEL, 1), (I_TYP_L, 1), (I_ACTION_L, 1)):
            try:
                vs.SetStaticTextStyle(dlg, iid, stil)
            except Exception:
                pass
        vs.SetBooleanItem(dlg, I_EBENE, s.get('ebene_aktiv', True))
        vs.SetItemText(dlg, I_EBNAME, s.get('ebene_name', 'Winkelstützmauer'))
        vs.SetItemText(dlg, I_EBMST, '%g' % s.get('ebene_massstab', 25.0))
        dialog_katalog_spalten(dlg)
        dialog_gab_spalten(dlg)
        vs.SetItemText(dlg, I_GLEN, '%g' % s.get('gab_laenge', 2.0))
        vs.SetItemText(dlg, I_GLAG, '%g' % s.get('gab_lage', 0.5))
        vs.SetItemText(dlg, I_GEIN, '%g' % s.get('gab_einbinde', 0.3))
        vs.SetItemText(dlg, I_GUEB, '%g' % s.get('gab_ueber', 0.2))
        vs.SetItemText(dlg, I_GSTAF, '%g' % s.get('gab_staffel', 0.5))
        vs.SetItemText(dlg, I_GMIN, '%g' % s.get('gab_lage_min', 0.25))
        vs.SetItemText(dlg, I_GSCH, '%g' % s.get('schnitt_station', 5.0))
        vs.SetItemText(dlg, I_GFUND_T, '%g' % s.get(
            'gab_fund_tiefe', GAB_FUND_TIEFE_CM))
        vs.SetItemText(dlg, I_GFUND_U, '%g' % s.get(
            'gab_fund_ueberstand', GAB_FUND_UEBERSTAND_CM))
        dialog_gab_tabelle_anzeigen(
            dlg, float(s.get('gab_lage', 0.5) or 0.5))
        vs.SetItemText(dlg, I_UO, '%g' % s['ueber_ok'])
        vs.SetItemText(dlg, I_UU, '%g' % s['unter_uk'])
        vs.SetItemText(dlg, I_WFUND_U, '%g' % s.get(
            'fund_ueberstand', WINKEL_FUND_UEBERSTAND_CM))
        vs.SetItemText(dlg, I_WFUND_T, '%g' % s.get(
            'fund_tiefe', WINKEL_FUND_TIEFE_CM))
        vs.SetItemText(dlg, I_FUSS_ST, '%g' % s.get(
            'winkel_fuss_staerke', 15.0))
        vs.SetItemText(dlg, I_BRF, '%g' % s['breite_frei'])
        vs.SetItemText(dlg, I_PMIN, '%g' % s['pass_min'])
        vs.SetItemText(dlg, I_ECK, '%g' % s.get('eck_schenkel', 50.0))
        vs.SetBooleanItem(dlg, I_ECKST, s.get('ecke_abstufen', False))
        vs.SetItemText(dlg, I_STUFE, '%g' % s.get('stufe_min', 0.0))
        vs.SetItemText(dlg, I_OKA, '%g' % s.get('ok_abstand', 10.0))
        vs.SetBooleanItem(dlg, I_EINZEL, s.get('einzelliste', True))
        vs.SetItemText(dlg, I_DICKEF, '%g' % s['dicke_frei'])
        vs.SetItemText(dlg, I_REFV, '%.3f' % s['ref_hoehe'])
        vs.SetItemText(dlg, I_FONT, TEXT_FONT)
        vs.EnableItem(dlg, I_FONT, False)
        vs.SetItemText(dlg, I_FSIZE, '%g' % normalized_font_size(
            s.get('font_size', TEXT_DEFAULT_SIZE)))
        vs.SetItemText(dlg, I_PREFIX, s.get('winkel_prefix', 'PD-MWL-'))
        vs.SetItemText(dlg, I_TOL, '%g' % s['toleranz'])
        vs.SetBooleanItem(dlg, I_AUFS, s['aufsicht'])
        vs.SetBooleanItem(dlg, I_DRAW_3D, s.get('draw_3d', True))
        vs.SetBooleanItem(dlg, I_REV, s['aufsicht_umkehren'])
        vs.SetBooleanItem(dlg, I_REF, s['ref_aktiv'])
        vs.SetBooleanItem(dlg, I_ROT, s['txt_rot'])
        vs.SetBooleanItem(dlg, I_WS, s['ws_tabelle'])
        vs.SetBooleanItem(dlg, I_TAB, s['zeichnungs_tabelle'])
        vs.SetBooleanItem(dlg, I_FUSS, s['fuss_zeichnen'])
        vs.SetBooleanItem(dlg, I_FARBEN, s.get('farben_neu', False))
        vs.SetBooleanItem(dlg, I_BEM, s.get('bemassung', True))
        vs.SetItemText(dlg, I_BEMD, '%g' % s.get('dim_abstand', 60.0))
        vs.SetItemText(dlg, I_TRANS, '%g' % s.get('transparenz', 50.0))
        vs.SetItemText(dlg, I_FUSSLS, s['fuss_ls'])
        dialog_farbe_setzen(
            dlg, I_FUND_C, s.get('fundament_farbe', DEFAULT_FUNDAMENT_FARBE))
        dialog_farbe_setzen(dlg, I_KAT_C, '#808080')
        dialog_farbe_setzen(dlg, I_GAB_C, '#808080')
        for iid, val in ((I_ACTION, 0),
                         (I_TYP, int(s.get('stein_typ', 0))),
                         (I_FARBM, int(s.get('farb_modus', 0))),
                         (I_UNIT, {'m': 0, 'cm': 1, 'mm': 2}.get(s['unit'], 0)),
                         (I_BR, s['breite_mode']),
                         (I_PLAGE, s['pass_lage']),
                         (I_HMODE, s['hoehen_mode']),
                         (I_DICKE, s['dicke_mode']),
                         (I_SEITE, s['seite'])):
            try:
                vs.SelectChoice(dlg, iid, val, True)
            except Exception:
                pass
        # Die typabhaengigen Bereiche bereits beim ersten Oeffnen korrekt
        # aktivieren; SelectChoice loest das I_TYP-Ereignis nicht verlaesslich aus.
        dialog_handler(I_TYP, 0)

    elif item == I_GLAG:
        try:
            hoehe = float(vs.GetItemText(dlg, I_GLAG).replace(',', '.'))
        except Exception:
            hoehe = 0.5
        if hoehe > 0:
            dialog_gab_tabelle_anzeigen(dlg, hoehe)

    elif item == I_GBR:
        nr = dialog_gab_auswahl(dlg)
        breiten = dialog_gab_breiten_holen()
        if nr is not None and 0 <= nr < len(breiten):
            vs.SetItemText(dlg, I_GAB_B, '%g' % breiten[nr])
            key = str(int(round(breiten[nr])))
            dialog_farbe_setzen(
                dlg, I_GAB_C,
                dialog_gab_farben_holen().get(key, '#808080'), breiten[nr])

    elif item == I_GAB_C:
        nr = dialog_gab_auswahl(dlg)
        breiten = dialog_gab_breiten_holen()
        if nr is not None and 0 <= nr < len(breiten):
            key = str(int(round(breiten[nr])))
            farben = dialog_gab_farben_holen()
            farben[key] = dialog_farbe_lesen(
                dlg, I_GAB_C, farben.get(key, '#808080'), breiten[nr])
            _dlg_values['gab_dirty'] = True
            _dlg_values['color_dirty'] = True
            dialog_gab_tabelle_anzeigen(dlg, auswahl=nr)

    elif item in (I_GAB_ADD, I_GAB_CHANGE, I_GAB_DEL):
        if item == I_GAB_ADD:
            dialog_gab_hinzufuegen(dlg)
        elif item == I_GAB_CHANGE:
            dialog_gab_aendern(dlg)
        else:
            dialog_gab_entfernen(dlg)

    elif item == I_ACTION:
        action = dialog_auswahl(dlg, I_ACTION, 0)
        dialog_schnittfeld_setzen(dlg, action)
        dialog_abhaengigkeiten_setzen(dlg)
        if action in (1, 2, 3, 4):
            dialog_tab_anzeigen(dlg, 4)       # Bezugshoehe / Ausgabe
        elif action == 5:
            dialog_tab_anzeigen(dlg, 1)       # numerische Schnittstation
        elif action == 6:
            typ = dialog_auswahl(dlg, I_TYP, 0)
            dialog_tab_anzeigen(dlg, 3 if typ == TYP_GABIONE else 2)

    elif item == I_HEIGHTS:
        try:
            typ = vs.GetSelectedChoiceIndex(dlg, I_TYP, 0)
        except Exception:
            typ = 0
        typ = 0 if typ is None or typ < 0 else typ
        if typ != TYP_GABIONE:
            nr = dialog_katalog_auswahl(dlg, typ)
            katalog = dialog_katalog_holen(typ)
            if nr is not None and 0 <= nr < len(katalog):
                vs.SetItemText(dlg, I_KAT_H, '%g' % katalog[nr][0])
                vs.SetItemText(dlg, I_KAT_F, '%g' % katalog[nr][1])
                dialog_farbe_setzen(
                    dlg, I_KAT_C, katalog[nr][2], katalog[nr][0])

    elif item == I_KAT_C:
        typ = dialog_auswahl(dlg, I_TYP, 0)
        if typ != TYP_GABIONE:
            nr = dialog_katalog_auswahl(dlg, typ)
            katalog = dialog_katalog_holen(typ)
            if nr is not None and 0 <= nr < len(katalog):
                h, fuss, farbe, bemerkung = katalog[nr]
                katalog[nr] = (
                    h, fuss,
                    dialog_farbe_lesen(dlg, I_KAT_C, farbe, h),
                    bemerkung)
                _kataloge[int(typ)] = list(katalog)
                _dlg_values.setdefault('catalog_dirty', set()).add(int(typ))
                _dlg_values['color_dirty'] = True
                dialog_katalog_anzeigen(dlg, typ, nr)

    elif item in (I_KAT_ADD, I_KAT_CHANGE, I_KAT_DEL):
        try:
            typ = vs.GetSelectedChoiceIndex(dlg, I_TYP, 0)
        except Exception:
            typ = 0
        typ = 0 if typ is None or typ < 0 else typ
        if typ == TYP_GABIONE:
            return item
        if item == I_KAT_ADD:
            dialog_katalog_hinzufuegen(dlg, typ)
        elif item == I_KAT_CHANGE:
            dialog_katalog_aendern(dlg, typ)
        else:
            dialog_katalog_entfernen(dlg, typ)

    elif item == I_TYP:
        try:
            typ = vs.GetSelectedChoiceIndex(dlg, I_TYP, 0)
        except Exception:
            typ = 0
        typ = 0 if typ is None or typ < 0 else typ
        if typ != TYP_GABIONE:
            dialog_katalog_anzeigen(dlg, typ)
            vs.SetItemText(dlg, I_KAT_H, '')
            vs.SetItemText(dlg, I_KAT_F, '')
            dialog_farbe_setzen(dlg, I_KAT_C, '#808080')

        # Die beiden Bereiche sind getrennt: was nicht zum gewaehlten
        # Mauertyp gehoert, wird ausgegraut.
        winkel = (I_SEPK, I_HEIGHTS_L, I_HEIGHTS,
                  I_KAT_H_L, I_KAT_H, I_KAT_F_L, I_KAT_F,
                  I_KAT_C_L, I_KAT_C,
                  I_KAT_ADD, I_KAT_CHANGE, I_KAT_DEL,
                  I_UO_L, I_UO, I_UU_L, I_UU,
                  I_BR_L, I_BR, I_BRF, I_ECK_L, I_ECK, I_ECKST,
                   I_STUFE_L, I_STUFE, I_HMODE_L, I_HMODE, I_OKA_L, I_OKA,
                   I_DICKE_L, I_DICKE, I_DICKEF, I_FUSS, I_FUSSLS_L, I_FUSSLS,
                   I_WFUND_U_L, I_WFUND_U, I_WFUND_T_L, I_WFUND_T,
                   I_FUSS_ST_L, I_FUSS_ST,
                   I_EINZEL, I_WS)
        gabione = (I_SEPG, I_GLEN_L, I_GLEN, I_GLAG_L, I_GLAG,
                   I_GEIN_L, I_GEIN, I_GUEB_L, I_GUEB, I_GSTAF_L, I_GSTAF,
                   I_GMIN_L, I_GMIN, I_GFUND_U_L, I_GFUND_U,
                   I_GFUND_T_L, I_GFUND_T,
                   I_GBR_L, I_GBR, I_GAB_B_L, I_GAB_B,
                   I_GAB_C_L, I_GAB_C,
                   I_GAB_ADD, I_GAB_CHANGE, I_GAB_DEL)
        for iid in winkel:
            try:
                vs.EnableItem(dlg, iid, typ != TYP_GABIONE)
            except Exception:
                pass
        try:
            vs.EnableLB(dlg, I_HEIGHTS, typ != TYP_GABIONE)
        except Exception:
            pass
        for iid in gabione:
            try:
                vs.EnableItem(dlg, iid, typ == TYP_GABIONE)
            except Exception:
                pass
        try:
            vs.EnableLB(dlg, I_GBR, typ == TYP_GABIONE)
        except Exception:
            pass
        for iid, aktiv in ((I_TAB_WINKEL, typ != TYP_GABIONE),
                           (I_TAB_GABIONE, typ == TYP_GABIONE)):
            try:
                vs.EnableItem(dlg, iid, aktiv)
            except Exception:
                pass
        dialog_actionen_setzen(dlg, typ)
        if typ == TYP_GABIONE:
            vs.SetItemText(dlg, I_EBNAME, s.get('gab_ebene_name', 'Gabione'))
            vs.SetItemText(dlg, I_EBMST, '%g' % s.get(
                'gab_ebene_massstab', 50.0))
            vs.SetItemText(dlg, I_PREFIX, s.get('gab_prefix', 'PD-MA-GAB-'))
        else:
            vs.SetItemText(dlg, I_EBNAME, s.get(
                'winkel_ebene_name', 'Winkelstützmauer'))
            vs.SetItemText(dlg, I_EBMST, '%g' % s.get(
                'winkel_ebene_massstab', 25.0))
            vs.SetItemText(dlg, I_PREFIX, s.get('winkel_prefix', 'PD-MWL-'))
        if typ == 1:
            # unarmiert: Regelbreite 40 cm
            try:
                vs.SelectChoice(dlg, I_BR, 2, True)
            except Exception:
                pass
            vs.SetItemText(dlg, I_BRF, '%g' % REGELBREITE_UN)
        elif typ == 0:
            try:
                vs.SelectChoice(dlg, I_BR, int(s.get('breite_mode', 1)), True)
            except Exception:
                pass
            vs.SetItemText(dlg, I_BRF, '%g' % s.get('breite_frei', 75.0))
        dialog_abhaengigkeiten_setzen(dlg)
        dialog_tab_anzeigen(dlg, 3 if typ == TYP_GABIONE else 2)

    elif item in (I_BR, I_DICKE, I_HMODE, I_FUSS, I_BEM, I_REF,
                  I_EBENE, I_AUFS):
        dialog_abhaengigkeiten_setzen(dlg)

    elif item in (I_FARBM, I_FUND_C):
        _dlg_values['color_dirty'] = True

    elif item == I_REFSEL:
        # Wert aus der Liste in das Eingabefeld uebernehmen
        try:
            i = vs.GetSelectedChoiceIndex(dlg, I_REFSEL, 0)
        except Exception:
            i = 0
        if 0 < i <= len(_ref_liste):
            vs.SetItemText(dlg, I_REFV, _ref_liste[i - 1])

    elif item == I_OK:
        typ = dialog_auswahl(dlg, I_TYP, int(s.get('stein_typ', 0)))
        action = dialog_auswahl(dlg, I_ACTION, 0)
        if not dialog_eingaben_pruefen(dlg, typ, action):
            return -1
        v = {}

        def choice(iid, fallback=0):
            try:
                idx = vs.GetSelectedChoiceIndex(dlg, iid, 0)
            except Exception:
                return fallback
            return fallback if idx is None or idx < 0 else idx

        v['action'] = choice(I_ACTION, 0)
        v['stein_typ'] = choice(I_TYP, int(s.get('stein_typ', 0)))
        v['unit'] = ['m', 'cm', 'mm'][choice(I_UNIT, 0)]
        v['breite_mode'] = choice(I_BR, s['breite_mode'])
        v['pass_lage'] = choice(I_PLAGE, s['pass_lage'])
        v['hoehen_mode'] = choice(I_HMODE, s['hoehen_mode'])
        v['dicke_mode'] = choice(I_DICKE, s['dicke_mode'])
        v['seite'] = choice(I_SEITE, s['seite'])
        v['fuss_zeichnen'] = vs.GetBooleanItem(dlg, I_FUSS)
        v['farb_modus'] = choice(I_FARBM, int(s.get('farb_modus', 0)))
        v['farben_neu'] = (vs.GetBooleanItem(dlg, I_FARBEN) or
                           bool(_dlg_values.get('color_dirty')))
        v['bemassung'] = vs.GetBooleanItem(dlg, I_BEM)
        v['dim_abstand'] = _f(dlg, I_BEMD, 60.0)
        v['transparenz'] = max(0.0, min(100.0, _f(dlg, I_TRANS, 50.0)))
        v['fuss_ls'] = vs.GetItemText(dlg, I_FUSSLS).strip()
        v['ebene_aktiv'] = vs.GetBooleanItem(dlg, I_EBENE)
        v['ebene_name'] = (vs.GetItemText(dlg, I_EBNAME).strip()
                           or 'Winkelstützmauer')
        v['ebene_massstab'] = _f(dlg, I_EBMST, 25.0)
        v['gab_laenge'] = _f(dlg, I_GLEN, 2.0)
        v['gab_lage'] = _f(dlg, I_GLAG, 0.5)
        v['gab_einbinde'] = _f(dlg, I_GEIN, 0.3)
        v['gab_ueber'] = _f(dlg, I_GUEB, 0.2)
        v['gab_staffel'] = max(0.0, _f(dlg, I_GSTAF, 0.0))
        v['gab_lage_min'] = max(0.0, _f(dlg, I_GMIN, 0.25))
        v['schnitt_station'] = max(0.0, _f(dlg, I_GSCH, 5.0))
        v['gab_fund_tiefe'] = max(0.0, _f(
            dlg, I_GFUND_T, GAB_FUND_TIEFE_CM))
        v['gab_fund_ueberstand'] = max(0.0, _f(
            dlg, I_GFUND_U, GAB_FUND_UEBERSTAND_CM))
        v['gab_breiten'] = '\n'.join(
            '%g' % b for b in dialog_gab_breiten_holen())
        v['gab_colors'] = dict(dialog_gab_farben_holen())
        v['fundament_farbe'] = dialog_farbe_lesen(
            dlg, I_FUND_C, s.get('fundament_farbe', DEFAULT_FUNDAMENT_FARBE))
        v['ueber_ok'] = _f(dlg, I_UO, DEFAULTS['ueber_ok'])
        v['unter_uk'] = _f(dlg, I_UU, DEFAULTS['unter_uk'])
        v['fund_ueberstand'] = max(0.0, _f(
            dlg, I_WFUND_U, WINKEL_FUND_UEBERSTAND_CM))
        v['fund_tiefe'] = max(0.0, _f(
            dlg, I_WFUND_T, WINKEL_FUND_TIEFE_CM))
        v['winkel_fuss_staerke'] = max(0.0, _f(
            dlg, I_FUSS_ST, 15.0))
        v['breite_frei'] = _f(dlg, I_BRF, DEFAULTS['breite_frei'])
        v['pass_min'] = _f(dlg, I_PMIN, DEFAULTS['pass_min'])
        v['eck_schenkel'] = _f(dlg, I_ECK, 50.0)
        v['ecke_abstufen'] = vs.GetBooleanItem(dlg, I_ECKST)
        v['stufe_min'] = max(0.0, _f(dlg, I_STUFE, 0.0))
        v['ok_abstand'] = _f(dlg, I_OKA, 10.0)
        v['einzelliste'] = vs.GetBooleanItem(dlg, I_EINZEL)
        v['dicke_frei'] = _f(dlg, I_DICKEF, DEFAULTS['dicke_frei'])
        v['ref_hoehe'] = _f(dlg, I_REFV, DEFAULTS['ref_hoehe'])
        liste = ['%.3f' % v['ref_hoehe']]
        liste += [x for x in _ref_liste if x != liste[0]]
        v['ref_liste'] = [float(x) for x in liste[:10]]
        v['font_size'] = normalized_font_size(
            _f(dlg, I_FSIZE, TEXT_DEFAULT_SIZE))
        v['toleranz'] = _f(dlg, I_TOL, 5.0)
        v['font'] = TEXT_FONT
        v['prefix'] = vs.GetItemText(dlg, I_PREFIX).strip() or 'PD-MWL-'
        if v['stein_typ'] == TYP_GABIONE:
            v['gab_prefix'] = v['prefix']
            v['gab_ebene_name'] = v['ebene_name']
            v['gab_ebene_massstab'] = v['ebene_massstab']
            v['winkel_prefix'] = s.get('winkel_prefix', 'PD-MWL-')
            v['winkel_ebene_name'] = s.get(
                'winkel_ebene_name', 'Winkelstützmauer')
            v['winkel_ebene_massstab'] = s.get('winkel_ebene_massstab', 25.0)
        else:
            v['winkel_prefix'] = v['prefix']
            v['winkel_ebene_name'] = v['ebene_name']
            v['winkel_ebene_massstab'] = v['ebene_massstab']
            v['gab_prefix'] = s.get('gab_prefix', 'PD-MA-GAB-')
            v['gab_ebene_name'] = s.get('gab_ebene_name', 'Gabione')
            v['gab_ebene_massstab'] = s.get('gab_ebene_massstab', 50.0)
        v['aufsicht'] = vs.GetBooleanItem(dlg, I_AUFS)
        v['draw_3d'] = vs.GetBooleanItem(dlg, I_DRAW_3D)
        v['aufsicht_umkehren'] = vs.GetBooleanItem(dlg, I_REV)
        v['ref_aktiv'] = vs.GetBooleanItem(dlg, I_REF)
        v['txt_rot'] = vs.GetBooleanItem(dlg, I_ROT)
        v['ws_tabelle'] = vs.GetBooleanItem(dlg, I_WS)
        v['zeichnungs_tabelle'] = vs.GetBooleanItem(dlg, I_TAB)

        for katalog_typ in (0, 1):
            katalog = katalog_normalisieren(dialog_katalog_holen(katalog_typ))
            _kataloge[katalog_typ] = list(katalog)
            v[katalog_schluessel(katalog_typ)] = [list(e) for e in katalog]
            v[katalog_custom_schluessel(katalog_typ)] = bool(
                s.get(katalog_custom_schluessel(katalog_typ), False) or
                katalog_typ in _dlg_values.get('catalog_dirty', set()))
        v['gab_catalog_custom'] = bool(
            s.get('gab_catalog_custom', False) or
            _dlg_values.get('gab_dirty', False))
        if v['stein_typ'] != TYP_GABIONE:
            v['heights'] = [e[0] for e in _kataloge[v['stein_typ']]]
        else:
            v['heights'] = list(s.get('heights') or DEFAULTS['heights'])
        v['_catalog_dirty'] = sorted(
            _dlg_values.get('catalog_dirty', set()))
        v['_gab_dirty'] = bool(_dlg_values.get('gab_dirty', False))
        _dlg_values['result'] = v
    return item


def show_dialog(s):
    dlg = vs.CreateLayout(_dialog_title('PD Winkelstützmauer'),
                          True, 'Ausführen', 'Abbrechen')
    _dlg_values.clear()
    _dlg_values['dlg'] = dlg
    _dlg_settings.clear()
    _dlg_settings.update(s)
    _pd_choices.clear()
    _ref_liste[:] = ['%.3f' % float(v) for v in s.get('ref_liste', [])][:10]

    def st(i, txt, style=0):
        if style:
            try:
                vs.CreateStyledStatic(dlg, i, txt, -1, style)
                return
            except Exception:
                pass
        vs.CreateStaticText(dlg, i, txt, -1)

    def ed(i, w=12):
        vs.CreateEditText(dlg, i, '', w)

    def pd(i, choices, w=22):
        vs.CreatePullDownMenu(dlg, i, w)
        _pd_choices[i] = list(choices)

    # Der kurze Kopf spart Breite. Mauertyp und Aktion bleiben ausserhalb der
    # Reiter dauerhaft sichtbar und bilden die primaere Bedienhierarchie.
    st(I_TITEL, 'MAUERTOOL  |  Winkelsteine + Gabionen  |  v' + VERSION, 213)
    try:
        vs.CreateImageControl2(dlg, I_LOGO, 104, 54, '')
    except Exception:
        pass
    vs.CreateTabControl(dlg, I_TABS)
    vs.CreateGroupBox(dlg, I_TAB_GRUND, 'Grundlagen', False)
    vs.CreateGroupBox(dlg, I_TAB_WINKEL, 'Winkelsteine', False)
    vs.CreateGroupBox(dlg, I_TAB_GABIONE, 'Gabionen', False)
    vs.CreateGroupBox(dlg, I_TAB_AUSGABE, 'Ausgabe', False)

    st(I_SEPG, 'AUFBAU UND FUNDAMENT', 211)
    st(I_GLEN_L, 'Regellaenge einer Gabione [m]:')
    ed(I_GLEN, 8)
    st(I_GLAG_L, 'Hoehe einer Gabionenlage [m]:')
    ed(I_GLAG, 8)
    st(I_GEIN_L, 'Einbindetiefe unter UK [m]:')
    ed(I_GEIN, 8)
    st(I_GUEB_L, 'Ueberstand ueber Gelaende [m]:')
    ed(I_GUEB, 8)
    st(I_GSTAF_L, 'Mindest-Abstaffelung OK [m]:')
    ed(I_GSTAF, 8)
    st(I_GMIN_L, 'Mindesthoehe unterste Lage [m]:')
    ed(I_GMIN, 8)
    st(I_GSCH_L, 'Schnittstation [m] (nur Einzelschnitt):')
    ed(I_GSCH, 8)
    st(I_GFUND_U_L, 'Fundamentueberstand allseitig [cm]:')
    ed(I_GFUND_U, 8)
    st(I_GFUND_T_L, 'Fundamenttiefe unter UK [cm]:')
    ed(I_GFUND_T, 8)
    st(I_GBR_L, 'LAGENTABELLE (OBEN NACH UNTEN)', 211)
    vs.CreateLB(dlg, I_GBR, 48, 8)
    st(I_GAB_B_L, 'Breite [cm]:')
    ed(I_GAB_B, 8)
    st(I_GAB_C_L, 'Farbe dieser Breite:')
    vs.CreateColorPopup(dlg, I_GAB_C, 18)
    vs.CreatePushButton(dlg, I_GAB_ADD, 'Neue Lage nach Auswahl')
    vs.CreatePushButton(dlg, I_GAB_CHANGE, 'Auswahl aendern')
    vs.CreatePushButton(dlg, I_GAB_DEL, 'Auswahl entfernen')
    st(I_SEPA, 'ABWICKLUNG', 211)
    st(I_SEPB, 'HOEHEN, AUFSICHT UND FUNDAMENT', 211)
    st(I_SEPD, 'BESCHRIFTUNG UND BEMASSUNG', 211)
    st(I_SEPC, 'ZEICHNUNG UND KONSTRUKTIONSEBENE', 211)
    st(I_SEP1, 'AUFSICHT UND SCHNITT', 211)
    st(I_TYP_L, 'MAUERTYP:', 211)
    pd(I_TYP, STEIN_TYPEN, 32)
    st(I_ACTION_L, 'AKTION:', 211)
    pd(I_ACTION, AKTIONEN_GABIONE if int(s.get('stein_typ', 0)) == TYP_GABIONE
       else AKTIONEN_WINKEL, 43)


    vs.CreateCheckBox(dlg, I_EBENE, 'Eigene Konstruktionsebene')
    st(I_EBNAME_L, 'Name der Ebene:')
    ed(I_EBNAME, 20)
    st(I_EBMST_L, 'Massstab 1:')
    ed(I_EBMST, 8)
    st(I_UNIT_L, 'Zeichnungseinheit:')
    pd(I_UNIT, ['Meter (m)', 'Zentimeter (cm)', 'Millimeter (mm)'], 22)

    st(I_UO_L, 'Ueberstand ueber OK [cm]:')
    ed(I_UO)
    st(I_UU_L, 'Tiefe unter UK [cm]:')
    ed(I_UU)

    st(I_BR_L, 'Elementlaenge (Regel):')
    pd(I_BR, ['50 cm', '100 cm', 'frei ->'], 16)
    ed(I_BRF, 8)

    st(I_ECK_L, 'Eckschenkel [cm]:')
    ed(I_ECK)
    vs.CreateCheckBox(dlg, I_ECKST,
                      'Ecken abtreppen')
    st(I_STUFE_L, 'Min. Abtreppung OK [cm]:')
    ed(I_STUFE, 8)
    st(I_PMIN_L, 'Mindestbreite Pass [cm]:')
    ed(I_PMIN)
    st(I_PLAGE_L, 'Lage des Passelements:')
    pd(I_PLAGE, ['am Ende', 'am Anfang', 'in der Mitte'], 18)

    st(I_HMODE_L, 'Hoehenverlauf:')
    pd(I_HMODE, ['Kopf an Oberkante-Vorgabe',
                 'Fuss auf Unterkante-Vorgabe',
                 'Ausgleich (mittig)',
                 'Oberkante parallel zur Oberkante-Linie'], 30)
    st(I_OKA_L, 'Parallelabstand OK [cm]:')
    ed(I_OKA, 8)

    st(I_DICKE_L, 'Mauerdicke [cm]:')
    pd(I_DICKE, ['10', '12', '15', '20', 'frei ->'], 12)
    ed(I_DICKEF, 8)
    st(I_SEITE_L, 'Mauer liegt:')
    pd(I_SEITE, ['links', 'rechts'], 14)
    vs.CreateCheckBox(dlg, I_FUSS, 'Fusslaenge gestrichelt')
    st(I_FUSSLS_L, 'Linientyp fuer den Fuss:')
    ed(I_FUSSLS, 16)
    st(I_WFUND_U_L, 'Fundamentueberstand [cm]:')
    ed(I_WFUND_U, 8)
    st(I_WFUND_T_L, 'Fundamenttiefe unter UK [cm]:')
    ed(I_WFUND_T, 8)
    st(I_FUSS_ST_L, 'Staerke Winkelsteinfuss [cm]:')
    ed(I_FUSS_ST, 8)
    vs.CreateCheckBox(dlg, I_AUFS, 'Aufsicht zeichnen')
    vs.CreateCheckBox(dlg, I_DRAW_3D, '3D-Konstruktion mit 5x5-mm-Fasen erzeugen')
    vs.CreateCheckBox(dlg, I_REV, 'Aufsichtslinie umkehren')
    vs.CreateCheckBox(dlg, I_REF, 'Bezugshoehe verwenden')
    st(I_SEP2, 'BEZUGSHOEHE', 211)
    st(I_REFV_L, 'Bezugshoehe [m]:')
    ed(I_REFV, 12)
    pd(I_REFSEL, ['(zuletzt benutzt)'] + _ref_liste, 18)
    st(I_REFHINT, 'Bezugspunkt: Oberkante am linken Mauerbeginn.\n'
                  'Vertikal verschieben und Mauer aktualisieren.')

    st(I_FONT_L, 'Schriftart:')
    ed(I_FONT, 16)
    st(I_FSIZE_L, 'Schrifthoehe [pt]:')
    ed(I_FSIZE, 8)
    vs.CreateCheckBox(dlg, I_ROT, 'Hoehentext 90 Grad drehen')

    st(I_SEP3, 'LISTEN UND TABELLEN', 211)
    st(I_SEPK, 'KATALOG WINKELSTEINE', 211)
    st(I_HEIGHTS_L, 'Verfuegbare Winkelsteingroessen:')
    vs.CreateLB(dlg, I_HEIGHTS, 42, 7)
    st(I_KAT_H_L, 'Hoehe [cm]:')
    ed(I_KAT_H, 8)
    st(I_KAT_F_L, 'Fusslaenge [cm]:')
    ed(I_KAT_F, 8)
    st(I_KAT_C_L, 'Farbe dieses Winkelsteins:')
    vs.CreateColorPopup(dlg, I_KAT_C, 18)
    vs.CreatePushButton(dlg, I_KAT_ADD, 'Neu hinzufuegen')
    vs.CreatePushButton(dlg, I_KAT_CHANGE, 'Auswahl aendern')
    vs.CreatePushButton(dlg, I_KAT_DEL, 'Auswahl entfernen')
    st(I_PREFIX_L, 'Klassen-Praefix:')
    ed(I_PREFIX, 16)
    st(I_TOL_L, 'Laengentoleranz [cm]:')
    ed(I_TOL, 8)
    st(I_TRANS_L, 'Transparenz Fuellung [%]:')
    ed(I_TRANS, 8)
    vs.CreateCheckBox(dlg, I_BEM, 'Mauer bemassen')
    st(I_BEMD_L, 'Abstand der Masslinie [cm]:')
    ed(I_BEMD, 8)
    st(I_FARBM_L, 'Farbzuordnung der Klassen:')
    pd(I_FARBM, FARB_MODI, 28)
    st(I_FUND_C_L, 'Fundamentfarbe:')
    vs.CreateColorPopup(dlg, I_FUND_C, 18)
    vs.CreateCheckBox(dlg, I_FARBEN,
                      'Klassenfarben neu setzen')
    vs.CreateCheckBox(dlg, I_EINZEL,
                      'Einzelliste je Winkelstein')
    vs.CreateCheckBox(dlg, I_WS, 'Summenliste als Arbeitsblatt')
    vs.CreateCheckBox(dlg, I_TAB, 'Summenliste in die Zeichnung')
    st(I_HINT, 'Neue Mauer: Unterkante, Oberkante und Aufsicht\n'
               'vor dem Start des Befehls auswaehlen.')

    # Kompakte Reiteranordnung. Jeder Reiter bleibt deutlich unter der Hoehe
    # des bisherigen Gesamtdialogs; lange Kataloge sind innerhalb ihrer
    # Tabellen scrollbar.
    def spalte(kopf, zeilen, vorher=None):
        """Setzt eine Spalte untereinander. zeilen = (links, mitte, rechts)."""
        oben = kopf
        for links, mitte, rechts in zeilen:
            vs.SetBelowItem(dlg, oben, links, 0, 0)
            if mitte is not None:
                vs.SetRightItem(dlg, links, mitte, 0, 0)
            if rechts is not None:
                vs.SetRightItem(dlg, mitte, rechts, 0, 0)
            oben = links
        return oben

    vs.SetFirstLayoutItem(dlg, I_TITEL)
    try:
        vs.SetRightItem(dlg, I_TITEL, I_LOGO, 24, 0)
    except Exception:
        pass
    vs.SetBelowItem(dlg, I_TITEL, I_TYP_L, 0, 8)
    vs.SetRightItem(dlg, I_TYP_L, I_TYP, 0, 0)
    vs.SetRightItem(dlg, I_TYP, I_ACTION_L, 24, 0)
    vs.SetRightItem(dlg, I_ACTION_L, I_ACTION, 0, 0)
    vs.SetBelowItem(dlg, I_TYP_L, I_TABS, 0, 10)

    # Reiter 1: gemeinsame Grundlagen
    vs.SetFirstGroupItem(dlg, I_TAB_GRUND, I_SEPC)
    spalte(I_SEPC, [
        (I_EBENE, None, None),
        (I_EBNAME_L, I_EBNAME, None),
        (I_EBMST_L, I_EBMST, None),
        (I_UNIT_L, I_UNIT, None),
        (I_HINT, None, None),
    ])
    vs.SetRightItem(dlg, I_SEPC, I_SEP1, 24, 0)
    spalte(I_SEP1, [
        (I_GSCH_L, I_GSCH, None),
        (I_AUFS, None, None),
        (I_DRAW_3D, None, None),
        (I_SEITE_L, I_SEITE, None),
        (I_REV, None, None),
    ])

    # Reiter 2: nur Winkelsteinparameter und editierbarer Katalog
    vs.SetFirstGroupItem(dlg, I_TAB_WINKEL, I_SEPA)
    spalte(I_SEPA, [
        (I_UO_L, I_UO, None),
        (I_UU_L, I_UU, None),
        (I_BR_L, I_BR, I_BRF),
        (I_PMIN_L, I_PMIN, None),
        (I_PLAGE_L, I_PLAGE, None),
        (I_TOL_L, I_TOL, None),
    ])
    vs.SetRightItem(dlg, I_SEPA, I_SEPB, 36, 0)
    spalte(I_SEPB, [
        (I_HMODE_L, I_HMODE, None),
        (I_OKA_L, I_OKA, None),
        (I_STUFE_L, I_STUFE, None),
        (I_ECK_L, I_ECK, None),
        (I_ECKST, None, None),
        (I_DICKE_L, I_DICKE, I_DICKEF),
        (I_FUSS, None, None),
        (I_FUSSLS_L, I_FUSSLS, None),
        (I_WFUND_U_L, I_WFUND_U, None),
        (I_WFUND_T_L, I_WFUND_T, None),
        (I_FUSS_ST_L, I_FUSS_ST, None),
    ])
    vs.SetRightItem(dlg, I_SEPB, I_SEPK, 36, 0)
    spalte(I_SEPK, [
        (I_HEIGHTS_L, None, None),
        (I_HEIGHTS, None, None),
        (I_KAT_H_L, I_KAT_H, None),
        (I_KAT_F_L, I_KAT_F, None),
        (I_KAT_C_L, I_KAT_C, None),
        (I_KAT_ADD, I_KAT_CHANGE, I_KAT_DEL),
    ])

    # Reiter 3: Gabionenparameter und zugehoerige Lagentabelle
    vs.SetFirstGroupItem(dlg, I_TAB_GABIONE, I_SEPG)
    spalte(I_SEPG, [
        (I_GLEN_L, I_GLEN, None),
        (I_GLAG_L, I_GLAG, None),
        (I_GEIN_L, I_GEIN, None),
        (I_GUEB_L, I_GUEB, None),
        (I_GSTAF_L, I_GSTAF, None),
        (I_GMIN_L, I_GMIN, None),
        (I_GFUND_U_L, I_GFUND_U, None),
        (I_GFUND_T_L, I_GFUND_T, None),
    ])
    vs.SetRightItem(dlg, I_SEPG, I_GBR_L, 24, 0)
    spalte(I_GBR_L, [
        (I_GBR, None, None),
        (I_GAB_B_L, I_GAB_B, None),
        (I_GAB_C_L, I_GAB_C, None),
        (I_GAB_ADD, I_GAB_CHANGE, I_GAB_DEL),
    ])

    # Reiter 4: Darstellung, Bezugshoehen und Ausgabelisten
    vs.SetFirstGroupItem(dlg, I_TAB_AUSGABE, I_SEPD)
    spalte(I_SEPD, [
        (I_FONT_L, I_FONT, None),
        (I_FSIZE_L, I_FSIZE, None),
        (I_ROT, None, None),
        (I_PREFIX_L, I_PREFIX, None),
        (I_FARBM_L, I_FARBM, None),
        (I_FUND_C_L, I_FUND_C, None),
        (I_FARBEN, None, None),
        (I_TRANS_L, I_TRANS, None),
        (I_BEM, None, None),
        (I_BEMD_L, I_BEMD, None),
    ])
    vs.SetRightItem(dlg, I_SEPD, I_SEP2, 24, 0)
    spalte(I_SEP2, [
        (I_REF, None, None),
        (I_REFV_L, I_REFV, I_REFSEL),
        (I_REFHINT, None, None),
        (I_SEP3, None, None),
        (I_EINZEL, None, None),
        (I_WS, None, None),
        (I_TAB, None, None),
    ])

    for pane in (I_TAB_GRUND, I_TAB_WINKEL, I_TAB_GABIONE, I_TAB_AUSGABE):
        vs.CreateTabPane(dlg, I_TABS, pane)

    res = vs.RunLayoutDialog(dlg, dialog_handler)
    if res == 1 and 'result' in _dlg_values:
        return True, _dlg_values['result']
    return False, None


# ---------------------------------------------------------------------------
# Kernberechnung: Elementverteilung
# ---------------------------------------------------------------------------


def pick_height(req_cm, heights):
    """Kleinste Katalog-Hoehe, die >= erforderliche Hoehe ist."""
    for h in sorted(heights):
        if h + 1e-6 >= req_cm:
            return h, False
    return max(heights), True          # zu klein -> Warnung


def split_run(length, b_regel, pass_min, pass_lage, b_max=None,
              meter_halbstein=False):
    """Teilt eine Wandstrecke in Elementbreiten auf.
    Es entsteht hoechstens EIN Passelement je Abschnitt: bleibt ein Rest
    unter der Mindest-Passbreite, entfaellt ein Regelelement und der Rest
    wird ihm zugeschlagen.
    Rueckgabe: Liste [(breite, ist_pass), ...]
    """
    eps = 1e-9
    if length <= eps:
        return []
    if b_max is None:
        b_max = b_regel

    # Bei 1,00-m-Winkelsteinen darf der verbleibende Abschnitt mit einem
    # lieferbaren 50-cm-Regelstein und genau einem Passelement geschlossen
    # werden. Diese Sonderregel ist explizit auf Winkelsteine begrenzt, damit
    # eine Gabionen-Regellaenge von 1,00 m unveraendert bleibt.
    meterregel = (meter_halbstein and
                  abs(b_regel - U.cm(100.0)) <= U.cm(0.01))
    halbstein = U.cm(50.0)

    def meterabschluss(n_regel, pass_breite):
        regeln = [(b_regel, False)] * n_regel
        halb = (halbstein, False)
        passelement = (pass_breite, True)
        if pass_lage == 1:        # Anfang
            return [passelement, halb] + regeln
        if pass_lage == 2:        # Mitte
            mitte = n_regel // 2
            return (regeln[:mitte] + [halb, passelement] +
                    regeln[mitte:])
        return regeln + [halb, passelement]  # Ende

    if length <= b_regel + eps:
        if (meterregel and length < b_regel - eps and
                length - halbstein >= pass_min - eps):
            return meterabschluss(0, length - halbstein)
        return [(length, abs(length - b_regel) > 1e-6)]

    n = int(math.floor(length / b_regel + 1e-9))
    rest = length - n * b_regel
    if rest < eps:
        return [(b_regel, False)] * n

    if meterregel:
        # Der Rest selbst bietet Platz fuer 50-cm-Regelstein + Passstueck.
        if rest - halbstein >= pass_min - eps:
            return meterabschluss(n, rest - halbstein)
        # Ein Rest unter der Mindest-Passbreite wird zusammen mit der Haelfte
        # des letzten Metersteins zu einem ausreichend grossen Passelement.
        if n >= 1 and rest < pass_min - eps:
            pass_breite = halbstein + rest
            if (pass_breite >= pass_min - eps and
                    pass_breite <= b_max + eps):
                return meterabschluss(n - 1, pass_breite)

    # Rest unter der Mindestbreite: ein Regelelement entfaellt, sein Mass
    # kommt zum Passstueck - aber nur, wenn das Passstueck aus einem
    # lieferbaren Element geschnitten werden kann.
    if rest < pass_min and n >= 1 and (rest + b_regel) <= b_max + 1e-9:
        n -= 1
        rest += b_regel

    parts = [(b_regel, False)] * n
    if pass_lage == 1:            # Anfang
        return [(rest, True)] + parts
    if pass_lage == 2:            # Mitte
        mid = n // 2
        return parts[:mid] + [(rest, True)] + parts[mid:]
    return parts + [(rest, True)]  # Ende (Regelfall)


def compute_elements(uk_pts, ok_pts, corners, x0, x1, p):
    """Erzeugt die Elementliste ueber die gesamte Abwicklungslaenge.

    Reihenfolge der Vergabe:
      1. An jeder Ecke zwei getrennte Regelelemente (Regel 50 cm je Seite).
      2. Direkt daran anschliessend das Passelement.
      3. Der Rest mit Regelelementen.
    """
    b_regel = U.cm(p['breite_cm'])
    pass_min = U.cm(p['pass_min'])
    schenkel = U.cm(p.get('eck_schenkel', 50.0))
    heights = p['heights']
    Lges = x1 - x0
    warn = []

    def masse(xa, xb, konstant=False):
        """Hoehenwahl und Lage fuer den Bereich [xa, xb].
        konstant=True erzwingt eine waagerechte Oberkante (Eckelemente).
        """
        uk_min, _ = y_extremes(uk_pts, xa, xb)
        _, ok_max = y_extremes(ok_pts, xa, xb)
        need_bot = uk_min - U.cm(p['unter_uk'])

        if p['hoehen_mode'] == 3 and not konstant:
            # Oberkante parallel zur Oberkante-Linie, fester Abstand
            abst = U.cm(p.get('ok_abstand', 10.0))
            ybot = need_bot
            xs = [xa] + [q[0] for q in ok_pts if xa < q[0] < xb] + [xb]
            top = [(x, y_at(ok_pts, x) + abst) for x in xs]
            ytop = max(q[1] for q in top)
            req = ytop - ybot
            req_cm = U.to_cm(req)
            h_cm, too_small = pick_height(req_cm, heights)
            fuss = 0.0
            try:
                fuss = float(p.get('feet', {}).get(str(int(round(h_cm))), 0.0))
            except Exception:
                fuss = 0.0
            return {'h_cm': h_cm, 'ybot': ybot, 'ytop': ytop, 'req_cm': req_cm,
                    'fuss_cm': fuss, 'too_small': too_small, 'top_pts': top,
                    'h_links_cm': U.to_cm(top[0][1] - ybot),
                    'h_rechts_cm': U.to_cm(top[-1][1] - ybot),
                    'parallel': True}

        # Im Parallelmodus gilt der Parallelabstand auch fuer die
        # waagerechten Eckelemente.
        if p['hoehen_mode'] == 3:
            need_top = ok_max + U.cm(p.get('ok_abstand', 10.0))
        else:
            need_top = ok_max + U.cm(p['ueber_ok'])
        req = need_top - need_bot
        req_cm = U.to_cm(req)
        h_cm, too_small = pick_height(req_cm, heights)
        H = U.cm(h_cm)
        if p['hoehen_mode'] == 1:                  # Fuss auf Unterkante
            ybot = need_bot
            ytop = ybot + H
        elif p['hoehen_mode'] == 2:                # Ausgleich
            ybot = need_bot - (H - req) / 2.0
            ytop = ybot + H
        else:                                      # Kopf an Oberkante
            ytop = need_top
            ybot = ytop - H
        fuss = 0.0
        try:
            fuss = float(p.get('feet', {}).get(str(int(round(h_cm))), 0.0))
        except Exception:
            fuss = 0.0
        return {'h_cm': h_cm, 'ybot': ybot, 'ytop': ytop, 'req_cm': req_cm,
                'fuss_cm': fuss, 'too_small': too_small,
                'top_pts': [(xa, ytop), (xb, ytop)],
                'h_links_cm': U.to_cm(ytop - ybot),
                'h_rechts_cm': U.to_cm(ytop - ybot),
                'need_top': need_top, 'need_bot': need_bot,
                'parallel': False}

    # ---- Eckelemente festlegen --------------------------------------------
    ecken = []
    for c in sorted(corners, key=lambda d: d['s']):
        sc = c['s']
        if sc <= 1e-9 or sc >= Lges - 1e-9:
            continue
        li = min(schenkel, sc, Lges - sc)
        if li <= 1e-9:
            continue
        ecken.append({'sc': sc, 'angle': c['angle'], 'leg': li})

    # Ueberschneidungen benachbarter Ecken entschaerfen
    for i in range(len(ecken) - 1):
        a, b = ecken[i], ecken[i + 1]
        frei = b['sc'] - a['sc']
        if a['leg'] + b['leg'] > frei:
            a['leg'] = b['leg'] = max(frei / 2.0, 0.0)
    ecken = [e for e in ecken if e['leg'] > 1e-9]

    elements = []
    # Abstufen nur ausserhalb des Parallelmodus - dort folgt die Ecke ohnehin
    # der Oberkante.
    abstufen = bool(p.get('ecke_abstufen')) and p['hoehen_mode'] != 3
    for e in ecken:
        s0, s1 = e['sc'] - e['leg'], e['sc'] + e['leg']
        # Ohne Abtreppung behalten beide Regelelemente die bisherige gemeinsame
        # Hoehenwahl. Mit Abtreppung wird jeder Schenkel einzeln bemessen.
        gemeinsam = None if abstufen else masse(
            x0 + s0, x0 + s1, konstant=(p['hoehen_mode'] != 3))
        for teil, (a, b) in (('a', (s0, e['sc'])),
                             ('b', (e['sc'], s1))):
            m = dict(gemeinsam) if gemeinsam is not None else masse(
                x0 + a, x0 + b, konstant=True)
            top = profil_abschnitt(
                m.get('top_pts') or [(x0 + a, m['ytop']),
                                     (x0 + b, m['ytop'])],
                x0 + a, x0 + b)
            m['top_pts'] = top
            m['ytop'] = max(q[1] for q in top)
            m['h_links_cm'] = U.to_cm(top[0][1] - m['ybot'])
            m['h_rechts_cm'] = U.to_cm(top[-1][1] - m['ybot'])
            elements.append(dict(
                m, s0=a, s1=b, sc=None, angle=e['angle'],
                corner_station=e['sc'], corner_part=teil, teil=teil,
                x0=x0 + a, x1=x0 + b,
                width=b - a, width_cm=U.to_cm(b - a),
                leg_cm=U.to_cm(b - a),
                is_pass=False, is_corner=True))

    # ---- Freie Abschnitte zwischen den Ecken fuellen ----------------------
    frei = []
    cursor = 0.0
    for e in ecken:
        frei.append((cursor, e['sc'] - e['leg'], cursor > 1e-9, True))
        cursor = e['sc'] + e['leg']
    frei.append((cursor, Lges, cursor > 1e-9, False))

    for s_a, s_b, ecke_am_anfang, ecke_am_ende in frei:
        L = s_b - s_a
        if L <= 1e-9:
            continue
        # Passelement direkt an die Ecke legen
        if ecke_am_anfang:
            lage = 1                                    # am Anfang
        elif ecke_am_ende:
            lage = 0                                    # am Ende
        else:
            lage = p['pass_lage']
        parts = split_run(L, b_regel, pass_min, lage,
                          meter_halbstein=True)
        s = s_a
        for width, is_pass in parts:
            m = masse(x0 + s, x0 + s + width)
            elements.append(dict(m, s0=s, s1=s + width,
                                 x0=x0 + s, x1=x0 + s + width,
                                 width=width, width_cm=U.to_cm(width),
                                 is_pass=is_pass, is_corner=False))
            s += width

    # ---- Sortieren, nummerieren, Laufindex --------------------------------
    elements.sort(key=lambda d: d['s0'])

    # ---- Mindest-Abtreppung der Oberkante ---------------------------------
    stufe = U.cm(p.get('stufe_min', 0.0) or 0.0)
    if stufe > 0 and p['hoehen_mode'] != 3:
        vorher = None
        for e in elements:
            need_top = e.get('need_top')
            need_bot = e.get('need_bot')
            if need_top is None or need_bot is None:
                continue
            if vorher is None:
                top = need_top
            else:
                d = need_top - vorher
                if d > 1e-9:
                    # steigend: entweder voller Sprung oder Mindeststufe
                    top = need_top if d >= stufe else vorher + stufe
                elif d < -stufe:
                    top = need_top            # deutlich fallend -> abtreppen
                else:
                    top = vorher              # zu kleine Aenderung -> halten
            h_cm, too_small = pick_height(U.to_cm(top - need_bot), heights)
            H = U.cm(h_cm)
            e['h_cm'] = h_cm
            if p['hoehen_mode'] == 1:
                e['ybot'] = need_bot
            elif p['hoehen_mode'] == 2:
                e['ybot'] = need_bot - (H - (top - need_bot)) / 2.0
            else:
                e['ybot'] = top - H
            e['ytop'] = e['ybot'] + H
            e['req_cm'] = U.to_cm(top - need_bot)
            e['top_pts'] = [(e['x0'], e['ytop']), (e['x1'], e['ytop'])]
            e['h_links_cm'] = U.to_cm(H)
            e['h_rechts_cm'] = U.to_cm(H)
            e['too_small'] = too_small
            try:
                e['fuss_cm'] = float(p.get('feet', {}).get(
                    str(int(round(h_cm))), 0.0))
            except Exception:
                e['fuss_cm'] = 0.0
            vorher = e['ytop']

    for e in elements:
        # tatsaechliche Ansichtshoehe: Gelaende-Oberkante zu Gelaende-Unterkante
        e['gelaende_links_cm'] = U.to_cm(y_at(ok_pts, e['x0'])
                                         - y_at(uk_pts, e['x0']))
        e['gelaende_rechts_cm'] = U.to_cm(y_at(ok_pts, e['x1'])
                                          - y_at(uk_pts, e['x1']))
        e['gel_uk_pts'] = profil_abschnitt(uk_pts, e['x0'], e['x1'])
    lauf = 0
    for i, e in enumerate(elements):
        e['nr'] = i + 1
        e['run'] = lauf
        if e.get('corner_part') == 'a':
            lauf += 1
        elif not e.get('corner_part') and e.get('is_corner') and e.get('teil') in (None, 'b'):
            lauf += 1
        if e.get('is_pass') and e['width_cm'] < p['pass_min'] - 0.05:
            warn.append('Element %d: Passstueck nur %.1f cm breit '
                        '(Mindestbreite %.1f cm)'
                        % (e['nr'], e['width_cm'], p['pass_min']))
        if e.pop('too_small', False):
            warn.append('Element %d: erforderlich %.1f cm > groesster '
                        'Katalogwert %.1f cm' % (e['nr'], e['req_cm'], e['h_cm']))
    return elements, warn


# ---------------------------------------------------------------------------
# Gabionenwand
# ---------------------------------------------------------------------------


def gab_breiten_laden(settings=None):
    """Eingebettete bzw. in den JSON-Einstellungen gespeicherte Breiten.

    Eine separate Gabionen-CSV wird nicht mehr benoetigt. Dadurch genuegt
    fuer die Verteilung auf andere Rechner die aktuelle Python-Datei.
    """
    daten = settings if isinstance(settings, dict) else {}
    text = daten.get('gab_breiten', '')
    werte = []
    for zeile in str(text or '').replace(';', '\n').split('\n'):
        try:
            wert = float(zeile.strip().replace(',', '.'))
        except Exception:
            continue
        if wert > 0:
            werte.append(wert)
    return werte or [float(b) for _t, b in GAB_BREITEN]


def gab_tabelle(text):
    """Breitenliste aus dem Dialogfeld - eine Zeile je Lage, von oben nach
    unten. Erlaubt sind reine Zahlen ('150') und Zeilen mit Beschriftung
    ('Lage 3: 150'); massgebend ist die letzte Zahl der Zeile.
    Rueckgabe: Liste der Breiten in cm.
    """
    breiten = []
    for zeile in (text or '').replace(';', '\n').split('\n'):
        zeile = zeile.strip()
        if not zeile:
            continue
        zahl = None
        for stueck in zeile.replace(':', ' ').replace('=', ' ').split():
            try:
                zahl = float(stueck.replace(',', '.'))
            except Exception:
                continue
        if zahl and zahl > 0:
            breiten.append(zahl)
    if not breiten:
        breiten = gab_breiten_laden()
    return breiten


def gab_breite(lage_index, breiten):
    """Breite der Gabione in cm fuer die Lage (0 = oberste Lage).
    Unterhalb der letzten Zeile gilt deren Breite weiter."""
    if not breiten:
        return 50.0
    return breiten[min(int(lage_index), len(breiten) - 1)]


def profil_abschnitt(pts, x_a, x_b):
    """Teil eines nach X sortierten Hoehenprofils inklusive Randpunkten."""
    if x_b < x_a:
        x_a, x_b = x_b, x_a
    out = [(x_a, y_at(pts, x_a))]
    out.extend((x, y) for x, y in pts if x_a + 1e-9 < x < x_b - 1e-9)
    out.append((x_b, y_at(pts, x_b)))
    sauber = [out[0]]
    for q in out[1:]:
        if abs(q[0] - sauber[-1][0]) > 1e-9:
            sauber.append(q)
        else:
            sauber[-1] = q
    return sauber


def gab_elemente(uk_pts, ok_pts, corners, x0, x1, p):
    """Zerlegt die Wand in Gabionen. Rueckgabe: (zellen, warnungen).

    Jede Zelle ist eine Gabione mit Laenge (entlang der Wand), Lagenhoehe
    und Breite (Tiefe nach hinten). Die Front steht senkrecht uebereinander,
    die Mehrbreite der unteren Lagen geht nach hinten.
    """
    breiten_liste = gab_tabelle(p.get('gab_breiten'))
    if len(breiten_liste) < 2:
        breiten_liste = gab_breiten_laden()
    L_regel = U.cm(float(p.get('gab_laenge', 2.0)) * 100.0)
    L_pass = U.cm(float(p.get('pass_min', 15.0)))
    h_lage = U.cm(float(p.get('gab_lage', 0.5)) * 100.0)
    einbinde = U.cm(float(p.get('gab_einbinde', 0.3)) * 100.0)
    ueber = U.cm(float(p.get('gab_ueber', 0.2)) * 100.0)
    staffel = U.cm(float(p.get('gab_staffel', 0.0)) * 100.0)
    warn = []
    if L_regel <= 0:
        return [], ['Die Regellaenge der Gabione muss groesser als 0 sein.']
    if h_lage <= 0:
        return [], ['Die Lagenhoehe muss groesser als 0 sein.']

    # ---- Saeulen (Laengenteilung, Ecken beruecksichtigen) -----------------
    Lges = x1 - x0
    grenzen = [0.0] + sorted(set(c['s'] for c in corners)) + [Lges]
    grenzen = sorted(set(round(g, 9) for g in grenzen
                         if -1e-9 <= g <= Lges + 1e-9))
    ecken_st = set(round(c['s'], 9) for c in corners)

    saeulen = []
    for i in range(len(grenzen) - 1):
        s_a, s_b = grenzen[i], grenzen[i + 1]
        if s_b - s_a <= 1e-9:
            continue
        lage = 1 if i > 0 else 0
        for breite, ist_pass in split_run(s_b - s_a, L_regel, L_pass, lage):
            saeulen.append({'s0': s_a, 's1': s_a + breite, 'is_pass': ist_pass})
            s_a += breite

    # ---- Ober- und Unterkante je Saeule, Abstaffelung ---------------------
    vorher = None
    for sp in saeulen:
        xa, xb = x0 + sp['s0'], x0 + sp['s1']
        uk_min, _ = y_extremes(uk_pts, xa, xb)
        uk_profil = profil_abschnitt(uk_pts, xa, xb)
        _, ok_max = y_extremes(ok_pts, xa, xb)
        soll_top = ok_max + ueber
        if staffel > 0 and vorher is not None:
            d = soll_top - vorher
            if d > 1e-9:
                top = soll_top if d >= staffel else vorher + staffel
            elif d < -staffel:
                top = soll_top
            else:
                top = vorher
        else:
            top = soll_top
        sp['x0'], sp['x1'] = xa, xb
        sp['gel_ok'] = ok_max
        sp['gel_uk'] = uk_min
        sp['gel_uk_pts'] = uk_profil
        sp['top'] = top
        sp['soll_bot'] = uk_min - einbinde
        vorher = top

    # ---- Lagen stapeln -----------------------------------------------------
    zellen = []
    nr = 0
    h_min = U.cm(float(p.get('gab_lage_min', 0.0) or 0.0) * 100.0)
    for sp in saeulen:
        hoehe = sp['top'] - sp['soll_bot']
        anzahl = max(1, int(math.ceil(hoehe / h_lage - 1e-9)))
        # Optimierung: reicht fuer die unterste Lage eine niedrigere Gabione,
        # wird die Einbindung nicht unnoetig tief.
        letzte_h = h_lage
        if anzahl >= 2 and 0 < h_min < h_lage:
            rest = hoehe - (anzahl - 1) * h_lage
            if rest <= h_min + 1e-9:
                letzte_h = h_min
        sp['bot'] = sp['top'] - ((anzahl - 1) * h_lage + letzte_h)
        sp['lagen'] = anzahl
        for k in range(anzahl):
            y_top = sp['top'] - k * h_lage
            y_bot = y_top - (letzte_h if k == anzahl - 1 else h_lage)
            b_cm = gab_breite(k, breiten_liste)
            nr += 1
            zellen.append({
                'nr': nr, 'lage': k + 1, 'lagen': anzahl,
                's0': sp['s0'], 's1': sp['s1'],
                'x0': sp['x0'], 'x1': sp['x1'],
                'width': sp['s1'] - sp['s0'],
                'width_cm': U.to_cm(sp['s1'] - sp['s0']),
                'ybot': y_bot, 'ytop': y_top,
                'h_cm': U.to_cm(y_top - y_bot),
                'b_cm': b_cm,
                'is_pass': sp['is_pass'],
                'gel_ok': sp['gel_ok'], 'gel_uk': sp['gel_uk'],
                'gel_uk_pts': list(sp['gel_uk_pts']),
                'is_corner': round(sp['s0'], 9) in ecken_st
                             or round(sp['s1'], 9) in ecken_st,
                'oberste': k == 0,
            })
            y_top = y_bot
    if not zellen:
        warn.append('Es konnten keine Gabionen gebildet werden.')
    return zellen, warn


def _linear_geklammertes_mittel(v0, v1, unten, oben):
    """Exaktes Mittel von clamp(linear(v0, v1), unten, oben)."""
    if oben <= unten:
        return 0.0
    grenzen = [0.0, 1.0]
    delta = v1 - v0
    if abs(delta) > 1e-12:
        for wert in (unten, oben):
            t = (wert - v0) / delta
            if 1e-12 < t < 1.0 - 1e-12:
                grenzen.append(t)
    grenzen = sorted(set(grenzen))

    def f(t):
        return max(unten, min(oben, v0 + delta * t))

    integral = 0.0
    for a, b in zip(grenzen, grenzen[1:]):
        integral += (f(a) + f(b)) * 0.5 * (b - a)
    return integral


def _profil_flaeche_m2(profil, v0_funktion, unten, oben):
    """Flaeche unter einem geklammerten, stueckweise linearen Profil."""
    flaeche = 0.0
    for a, b in zip(profil, profil[1:]):
        laenge_m = U.to_m(b[0] - a[0])
        mittel = _linear_geklammertes_mittel(
            v0_funktion(a[1]), v0_funktion(b[1]), unten, oben)
        flaeche += laenge_m * U.to_m(mittel)
    return flaeche


def _profilband_flaeche_m2(oben, unten):
    """Flaeche zwischen zwei Profilen mit identischen X-Stuetzstellen."""
    flaeche = 0.0
    for (o1, o2), (u1, u2) in zip(zip(oben, oben[1:]),
                                  zip(unten, unten[1:])):
        laenge_m = U.to_m(o2[0] - o1[0])
        h1 = max(0.0, U.to_m(o1[1] - u1[1]))
        h2 = max(0.0, U.to_m(o2[1] - u2[1]))
        flaeche += laenge_m * (h1 + h2) * 0.5
    return flaeche


def gab_saeulen(zellen):
    """Gabionenzellen nach Laengsabschnitt gruppiert, jeweils oben nach unten."""
    saeulen = {}
    for z in zellen:
        saeulen.setdefault((round(z['s0'], 6), round(z['s1'], 6)), []).append(z)
    for lagen in saeulen.values():
        lagen.sort(key=lambda q: -q['ytop'])
    return saeulen


def gab_fundamente(zellen, p=None):
    """Fundamentsegmente unter den Gabionen.

    Die Fundamentsohle liegt im frei gewaehlten Abstand unter UK Gelaende.
    Die Oberkante liegt an der Unterseite der tiefsten Gabione (hoechstens
    auf UK Gelaende). In der Aufsicht steht das Fundament auf allen Seiten
    um den frei gewaehlten Wert ueber.
    """
    p = p or DEFAULTS
    tiefe_cm = max(0.0, float(p.get(
        'gab_fund_tiefe', GAB_FUND_TIEFE_CM)))
    tiefe = U.cm(tiefe_cm)
    min_staerke = U.cm(10.0)
    ueber_cm = gab_fund_ueberstand_cm(p)
    ueber = U.cm(ueber_cm)
    daten = []
    saeulen = gab_saeulen(zellen)
    schluessel = sorted(saeulen)
    if not schluessel:
        return daten
    gesamt_s0 = min(sch[0] for sch in schluessel)
    gesamt_s1 = max(sch[1] for sch in schluessel)
    for sch, lagen in sorted(saeulen.items()):
        tiefste = lagen[-1]
        profil = tiefste.get('gel_uk_pts') or [
            (tiefste['x0'], tiefste.get('gel_uk', tiefste['ybot'])),
            (tiefste['x1'], tiefste.get('gel_uk', tiefste['ybot']))]
        profil = list(profil)
        y_top = tiefste['ybot']
        # Die gewaehlte Tiefe unter Gelaende ist die Mindesttiefe. Reicht die Gabione
        # tiefer, wird die Sohle so weit abgesenkt, dass 10 cm Fundament
        # verbleiben, statt ein physikalisch unmoegliches Nullfundament zu
        # melden.
        basis = [(x, min(y - tiefe, y_top - min_staerke)) for x, y in profil]
        oben = [(x, max(yb, min(y_top, y)))
                for (x, y), (_xb, yb) in zip(profil, basis)]
        # Allseitig bedeutet auch Ueberstand am Anfang und Ende der gesamten
        # Wand. An inneren Element-/Breitenwechseln wird nichts doppelt
        # angesetzt.
        links = ueber if abs(sch[0] - gesamt_s0) <= 1e-6 else 0.0
        rechts = ueber if abs(sch[1] - gesamt_s1) <= 1e-6 else 0.0
        if links > 0.0:
            profil.insert(0, (profil[0][0] - links, profil[0][1]))
            basis.insert(0, (basis[0][0] - links, basis[0][1]))
            oben.insert(0, (oben[0][0] - links, oben[0][1]))
        if rechts > 0.0:
            profil.append((profil[-1][0] + rechts, profil[-1][1]))
            basis.append((basis[-1][0] + rechts, basis[-1][1]))
            oben.append((oben[-1][0] + rechts, oben[-1][1]))
        querschnitt_m2 = _profilband_flaeche_m2(oben, basis)
        laenge_m = U.to_m(tiefste['width'] + links + rechts)
        breite_cm = float(tiefste['b_cm']) + 2.0 * ueber_cm
        breite_m = breite_cm / 100.0
        eck_faktor = max(0.0, float(tiefste.get(
            '_gab_fund_eck_faktor', 1.0)))
        daten.append({
            's0': sch[0], 's1': sch[1],
            'x0': basis[0][0], 'x1': basis[-1][0],
            'y_top': y_top, 'basis_pts': basis, 'top_pts': oben,
            'gel_pts': list(profil), 'tiefe_cm': tiefe_cm,
            'gab_b_cm': float(tiefste['b_cm']),
            'ueberstand_cm': ueber_cm,
            'breite_cm': breite_cm, 'breite_units': U.cm(breite_cm),
            'ueberstand_units': ueber,
            'laenge_m': laenge_m,
            'flaeche_m2': laenge_m * breite_m * eck_faktor,
            'volumen_m3': querschnitt_m2 * breite_m * eck_faktor,
            'querschnitt_m2': querschnitt_m2,
        })
    return daten


def winkel_fundamente(elements, p):
    """Fundamentsegmente der armierten und unarmierten Winkelsteine.

    Die Fundamentsohle folgt UK Gelaende im vorgegebenen Abstand. Das
    Fundament reicht bis zur Unterseite des Winkelfusses; der Erdaushub wird
    ueber die volle Tiefe von UK Gelaende bis zur Fundamentsohle berechnet.
    """
    tiefe_cm = max(0.0, float(p.get('fund_tiefe', WINKEL_FUND_TIEFE_CM)))
    ueber_cm = max(0.0, float(p.get(
        'fund_ueberstand', WINKEL_FUND_UEBERSTAND_CM)))
    tiefe = U.cm(tiefe_cm)
    daten = []
    for e in elements:
        profil = e.get('gel_uk_pts') or [
            (e['x0'], e['ybot'] + U.cm(p.get('unter_uk', 0.0))),
            (e['x1'], e['ybot'] + U.cm(p.get('unter_uk', 0.0)))]
        y_top = e['ybot']
        basis = [(x, y - tiefe) for x, y in profil]
        oben = [(x, max(y - tiefe, min(y_top, y))) for x, y in profil]
        querschnitt_m2 = _profil_flaeche_m2(
            profil, lambda gel: y_top + tiefe - gel, 0.0, tiefe)
        fuss_cm = max(float(e.get('fuss_cm', 0.0)),
                      float(p.get('dicke_cm', 0.0)))
        breite_cm = fuss_cm + 2.0 * ueber_cm
        laenge_m = U.to_m(e['width'])
        breite_m = breite_cm / 100.0
        eck_faktor = max(0.0, float(e.get('_fund_eck_faktor', 1.0)))
        daten.append({
            'nr': e.get('nr'), 's0': e['s0'], 's1': e['s1'],
            'basis_pts': basis, 'top_pts': oben,
            'gel_pts': list(profil), 'tiefe_cm': tiefe_cm,
            'fuss_cm': fuss_cm, 'breite_cm': breite_cm,
            'ueberstand_cm': ueber_cm,
            'laenge_m': laenge_m,
            'aufsicht_m2': laenge_m * breite_m * eck_faktor,
            'volumen_m3': querschnitt_m2 * breite_m * eck_faktor,
            'aushub_m3': (laenge_m * breite_m * tiefe_cm / 100.0
                          * eck_faktor),
        })
    return daten


def gab_summen(zellen, p):
    """Kennwerte je Gabionenbreite einschliesslich Fundament und Aushub."""
    reihen = {}

    for z in zellen:
        b = round(z['b_cm'], 1)
        r = reihen.setdefault(b, {'b_cm': b, 'anzahl': 0, 'laenge_m': 0.0,
                                  'front_m2': 0.0, 'sicht_m2': 0.0,
                                  'kopf_m2': 0.0, 'volumen_m3': 0.0,
                                  'rueck_m2': 0.0, 'fund_laenge_m': 0.0,
                                  'sohle_m2': 0.0, 'fund_m2': 0.0,
                                  'fund_volumen_m3': 0.0,
                                  'gab_unter_gel_m3': 0.0,
                                  'aushub_m3': 0.0})
        laenge = U.to_m(z['width'])
        hoehe = U.to_m(z['ytop'] - z['ybot'])
        front = laenge * hoehe
        r['anzahl'] += 1
        r['laenge_m'] += laenge
        r['front_m2'] += front
        r['volumen_m3'] += front * b / 100.0
        r['rueck_m2'] += front
        profil = z.get('gel_uk_pts') or [
            (z['x0'], z.get('gel_uk', z['ybot'])),
            (z['x1'], z.get('gel_uk', z['ybot']))]
        verdeckt_m2 = _profil_flaeche_m2(
            profil, lambda gel: gel - z['ybot'], 0.0, z['ytop'] - z['ybot'])
        r['sicht_m2'] += max(0.0, front - verdeckt_m2)
        r['gab_unter_gel_m3'] += verdeckt_m2 * b / 100.0
        if z.get('oberste'):
            r['kopf_m2'] += laenge * b / 100.0

    # Offene Kopfflaechen und Sohlaufstand der tiefsten Gabione je Saeule.
    for lagen in gab_saeulen(zellen).values():
        for oben, unten in zip(lagen, lagen[1:]):
            zuwachs = (unten['b_cm'] - oben['b_cm']) / 100.0
            if zuwachs > 0:
                reihen[round(unten['b_cm'], 1)]['rueck_m2'] += \
                    U.to_m(unten['width']) * zuwachs
        tiefste = lagen[-1]
        r = reihen[round(tiefste['b_cm'], 1)]
        laenge = U.to_m(tiefste['width'])
        r['sohle_m2'] += laenge * tiefste['b_cm'] / 100.0

    # Fundamentmengen werden der Breite der jeweils tiefsten Gabione
    # zugeordnet. So bleiben die Typzeilen und ihre Summen nachvollziehbar.
    for fund in gab_fundamente(zellen, p):
        r = reihen[round(fund['gab_b_cm'], 1)]
        r['fund_laenge_m'] += fund['laenge_m']
        r['fund_m2'] += fund['flaeche_m2']
        r['fund_volumen_m3'] += fund['volumen_m3']

    for r in reihen.values():
        r['aushub_m3'] = r['fund_volumen_m3'] + r['gab_unter_gel_m3']
    return [reihen[k] for k in sorted(reihen)]


def y_on_top(top_pts, x):
    """Hoehe der Elementoberkante an der Stelle x."""
    if not top_pts:
        return 0.0
    if len(top_pts) == 1:
        return top_pts[0][1]
    for i in range(len(top_pts) - 1):
        x1, y1 = top_pts[i]
        x2, y2 = top_pts[i + 1]
        if min(x1, x2) - 1e-9 <= x <= max(x1, x2) + 1e-9:
            if abs(x2 - x1) < 1e-12:
                return max(y1, y2)
            return y1 + (x - x1) / (x2 - x1) * (y2 - y1)
    return top_pts[-1][1]


def draw_abwicklung(elements, p, colors):
    prefix = p['prefix']
    txt_cls = prefix + 'TXT'
    off = text_metrics(p)[0] * 0.2
    deckkraft = max(0.0, 100.0 - p.get('transparenz', 0.0))
    for fund in winkel_fundamente(elements, p):
        punkte = list(fund['basis_pts']) + list(reversed(fund['top_pts']))
        make_filled_poly(punkte, prefix + 'FUNDAMENT', fundament_rgb(p),
                         deckkraft)
    for e in elements:
        cls = class_name_for_height(prefix, e['h_cm'])
        rgb = colors.get(int(round(e['h_cm'])), (52000, 52000, 52000))
        top = e.get('top_pts') or [(e['x0'], e['ytop']), (e['x1'], e['ytop'])]
        pts = [(e['x0'], e['ybot']), (e['x1'], e['ybot'])] + list(reversed(top))
        make_filled_poly(pts, cls, rgb, deckkraft)

        # Eckelement: Trennlinie zwischen den beiden Schenkeln
        if e.get('sc') is not None and e['s0'] < e['sc'] < e['s1']:
            xc = e['x0'] + (e['sc'] - e['s0'])
            _dline(xc, e['ybot'], xc, y_on_top(top, xc), cls)

        set_text_style(p['font'], p['font_size'])
        # Nummer unten links
        make_text(str(e['nr']), e['x0'] + off, e['ybot'] + off, 0, 1, 4, txt_cls)
        # Hoehe (und ggf. Passlaenge / Eckwinkel) im Element
        if e.get('parallel'):
            label = 'H %.0f-%.0f' % (e.get('h_links_cm', 0), e.get('h_rechts_cm', 0))
        else:
            label = 'H %g' % e['h_cm']
        if e.get('is_corner'):
            hoehe = ('H %.0f-%.0f' % (e.get('h_links_cm', 0), e.get('h_rechts_cm', 0))
                     if e.get('parallel') else 'H %g' % e['h_cm'])
            if e.get('teil'):
                label = 'Ecke %.0f%s Schenkel %s / %s / %.0f' % (
                    e.get('angle', 90.0), chr(176), e['teil'], hoehe,
                    e.get('leg_cm', 50.0))
            else:
                label = 'Ecke %.0f%s / %s / 2 x %.0f' % (
                    e.get('angle', 90.0), chr(176), hoehe,
                    e.get('leg_cm', 50.0))
        elif e['is_pass']:
            label += ' / P %.0f' % e['width_cm']
        cx = (e['x0'] + e['x1']) / 2.0
        cy = (e['ybot'] + e['ytop']) / 2.0
        rot = 90.0 if p['txt_rot'] else 0.0
        make_text(label, cx, cy, rot, 2, 2, txt_cls)

    if p.get('ref_aktiv'):
        draw_koten_abwicklung(elements, p)
    if p.get('bemassung'):
        draw_dims_abwicklung(elements, p)


def draw_aufsicht(elements, pl_pts, st_tab, p, colors, reverse,
                  breaks=None, L_ges=None):
    prefix = p['prefix']
    txt_cls = prefix + 'TXT'
    d = U.cm(p['dicke_cm'])
    total = st_tab[-1]
    sign = 1.0 if p['seite'] == 0 else -1.0
    if L_ges is None:
        L_ges = max((e['s1'] for e in elements), default=total)
    laeufe_gesehen = set()
    hoehen_gesehen = set()
    lauf_enden = {}
    deckkraft = max(0.0, 100.0 - p.get('transparenz', 0.0))
    fund_quermasse = []

    def station(sw):
        return (total - sw) if reverse else sw

    # Die am Knick liegenden 50-cm-Steine sind zwei eigenstaendige
    # Regelelemente. An einer Innenecke der Mauervorderseite liegt der Fuss
    # auf der geometrischen Aussenseite des Linienknicks. Dort behalten beide
    # Steine ihre vollstaendigen rechteckigen Koerper.
    eckgruppen = {}
    for e in elements:
        sc = e.get('corner_station')
        if sc is not None:
            eckgruppen.setdefault(round(float(sc), 9), []).append(e)
    eckkoerper = {}
    for sc_key, gruppe in eckgruppen.items():
        if len(gruppe) != 2:
            continue
        sc_plan = station(float(sc_key))
        intervalle = []
        for e in gruppe:
            a, b = station(e['s0']), station(e['s1'])
            intervalle.append((min(a, b), max(a, b), e))
        s_a = min(q[0] for q in intervalle)
        s_b = max(q[1] for q in intervalle)
        pa, _ = point_at_station(pl_pts, st_tab, s_a)
        pc, _ = point_at_station(pl_pts, st_tab, sc_plan)
        pb, _ = point_at_station(pl_pts, st_tab, s_b)
        koerper_a, koerper_b = geteilte_eckkoerper(pa, pc, pb, sign, d)
        if koerper_a is None or koerper_b is None:
            continue
        for a, b, e in intervalle:
            eckkoerper[e['nr']] = (koerper_a if abs(b - sc_plan) <= 1e-6
                                   else koerper_b)

    # Fundament vor allen Winkelsteinen aus einfachen, gueltigen Teilflaechen
    # bilden und in Vectorworks vereinigen. So werden Innenueberdeckungen
    # entfernt und Aussengehrungen ergaenzt, ohne selbstschneidende Polygone.
    fundamente = winkel_fundamente(elements, p)
    fund_abschnitte = [
        (station(fund['s0']), station(fund['s1']),
         U.cm(fund['fuss_cm'] + fund['ueberstand_cm']), nr)
        for nr, fund in enumerate(fundamente)]
    fund_ueberstand = max(
        (float(fund['ueberstand_cm']) for fund in fundamente), default=0.0)
    fund_polygone = band_primitiven(
        pl_pts, st_tab, fund_abschnitte, U.cm(fund_ueberstand), sign)
    draw_surface_union(
        fund_polygone, prefix + 'FUNDAMENT', fundament_rgb(p), True,
        deckkraft)

    # Gleiche Fundamentbreiten nur fuer die Anzahl und Lage der Quermasse
    # zusammenfassen; die Fundamentflaeche selbst ist bereits durchgehend.
    fund_lauefe = []
    for fund in fundamente:
        if (fund_lauefe and
                abs(fund_lauefe[-1]['s1'] - fund['s0']) <= 1e-6 and
                abs(fund_lauefe[-1]['breite_cm'] - fund['breite_cm']) <= 1e-6):
            fund_lauefe[-1]['s1'] = fund['s1']
            fund_lauefe[-1]['aufsicht_m2'] += fund['aufsicht_m2']
        else:
            fund_lauefe.append(dict(fund))
    for fund in fund_lauefe:
        sm = station((fund['s0'] + fund['s1']) / 2.0)
        q, richt = point_at_station(pl_pts, st_tab, sm)
        ux, uy = richt
        nx, ny = -uy * sign, ux * sign
        fund_quermasse.append((
            (q[0] - nx * U.cm(fund['ueberstand_cm']),
             q[1] - ny * U.cm(fund['ueberstand_cm'])),
            (q[0] + nx * U.cm(fund['fuss_cm'] + fund['ueberstand_cm']),
             q[1] + ny * U.cm(fund['fuss_cm'] + fund['ueberstand_cm'])),
            fund['breite_cm']))

    # Winkelsteinfuesse nach demselben Prinzip vereinigen. Unterschiedliche
    # Fusslaengen duerfen am Knick weder geschlossene Endkappen noch Luecken
    # erzeugen.
    if p.get('fuss_zeichnen'):
        fuss_abschnitte = [
            (station(e['s0']), station(e['s1']),
             U.cm(max(float(p.get('dicke_cm', 0.0)),
                      float(e.get('fuss_cm', 0.0)))), nr)
            for nr, e in enumerate(elements)]
        fuss_polygone = winkel_fuss_primitiven(
            pl_pts, st_tab, fuss_abschnitte, sign)
        draw_surface_union(
            fuss_polygone, prefix + 'FUSS', None, False, 100.0,
            p.get('fuss_ls', ''))

    # Innerhalb eines durchgehenden Fussbandes bleiben die Steinfugen
    # sichtbar. Am Mauerknick werden keine zusaetzlichen Fugen erzeugt: Die
    # zwei getrennten Inneneck-Rechtecke besitzen dort bereits ihre eigenen
    # vollstaendigen Endkanten.
    if p.get('fuss_zeichnen'):
        geordnet = sorted(elements, key=lambda q: (q['s0'], q['s1']))
        knicke = list(st_tab[1:-1])
        for links, rechts in zip(geordnet, geordnet[1:]):
            if abs(links['s1'] - rechts['s0']) > 1e-6:
                continue
            f_links = max(float(p.get('dicke_cm', 0.0)),
                          float(links.get('fuss_cm', 0.0)))
            f_rechts = max(float(p.get('dicke_cm', 0.0)),
                           float(rechts.get('fuss_cm', 0.0)))
            if max(f_links, f_rechts) <= 1e-9:
                continue
            sm = station(links['s1'])
            if any(abs(sm - k) <= 1e-6 for k in knicke):
                continue
            q, richt = point_at_station(pl_pts, st_tab, sm)
            ux, uy = richt
            nx, ny = -uy * sign, ux * sign
            apply_attrs(prefix + 'FUSS', None, False)
            set_new_line_style(p.get('fuss_ls', ''))
            vs.MoveTo(q[0] + nx * d, q[1] + ny * d)
            f_gemeinsam = min(f_links, f_rechts)
            if f_gemeinsam <= float(p.get('dicke_cm', 0.0)) + 1e-9:
                set_new_line_style('')
                continue
            vs.LineTo(q[0] + nx * U.cm(f_gemeinsam),
                      q[1] + ny * U.cm(f_gemeinsam))
            _reg(vs.LNewObj())
            set_new_line_style('')

    for e in elements:
        s0, s1 = e['s0'], e['s1']
        sc = e.get('sc')
        if reverse:
            s0, s1 = total - e['s1'], total - e['s0']
            if sc is not None:
                sc = total - e['sc']

        # Eckelement: zwei Schenkel, sonst ein Stueck
        if sc is not None and s0 < sc < s1:
            teile = [(s0, sc), (sc, s1)]
        else:
            teile = [(s0, s1)]

        cls = class_name_for_height(prefix, e['h_cm'])
        rgb = colors.get(int(round(e['h_cm'])), (52000, 52000, 52000))
        erstes_teil = True
        mitte = None

        # Eckelement: Mauerkoerper als ein gemitertes Sonderelement. Der Fuss
        # wurde bereits oben als durchgehendes Band gezeichnet.
        eck_gezeichnet = False
        regel_eckkoerper = eckkoerper.get(e['nr'])
        if regel_eckkoerper:
            make_filled_poly(regel_eckkoerper, cls, rgb, deckkraft)
            eck_gezeichnet = True
        elif len(teile) == 2:
            qa, _r1 = point_at_station(pl_pts, st_tab, teile[0][0])
            qc, _r2 = point_at_station(pl_pts, st_tab, teile[0][1])
            qb, _r3 = point_at_station(pl_pts, st_tab, teile[1][1])
            koerper, _fussflaeche = eck_polygone(
                qa, qc, qb, sign, d, 0.0)
            if koerper:
                make_filled_poly(koerper, cls, rgb, deckkraft)
                eck_gezeichnet = True

        for sa, sb in teile:
            pa, _ = point_at_station(pl_pts, st_tab, sa)
            pb, _ = point_at_station(pl_pts, st_tab, sb)
            dx, dy = pb[0] - pa[0], pb[1] - pa[1]
            L = math.hypot(dx, dy)
            if L < 1e-12:
                continue
            ux, uy = dx / L, dy / L
            nx, ny = -uy * sign * d, ux * sign * d

            if not eck_gezeichnet:
                pts = [(pa[0], pa[1]), (pb[0], pb[1]),
                       (pb[0] + nx, pb[1] + ny), (pa[0] + nx, pa[1] + ny)]
                make_filled_poly(pts, cls, rgb, deckkraft)

            if erstes_teil:
                ang = math.degrees(math.atan2(uy, ux))
                if ang > 90.0:
                    ang -= 180.0
                if ang < -90.0:
                    ang += 180.0
                nlen = math.hypot(nx, ny) or 1.0
                mitte = ((pa[0] + pb[0]) / 2.0 + nx / 2.0,
                         (pa[1] + pb[1]) / 2.0 + ny / 2.0, ang,
                         (nx / nlen, ny / nlen))

            if p.get('bemassung'):
                run = e.get('run', 0)
                hoe = int(round(e['h_cm']))
                laenge_cm = U.to_cm(L)
                draw_dims_aufsicht_element(
                    e, pa, pb, ux, uy, sign, p,
                    run not in laeufe_gesehen, hoe not in hoehen_gesehen,
                    laenge_cm)
                laeufe_gesehen.add(run)
                hoehen_gesehen.add(hoe)
                if run not in lauf_enden:
                    lauf_enden[run] = [pa, pb, laenge_cm]
                else:
                    lauf_enden[run][1] = pb
                    lauf_enden[run][2] += laenge_cm
            erstes_teil = False

        # Beschriftung
        if mitte is not None:
            if e.get('is_corner'):
                hoehe = ('H %.0f-%.0f' % (e.get('h_links_cm', 0),
                                          e.get('h_rechts_cm', 0))
                         if e.get('parallel') else 'H %g' % e['h_cm'])
                if e.get('teil'):
                    label = '%d | Ecke %.0f%s %s | %s | %.0f' % (
                        e['nr'], e.get('angle', 90.0), chr(176), e['teil'],
                        hoehe, e.get('leg_cm', 50.0))
                else:
                    label = '%d | Ecke %.0f%s | %s | 2 x %.0f' % (
                        e['nr'], e.get('angle', 90.0), chr(176), hoehe,
                        e.get('leg_cm', 50.0))
            elif e.get('parallel'):
                label = '%d | H %.0f-%.0f' % (e['nr'], e.get('h_links_cm', 0),
                                              e.get('h_rechts_cm', 0))
                if e['is_pass']:
                    label += ' | P %.0f' % e['width_cm']
            else:
                label = '%d | H %g' % (e['nr'], e['h_cm'])
                if e['is_pass']:
                    label += ' | P %.0f' % e['width_cm']
            set_text_style(p['font'], p['font_size'])
            make_text(label, mitte[0], mitte[1], mitte[2], 2, 2, txt_cls)
            if p['ref_aktiv'] and mitte[3] is not None:
                th = text_metrics(p)[0]
                ox, oy = mitte[3]          # Einheitsnormale zur Mauerseite
                mx = mitte[0] - ox * d / 2.0     # Mitte auf der Aussenkante
                my = mitte[1] - oy * d / 2.0
                # Unterkante: parallel zur Mauer, auf der anderen Seite
                make_text('UK ' + kote_text(p, e['ybot']),
                          mx - ox * th * 0.8, my - oy * th * 0.8,
                          mitte[2], 2, 2, prefix + 'KOTE')
                if not e.get('parallel'):
                    # Abgetreppt: Oberkante auf der Innenkante der Mauer
                    make_text('OK ' + kote_text(p, e['ytop']),
                              mx + ox * (d + th * 0.7),
                              my + oy * (d + th * 0.7),
                              mitte[2], 2, 2, prefix + 'KOTE')

    if p.get('bemassung'):
        set_text_style(p['font'], p['font_size'])
        fund_cls = prefix + 'FUNDAMENT-BEM'
        for pa, pb, breite_cm in eindeutige_fundament_quermasse(
                fund_quermasse):
            dim_between(pa, pb, dim_abstand_units(p) * 0.65,
                        'B Fund. = %s cm' % fmt_cm(breite_cm),
                        fund_cls, p, kurz=True)

    # Parallelmodus: Oberkante gedreht an Anfang, Ende und jedem Anschluss
    if p.get('ref_aktiv') and any(e.get('parallel') for e in elements):
        th = text_metrics(p)[0]
        cls_k = prefix + 'KOTE'
        # ausserhalb der Fussflaeche ansetzen, damit die Koten nicht durch
        # die Quermasse im Fussbereich laufen
        aussen = max(d, max((U.cm(e.get('fuss_cm', 0.0)) for e in elements),
                            default=0.0))
        stellen = []
        for e in elements:
            top = e.get('top_pts') or [(e['x0'], e['ytop']), (e['x1'], e['ytop'])]
            stellen.append((e['s0'], y_on_top(top, e['x0'])))
        letzt = elements[-1]
        top = letzt.get('top_pts') or [(letzt['x0'], letzt['ytop']),
                                       (letzt['x1'], letzt['ytop'])]
        stellen.append((letzt['s1'], y_on_top(top, letzt['x1'])))
        gesehen = set()
        set_text_style(p['font'], p['font_size'])
        for st_wert, yo in stellen:
            schl = round(st_wert, 6)
            if schl in gesehen:
                continue
            gesehen.add(schl)
            ss = (total - st_wert) if reverse else st_wert
            q, richt = point_at_station(pl_pts, st_tab, ss)
            ux, uy = richt
            nx, ny = -uy * sign, ux * sign
            ang_n = math.degrees(math.atan2(ny, nx))
            if -90.0 <= ang_n <= 90.0:
                just, ang_t = 1, ang_n
            else:
                just = 3
                ang_t = ang_n - 180.0 if ang_n > 0 else ang_n + 180.0
            make_text('OK ' + kote_text(p, yo),
                      q[0] + nx * (aussen + th * 0.9),
                      q[1] + ny * (aussen + th * 0.9),
                      ang_t, just, 2, cls_k)

    # Gesamtlaenge je gerader Mauerstrecke - direkt aus der Geometrie
    if p.get('bemassung'):
        cls = prefix + 'BEM'
        grenzen = [0.0] + sorted(set(breaks or [])) + [L_ges]
        grenzen = sorted(set(round(g, 9) for g in grenzen
                             if -1e-9 <= g <= L_ges + 1e-9))
        for i in range(len(grenzen) - 1):
            sa, sb = grenzen[i], grenzen[i + 1]
            if sb - sa <= 1e-9:
                continue
            if reverse:
                sa, sb = total - sb, total - sa
            qa, _ = point_at_station(pl_pts, st_tab, sa)
            qb, _ = point_at_station(pl_pts, st_tab, sb)
            strecke = math.hypot(qb[0] - qa[0], qb[1] - qa[1])
            dim_between(qa, qb, -sign * dim_abstand_units(p) * 1.9,
                        'L = %.2f m' % U.to_m(strecke), cls, p, kurz=True)


def table_frame(x, y_oben, breite, y_unten, cols, cw, cls):
    """Rahmen und Spaltentrenner - damit die Tabelle wie eine Tabelle aussieht."""
    rand = cw * 0.4
    x1 = x - rand
    x2 = x + breite - rand
    _dline(x1, y_oben, x2, y_oben, cls)
    _dline(x1, y_unten, x2, y_unten, cls)
    _dline(x1, y_oben, x1, y_unten, cls)
    _dline(x2, y_oben, x2, y_unten, cls)
    for c in cols[1:]:
        _dline(x + c - rand, y_oben, x + c - rand, y_unten, cls)


def draw_table(elements, p, x, y):
    """Summenliste als Text in die Zeichnung schreiben.
    Rueckgabe: Y-Wert der letzten Zeile."""
    cls = p['prefix'] + 'TABELLE'
    rows = summarize(elements, p)
    th, line_h, cw = text_metrics(p)
    header = ['Typ', 'Hoehe [cm]', 'Breite [cm]', 'Anzahl', 'Laenge [m]',
              'Fund.-Aufsicht [m2]', 'Fundament [m3]', 'Aushub [m3]']
    breiten = [24, 11, 12, 8, 11, 21, 16, 13]
    breiten = [max(b, len(t) + 2) for b, t in zip(breiten, header)]
    cols, acc = [], 0.0
    for b in breiten:
        cols.append(acc)
        acc += b * cw
    gesamt = acc
    set_text_style(p['font'], p['font_size'])

    yy = y
    make_text('SUMMENLISTE MAUERWINKEL  (%s)'
              % datetime.datetime.now().strftime('%d.%m.%Y'),
              x, yy, 0, 1, 4, cls, kollision=False)
    yy -= line_h * 1.6
    for i, t in enumerate(header):
        make_text(t, x + cols[i], yy, 0, 1, 4, cls, kollision=False)
    yy -= line_h * 0.35
    _dline(x, yy, x + gesamt, yy, cls)
    yy -= line_h

    total_n, total_l = 0, 0.0
    total_fa, total_fv, total_au = 0.0, 0.0, 0.0
    for r in rows:
        vals = [r['typ'], '%g' % r['h_cm'], fmt_cm(r['b_cm']),
                '%d' % r['anzahl'], '%.2f' % r['laenge_m'],
                '%.2f' % r['fund_aufsicht_m2'],
                '%.2f' % r['fund_volumen_m3'],
                '%.2f' % r['aushub_m3']]
        for i, t in enumerate(vals):
            make_text(t, x + cols[i], yy, 0, 1, 4, cls, kollision=False)
        total_n += r['anzahl']
        total_l += r['laenge_m']
        total_fa += r['fund_aufsicht_m2']
        total_fv += r['fund_volumen_m3']
        total_au += r['aushub_m3']
        yy -= line_h

    yy -= line_h * 0.25
    _dline(x, yy, x + gesamt, yy, cls)
    yy -= line_h
    make_text('SUMME', x, yy, 0, 1, 4, cls, kollision=False)
    make_text('%d' % total_n, x + cols[3], yy, 0, 1, 4, cls, kollision=False)
    make_text('%.2f' % total_l, x + cols[4], yy, 0, 1, 4, cls, kollision=False)
    make_text('%.2f' % total_fa, x + cols[5], yy, 0, 1, 4, cls, kollision=False)
    make_text('%.2f' % total_fv, x + cols[6], yy, 0, 1, 4, cls, kollision=False)
    make_text('%.2f' % total_au, x + cols[7], yy, 0, 1, 4, cls, kollision=False)
    unten = yy - line_h * 0.35
    table_frame(x, y + line_h * 0.9, gesamt, unten, cols, cw, cls)
    return unten


def element_rows(elements, p=None):
    """Zeilen der Einzelliste: je Mauerwinkel eine Zeile.
    Ausnahme: Eckelemente im Parallelmodus werden als zwei Zeilen gefuehrt -
    je Schenkel eine, mit den Hoehen links und rechts des Schenkels. Die
    Fundament-Aufsichtsflaeche wird je Zeile bzw. Schenkel ausgewiesen.
    """
    rows = []
    fundamente = winkel_fundamente(elements, p or DEFAULTS)
    for e, fund in zip(elements, fundamente):
        if e.get('is_corner'):
            typ = 'Ecke %.0f%s' % (e.get('angle', 90.0), chr(176))
            if e.get('teil'):
                typ += ' Schenkel ' + e['teil']
            if e.get('parallel') and e.get('sc') is not None:
                xc = e['x0'] + (e['sc'] - e['s0'])
                top = e.get('top_pts') or [(e['x0'], e['ytop']),
                                           (e['x1'], e['ytop'])]
                yb = e['ybot']
                h_a = U.to_cm(y_on_top(top, e['x0']) - yb)
                h_m = U.to_cm(y_on_top(top, xc) - yb)
                h_b = U.to_cm(y_on_top(top, e['x1']) - yb)
                for suffix, br, hl, hr in (
                        ('a', xc - e['x0'], h_a, h_m),
                        ('b', e['x1'] - xc, h_m, h_b)):
                    rows.append({
                        'nr': '%d%s' % (e['nr'], suffix),
                        'typ': typ + ' Schenkel ' + suffix,
                        'breite': fmt_cm(U.to_cm(br)),
                        'breite_cm': U.to_cm(br),
                        'h_links_cm': hl,
                        'h_rechts_cm': hr,
                        'bestell_cm': e['h_cm'],
                        'fund_aufsicht_m2': (U.to_m(br)
                                             * fund['breite_cm'] / 100.0
                                             * float(e.get(
                                                 '_fund_eck_faktor', 1.0))),
                    })
                continue
            breite = (fmt_cm(e['width_cm']) if e.get('teil')
                      else '2 x %.0f' % e.get('leg_cm', 50.0))
        elif e['is_pass']:
            typ = 'Pass'
            breite = fmt_cm(e['width_cm'])
        else:
            typ = 'Regel'
            breite = fmt_cm(e['width_cm'])
        rows.append({
            'nr': '%d' % e['nr'],
            'typ': typ,
            'breite': breite,
            'breite_cm': e['width_cm'],
            'h_links_cm': e.get('h_links_cm', e['h_cm']),
            'h_rechts_cm': e.get('h_rechts_cm', e['h_cm']),
            'bestell_cm': e['h_cm'],
            'fund_aufsicht_m2': fund['aufsicht_m2'],
        })
    return rows


def draw_element_table(elements, p, x, y):
    """Tabelle mit jedem einzelnen Mauerwinkel. Rueckgabe: Y der letzten Zeile."""
    cls = p['prefix'] + 'TABELLE'
    rows = element_rows(elements, p)
    th, line_h, cw = text_metrics(p)
    header = ['Nr', 'Typ', 'Breite [cm]', 'Hoehe links [cm]',
              'Hoehe rechts [cm]', 'Bestellhoehe [cm]',
              'Fund.-Aufsicht [m2]']
    breiten = [6, 20, 13, 18, 19, 18, 20]
    breiten = [max(b, len(t) + 2) for b, t in zip(breiten, header)]
    cols, acc = [], 0.0
    for b in breiten:
        cols.append(acc)
        acc += b * cw
    gesamt = acc
    set_text_style(p['font'], p['font_size'])

    yy = y
    make_text('EINZELLISTE MAUERWINKEL', x, yy, 0, 1, 4, cls, kollision=False)
    yy -= line_h * 1.6
    for i, t in enumerate(header):
        make_text(t, x + cols[i], yy, 0, 1, 4, cls, kollision=False)
    yy -= line_h * 0.35
    _dline(x, yy, x + gesamt, yy, cls)
    yy -= line_h

    for r in rows:
        vals = [str(r['nr']), r['typ'], r['breite'],
                fmt_cm(r['h_links_cm']), fmt_cm(r['h_rechts_cm']),
                fmt_cm(r['bestell_cm']), '%.2f' % r['fund_aufsicht_m2']]
        for i, t in enumerate(vals):
            make_text(t, x + cols[i], yy, 0, 1, 4, cls, kollision=False)
        yy -= line_h
    unten = yy + line_h * 0.65
    table_frame(x, y + line_h * 0.9, gesamt, unten, cols, cw, cls)
    return unten


def summarize(elements, p):
    """Gruppiert Elemente sowie Fundament- und Aushubmengen nach Typ."""
    agg = {}
    fundamente = winkel_fundamente(elements, p)
    for e, fund in zip(elements, fundamente):
        if e.get('is_corner'):
            if e.get('teil'):
                typ = 'Eckschenkel %.0f%s' % (e.get('angle', 90.0), chr(176))
            else:
                typ = 'Eckelement %.0f%s (2 x %.0f)' % (
                    e.get('angle', 90.0), chr(176), e.get('leg_cm', 50.0))
        elif e['is_pass']:
            typ = 'Passelement'
        else:
            typ = 'Regelelement'
        key = (typ, round(e['h_cm'], 1), round(e['width_cm'], 1))
        if key not in agg:
            agg[key] = {'typ': typ, 'h_cm': key[1], 'b_cm': key[2],
                        'anzahl': 0, 'laenge_m': 0.0,
                        'fund_aufsicht_m2': 0.0,
                        'fund_volumen_m3': 0.0,
                        'aushub_m3': 0.0}
        agg[key]['anzahl'] += 1
        agg[key]['laenge_m'] += e['width_cm'] / 100.0
        agg[key]['fund_aufsicht_m2'] += fund['aufsicht_m2']
        agg[key]['fund_volumen_m3'] += fund['volumen_m3']
        agg[key]['aushub_m3'] += fund['aushub_m3']
    return sorted(agg.values(), key=lambda r: (r['h_cm'], -r['b_cm']))


def export_kennung(p):
    wid = ''.join(ch for ch in str(p.get('wall_id', '')) if ch.isalnum())[-10:]
    return wid or datetime.datetime.now().strftime('%H%M%S%f')


def csv_export(elements, p):
    """Schreibt Summen- und Einzelliste als CSV-Dateien (Semikolon, Komma
    als Dezimaltrennzeichen - direkt in Excel zu oeffnen).
    Rueckgabe: Liste der geschriebenen Pfade.
    """
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')
    kennung = export_kennung(p)
    ordner = doc_dir()
    stem = doc_stem()
    pfade = []

    def zahl(v):
        return ('%.1f' % v).replace('.', ',')

    try:
        f = os.path.join(ordner, '%s_PD-MW_Summenliste_%s_%s.csv'
                         % (stem, kennung, stamp))
        with open(f, 'w', encoding='utf-8-sig') as fp:
            fp.write('Typ;Hoehe [cm];Breite [cm];Anzahl;Laenge [m];'
                     'Fundament Aufsichtsflaeche [m2];Fundament Volumen [m3];'
                     'Erdaushub bis UK Gelaende [m3]\n')
            tn, tl, tfa, tfv, tau = 0, 0.0, 0.0, 0.0, 0.0
            for r in summarize(elements, p):
                fp.write('%s;%s;%s;%d;%s;%s;%s;%s\n' % (
                    r['typ'], zahl(r['h_cm']), zahl(r['b_cm']), r['anzahl'],
                    ('%.2f' % r['laenge_m']).replace('.', ','),
                    ('%.2f' % r['fund_aufsicht_m2']).replace('.', ','),
                    ('%.2f' % r['fund_volumen_m3']).replace('.', ','),
                    ('%.2f' % r['aushub_m3']).replace('.', ',')))
                tn += r['anzahl']
                tl += r['laenge_m']
                tfa += r['fund_aufsicht_m2']
                tfv += r['fund_volumen_m3']
                tau += r['aushub_m3']
            fp.write('SUMME;;;%d;%s;%s;%s;%s\n' % (
                tn, ('%.2f' % tl).replace('.', ','),
                ('%.2f' % tfa).replace('.', ','),
                ('%.2f' % tfv).replace('.', ','),
                ('%.2f' % tau).replace('.', ',')))
        pfade.append(f)
    except Exception:
        pass

    if p.get('einzelliste'):
        try:
            f = os.path.join(ordner, '%s_PD-MW_Einzelliste_%s_%s.csv'
                             % (stem, kennung, stamp))
            with open(f, 'w', encoding='utf-8-sig') as fp:
                fp.write('Nr;Typ;Breite [cm];Hoehe links [cm];'
                         'Hoehe rechts [cm];Bestellhoehe [cm];'
                         'Fundament Aufsichtsflaeche [m2]\n')
                for r in element_rows(elements, p):
                    fp.write('%s;%s;%s;%s;%s;%s;%s\n'
                             % (r['nr'], r['typ'], str(r['breite']).replace('.', ','),
                                zahl(r['h_links_cm']), zahl(r['h_rechts_cm']),
                                zahl(r['bestell_cm']),
                                ('%.2f' % r['fund_aufsicht_m2']).replace('.', ',')))
            pfade.append(f)
        except Exception:
            pass
    return pfade


def ws_text(ws, zeile, spalte, wert):
    """Textwert in eine Arbeitsblattzelle schreiben."""
    vs.SetWSCellFormula(ws, zeile, spalte, zeile, spalte, str(wert))


def ws_zahl(ws, zeile, spalte, wert):
    """Echten Zahlenwert statt eines formatierten Textes schreiben."""
    vs.SetWSCellFormula(ws, zeile, spalte, zeile, spalte,
                        '=%.12g' % float(wert))


def worksheet_formatieren(ws, letzte_zeile, spaltenbreiten,
                           zahlenformate=None):
    """Arbeitsblatt lesbar und unabhaengig von Dokumentstilen formatieren.

    zahlenformate ist ein Dictionary {Spalte: Dezimalstellen}. Alle Aufrufe
    sind einzeln abgesichert, damit eine aeltere Vectorworks-Version nicht
    die Erzeugung des gesamten Arbeitsblatts verhindert.
    """
    n_spalten = len(spaltenbreiten)
    try:
        font_id = vs.GetFontID(TEXT_FONT)
        vs.SetWSCellTextFormat(ws, 1, 1, letzte_zeile, n_spalten,
                               font_id, int(TEXT_DEFAULT_SIZE), 0)
        vs.SetWSCellTextFormat(ws, 1, 1, 1, n_spalten,
                               font_id, int(TEXT_DEFAULT_SIZE), 1)
    except Exception:
        pass
    try:
        schwarz = vs.RGBToColorIndex(0, 0, 0)
    except Exception:
        schwarz = 0
    try:
        vs.SetWSCellTextColor(ws, 1, 1, letzte_zeile, n_spalten, schwarz)
    except Exception:
        pass
    for nr, breite in enumerate(spaltenbreiten, 1):
        try:
            vs.SetWSColumnWidth(ws, nr, nr, int(breite))
        except Exception:
            pass
    try:
        vs.SetWSRowHeight(ws, 1, 1, 32, False, False)
        vs.SetWSCellWrapTextFlag(ws, 1, 1, 1, n_spalten, True)
    except Exception:
        pass
    for spalte, stellen in (zahlenformate or {}).items():
        if letzte_zeile < 2:
            continue
        try:
            vs.SetWSCellNumberFormat(ws, 2, spalte, letzte_zeile, spalte,
                                     1, int(stellen), '', '')
            vs.SetWSCellAlignment(ws, 2, spalte, letzte_zeile, spalte, 3)
        except Exception:
            pass
    try:
        vs.RecalculateWS(ws)
    except Exception:
        pass


def create_element_worksheet(elements, p):
    """Arbeitsblatt mit jedem einzelnen Mauerwinkel."""
    rows = element_rows(elements, p)
    name = 'PD-MW Einzelliste %s %s' % (
        export_kennung(p), datetime.datetime.now().strftime('%H%M%S%f'))
    try:
        ws = vs.CreateWS(name, len(rows) + 3, 7)
        if not handle_valid(ws):
            return None
        head = ['Nr', 'Typ', 'Breite [cm]', 'Hoehe links [cm]',
                'Hoehe rechts [cm]', 'Bestellhoehe [cm]',
                'Fundament Aufsichtsflaeche [m2]']
        for c, t in enumerate(head):
            ws_text(ws, 1, c + 1, t)
        r = 2
        for x in rows:
            ws_text(ws, r, 1, x['nr'])
            ws_text(ws, r, 2, x['typ'])
            ws_text(ws, r, 3, x['breite'])
            ws_zahl(ws, r, 4, x['h_links_cm'])
            ws_zahl(ws, r, 5, x['h_rechts_cm'])
            ws_zahl(ws, r, 6, x['bestell_cm'])
            ws_zahl(ws, r, 7, x['fund_aufsicht_m2'])
            r += 1
        worksheet_formatieren(ws, max(1, r - 1),
                               [55, 145, 95, 120, 125, 130, 220],
                               {4: 1, 5: 1, 6: 1, 7: 2})
        try:
            vs.ShowWS(ws, True)
        except Exception:
            pass
        return ws
    except Exception:
        return None


def create_worksheet(elements, p):
    rows = summarize(elements, p)
    name = 'PD-MW Summenliste %s %s' % (
        export_kennung(p), datetime.datetime.now().strftime('%H%M%S%f'))
    try:
        ws = vs.CreateWS(name, len(rows) + 4, 8)
        if not handle_valid(ws):
            return None
        head = ['Typ', 'Hoehe [cm]', 'Breite [cm]', 'Anzahl', 'Laenge [m]',
                'Fundament Aufsichtsflaeche [m2]', 'Fundament Volumen [m3]',
                'Erdaushub bis UK Gelaende [m3]']
        for c, t in enumerate(head):
            ws_text(ws, 1, c + 1, t)
        r = 2
        tn, tl, tfa, tfv, tau = 0, 0.0, 0.0, 0.0, 0.0
        for x in rows:
            ws_text(ws, r, 1, x['typ'])
            for c, wert in enumerate(
                    [x['h_cm'], x['b_cm'], x['anzahl'], x['laenge_m'],
                     x['fund_aufsicht_m2'], x['fund_volumen_m3'],
                     x['aushub_m3']], 2):
                ws_zahl(ws, r, c, wert)
            tn += x['anzahl']
            tl += x['laenge_m']
            tfa += x['fund_aufsicht_m2']
            tfv += x['fund_volumen_m3']
            tau += x['aushub_m3']
            r += 1
        sum_zeile = r + 1
        ws_text(ws, sum_zeile, 1, 'SUMME')
        for c, wert in ((4, tn), (5, tl), (6, tfa), (7, tfv), (8, tau)):
            ws_zahl(ws, sum_zeile, c, wert)
        worksheet_formatieren(
            ws, sum_zeile, [180, 90, 95, 75, 90, 230, 190, 220],
            {2: 1, 3: 1, 4: 0, 5: 2, 6: 2, 7: 2, 8: 2})
        try:
            vs.ShowWS(ws, True)
        except Exception:
            pass
        return ws
    except Exception:
        return None


def group_objects(objs):
    """Erzeugte Objekte nachtraeglich zu einer Gruppe zusammenfassen."""
    if not objs:
        return None
    try:
        vs.DSelectAll()
        n = 0
        for h in objs:
            try:
                vs.SetSelect(h)
                n += 1
            except Exception:
                pass
        if n == 0:
            return None
        vs.Group()
        g = vs.FSActLayer()
        vs.DSelectAll()
        return g if handle_valid(g) else None
    except Exception:
        return None


def ensure_record():
    try:
        if get_object(REC_NAME) is None:
            vs.NewField(REC_NAME, REC_FIELD, '', 4, 0)
    except Exception:
        try:
            vs.NewField(REC_NAME, REC_FIELD, '', 4, 0)
        except Exception:
            pass


def attach_data(h, data):
    ensure_record()
    try:
        vs.SetRecord(h, REC_NAME)
        vs.SetRField(h, REC_NAME, REC_FIELD, json.dumps(data, ensure_ascii=True))
    except Exception:
        pass


def read_data(h):
    try:
        s = vs.GetRField(h, REC_NAME, REC_FIELD)
        if s:
            return migrate_data(json.loads(s))
    except Exception:
        pass
    return None


LAST_BUILD = {}


def new_wall_id(kuerzel):
    return '%s-%s' % (kuerzel, uuid.uuid4().hex)


def delete_objects(handles):
    """Best-effort-Loeschung einer exakt vorgegebenen Handleliste."""
    for h in handles or []:
        if h is None:
            continue
        try:
            vs.DelObject(h)
        except Exception:
            pass


GEHRUNG_GRENZE = 2.5      # laenger als 2,5 x Tiefe -> abschraegen


def gehrung(pc, n1, n2, tiefe, grenze=GEHRUNG_GRENZE):
    """Schnittpunkt der beiden Versatzlinien an einer Ecke (Gehrung).
    Bei sehr spitzen Ecken wuerde die Spitze weit hinausschiessen - dann
    wird None geliefert und der Aufrufer schraegt ab."""
    mx, my = n1[0] + n2[0], n1[1] + n2[1]
    L = math.hypot(mx, my)
    if L < 1e-9:
        return None
    mx, my = mx / L, my / L
    cosphi = mx * n1[0] + my * n1[1]
    if abs(cosphi) < 1e-6:
        return None
    laenge = tiefe / cosphi
    if grenze and abs(laenge) > abs(tiefe) * grenze:
        return None
    return (pc[0] + mx * laenge, pc[1] + my * laenge)


def eck_polygone(pa, pc, pb, sign, dicke, fuss):
    """Mauerkoerper und Fuss eines Eckelements als je EIN gemitertes Polygon -
    dadurch ueberlagern sich die Fuesse der beiden Schenkel nicht."""
    def einheit(q1, q2):
        dx, dy = q2[0] - q1[0], q2[1] - q1[1]
        L = math.hypot(dx, dy)
        return (dx / L, dy / L) if L > 1e-12 else None

    u1 = einheit(pa, pc)
    u2 = einheit(pc, pb)
    if u1 is None or u2 is None:
        return None, None

    # Nur INNENWINKEL als Sonderelement: dort liegen Mauerkoerper und Fuss
    # auf der Innenseite der Ecke und wuerden sich ueberlagern.
    kreuz = u1[0] * u2[1] - u1[1] * u2[0]
    if kreuz * sign <= 1e-12:
        return None, None

    n1 = (-u1[1] * sign, u1[0] * sign)
    n2 = (-u2[1] * sign, u2[0] * sign)

    def band(tiefe):
        if tiefe <= 0:
            return None
        pm = gehrung(pc, n1, n2, tiefe)
        if pm is None:
            pm = (pc[0] + n1[0] * tiefe, pc[1] + n1[1] * tiefe)
        return [(pa[0], pa[1]), (pc[0], pc[1]), (pb[0], pb[1]),
                (pb[0] + n2[0] * tiefe, pb[1] + n2[1] * tiefe),
                pm,
                (pa[0] + n1[0] * tiefe, pa[1] + n1[1] * tiefe)]

    return band(dicke), band(fuss)


def geteilte_eckkoerper(pa, pc, pb, sign, dicke):
    """Koerper zweier Regelelemente am Knick.

    An Innenecken der Mauervorderseite bleiben beide Koerper vollstaendige
    Rechtecke; sie sind keine zugeschnittenen Sonderelemente. Die zugehoerige
    Fussseite ist rechnerisch die Aussenseite des Linienknicks.
    """
    def richtung(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        laenge = math.hypot(dx, dy)
        return ((dx / laenge, dy / laenge)
                if laenge > 1e-12 else None)

    u1 = richtung(pa, pc)
    u2 = richtung(pc, pb)
    if u1 is None or u2 is None:
        return None, None
    n1 = (-u1[1] * sign, u1[0] * sign)
    n2 = (-u2[1] * sign, u2[0] * sign)
    aussen_a = (pa[0] + n1[0] * dicke, pa[1] + n1[1] * dicke)
    aussen_b = (pb[0] + n2[0] * dicke, pb[1] + n2[1] * dicke)
    knick_a = (pc[0] + n1[0] * dicke, pc[1] + n1[1] * dicke)
    knick_b = (pc[0] + n2[0] * dicke, pc[1] + n2[1] * dicke)
    kreuz = u1[0] * u2[1] - u1[1] * u2[0]
    if kreuz * sign < -1e-12:
        return ([pa, pc, knick_a, aussen_a],
                [pc, pb, aussen_b, knick_b])
    mitte = gehrung(pc, n1, n2, dicke)
    if mitte is None:
        mitte = ((knick_a[0] + knick_b[0]) / 2.0,
                 (knick_a[1] + knick_b[1]) / 2.0)
    return ([pa, pc, mitte, aussen_a],
            [pc, pb, aussen_b, mitte])


def teilstueck(pl_pts, st_tab, s_a, s_b):
    """Punkte der Aufsichtslinie zwischen zwei Stationen, mit Knickpunkten."""
    pts = [point_at_station(pl_pts, st_tab, s_a)[0]]
    for i, st in enumerate(st_tab):
        if s_a + 1e-9 < st < s_b - 1e-9:
            pts.append((pl_pts[i][0], pl_pts[i][1]))
    pts.append(point_at_station(pl_pts, st_tab, s_b)[0])
    saubere = [pts[0]]
    for q in pts[1:]:
        if math.hypot(q[0] - saubere[-1][0], q[1] - saubere[-1][1]) > 1e-9:
            saubere.append(q)
    return saubere


def _versatz_schnittpunkt(pc, u1, u2, d1, d2, sign):
    """Schnittpunkt zweier verschieden weit versetzter Geraden."""
    n1 = (-u1[1] * sign, u1[0] * sign)
    n2 = (-u2[1] * sign, u2[0] * sign)
    a = (pc[0] + n1[0] * d1, pc[1] + n1[1] * d1)
    b = (pc[0] + n2[0] * d2, pc[1] + n2[1] * d2)
    nenner = u1[0] * u2[1] - u1[1] * u2[0]
    if abs(nenner) < 1e-9:
        return None
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = (dx * u2[1] - dy * u2[0]) / nenner
    return (a[0] + u1[0] * t, a[1] + u1[1] * t)


def band_primitiven(pl_pts, st_tab, abschnitte, vorne, sign):
    """Einfache Teilflaechen eines Bandes mit variabler rueckseitiger Tiefe.

    ``abschnitte`` enthaelt Planstation Anfang/Ende, Tiefe und Besitzerindex.
    Die Segmentrechtecke ueberlappen sich an Innenecken. An der jeweiligen
    Aussenseite wird der Gehrungskeil ergaenzt. Erst Vectorworks vereinigt die
    Flaechen; kein Einzelpolygon kann sich dabei selbst schneiden.
    """
    intervalle = []
    for eintrag in abschnitte:
        if len(eintrag) < 3:
            continue
        s0, s1, tiefe = float(eintrag[0]), float(eintrag[1]), float(eintrag[2])
        besitzer = eintrag[3] if len(eintrag) > 3 else None
        a, b = min(s0, s1), max(s0, s1)
        if b - a > 1e-9:
            intervalle.append((a, b, max(0.0, tiefe), besitzer))
    if not intervalle or len(pl_pts) < 2:
        return []

    polygone = []
    for s0, s1, hinten, besitzer in intervalle:
        pts = teilstueck(pl_pts, st_tab, s0, s1)
        for q0, q1 in zip(pts, pts[1:]):
            dx, dy = q1[0] - q0[0], q1[1] - q0[1]
            laenge = math.hypot(dx, dy)
            if laenge <= 1e-12:
                continue
            ux, uy = dx / laenge, dy / laenge
            nx, ny = -uy * sign, ux * sign
            polygone.append({
                'punkte': [
                    (q0[0] - nx * vorne, q0[1] - ny * vorne),
                    (q1[0] - nx * vorne, q1[1] - ny * vorne),
                    (q1[0] + nx * hinten, q1[1] + ny * hinten),
                    (q0[0] + nx * hinten, q0[1] + ny * hinten)],
                'linie': (q0, q1), 'besitzer': besitzer, 'art': 'segment'})

    def abschnitt_neben(station, richtung, schritt):
        probe = station + richtung * schritt
        treffer = [(t, nr) for a, b, t, nr in intervalle
                   if a - 1e-9 <= probe <= b + 1e-9]
        return max(treffer, key=lambda q: q[0]) if treffer else (None, None)

    for i in range(1, len(pl_pts) - 1):
        pc = pl_pts[i]
        l1 = math.hypot(pc[0] - pl_pts[i - 1][0],
                        pc[1] - pl_pts[i - 1][1])
        l2 = math.hypot(pl_pts[i + 1][0] - pc[0],
                        pl_pts[i + 1][1] - pc[1])
        if l1 <= 1e-12 or l2 <= 1e-12:
            continue
        st = st_tab[i]
        schritt = max(1e-8, min(l1, l2) * 1e-6)
        hinten1, besitzer1 = abschnitt_neben(st, -1.0, schritt)
        hinten2, besitzer2 = abschnitt_neben(st, 1.0, schritt)
        if hinten1 is None or hinten2 is None:
            continue
        u1 = ((pc[0] - pl_pts[i - 1][0]) / l1,
              (pc[1] - pl_pts[i - 1][1]) / l1)
        u2 = ((pl_pts[i + 1][0] - pc[0]) / l2,
              (pl_pts[i + 1][1] - pc[1]) / l2)
        drehung = u1[0] * u2[1] - u1[1] * u2[0]
        seiten_drehung = drehung * sign
        if seiten_drehung < -1e-9:
            aussen_sign, d1, d2 = sign, hinten1, hinten2
        elif seiten_drehung > 1e-9 and vorne > 1e-12:
            aussen_sign, d1, d2 = -sign, vorne, vorne
        else:
            continue
        n1 = (-u1[1] * aussen_sign, u1[0] * aussen_sign)
        n2 = (-u2[1] * aussen_sign, u2[0] * aussen_sign)
        o1 = (pc[0] + n1[0] * d1, pc[1] + n1[1] * d1)
        o2 = (pc[0] + n2[0] * d2, pc[1] + n2[1] * d2)
        m = _versatz_schnittpunkt(pc, u1, u2, d1, d2, aussen_sign)
        if m is not None:
            radial = math.hypot(m[0] - pc[0], m[1] - pc[1])
            if radial > max(d1, d2, 1e-12) * GEHRUNG_GRENZE:
                m = None
        if m is not None:
            seite_pc = ((o2[0] - o1[0]) * (pc[1] - o1[1]) -
                        (o2[1] - o1[1]) * (pc[0] - o1[0]))
            seite_m = ((o2[0] - o1[0]) * (m[1] - o1[1]) -
                       (o2[1] - o1[1]) * (m[0] - o1[0]))
            if seite_pc * seite_m >= -1e-12:
                m = None
        eps = min(min(l1, l2) * 0.01,
                  max(min(l1, l2) * 1e-7, U.cm(0.01)))

        o1_innen = (o1[0] - u1[0] * eps, o1[1] - u1[1] * eps)
        o2_innen = (o2[0] + u2[0] * eps, o2[1] + u2[1] * eps)
        mengen_punkte = ([pc, o1, m, o2] if m is not None else
                         [pc, o1, o2])
        punkte = ([pc, o1_innen, m, o2_innen] if m is not None else
                  [pc, o1_innen, o2_innen])
        polygone.append({'punkte': punkte,
                         'mengen_punkte': mengen_punkte,
                         'besitzer': (besitzer1, besitzer2),
                         'art': 'aussengehrung'})
    return polygone


def winkel_fuss_primitiven(pl_pts, st_tab, abschnitte, sign):
    """Vollstaendige Regelsteinfuesse ohne kuenstlichen Inneneckkeil.

    ``band_primitiven`` schliesst auf der geometrischen Aussenseite eines
    Knicks die Luecke mit einem Gehrungskeil. Bei Winkelsteinen ist diese
    Situation die Innenecke der Mauervorderseite: Dort stehen zwei normale
    Rechteckfuesse auf einem gemeinsamen Fundament, kein Sonderelement.
    """
    return [eintrag for eintrag in
            band_primitiven(pl_pts, st_tab, abschnitte, 0.0, sign)
            if eintrag.get('art') != 'aussengehrung']


def _polygon_flaeche(punkte):
    if len(punkte) < 3:
        return 0.0
    return abs(sum(
        punkte[i][0] * punkte[(i + 1) % len(punkte)][1] -
        punkte[(i + 1) % len(punkte)][0] * punkte[i][1]
        for i in range(len(punkte))) / 2.0)


def _konvexer_schnitt(subject, clip):
    """Sutherland-Hodgman-Schnitt zweier konvexer Polygone."""
    if len(subject) < 3 or len(clip) < 3:
        return []
    orient = 1.0 if sum(
        clip[i][0] * clip[(i + 1) % len(clip)][1] -
        clip[(i + 1) % len(clip)][0] * clip[i][1]
        for i in range(len(clip))) >= 0 else -1.0

    def innen(punkt, a, b):
        return orient * ((b[0] - a[0]) * (punkt[1] - a[1]) -
                         (b[1] - a[1]) * (punkt[0] - a[0])) >= -1e-10

    def schnitt(p1, p2, a, b):
        rx, ry = p2[0] - p1[0], p2[1] - p1[1]
        sx, sy = b[0] - a[0], b[1] - a[1]
        nenner = rx * sy - ry * sx
        if abs(nenner) < 1e-12:
            return p2
        t = ((a[0] - p1[0]) * sy - (a[1] - p1[1]) * sx) / nenner
        return p1[0] + t * rx, p1[1] + t * ry

    ausgabe = list(subject)
    for i, a in enumerate(clip):
        b = clip[(i + 1) % len(clip)]
        eingabe, ausgabe = ausgabe, []
        if not eingabe:
            break
        vorher = eingabe[-1]
        for aktuell in eingabe:
            if innen(aktuell, a, b):
                if not innen(vorher, a, b):
                    ausgabe.append(schnitt(vorher, aktuell, a, b))
                ausgabe.append(aktuell)
            elif innen(vorher, a, b):
                ausgabe.append(schnitt(vorher, aktuell, a, b))
            vorher = aktuell
    return ausgabe


def band_flaechen_je_besitzer(polygone):
    """Exakte Vereinigungsflaeche lokal auf die Elemente verteilen.

    Tiefe Eckfuesse koennen mehrere, nicht unmittelbar benachbarte Rechtecke
    ueberdecken. Eine reine Paarrechnung wuerde bei Dreifachueberdeckungen
    zudem Bereiche mehrfach abziehen. Deshalb wird die gesamte Anordnung an
    allen Eck- und Schnitt-x-Werten in Streifen zerlegt. Innerhalb eines
    Streifens sind alle Polygonkanten linear und die vereinigte Flaeche ist
    mit der Trapezregel exakt. Flaechig beteiligte Besitzer teilen sich einen
    Ueberdeckungsbereich gleichmaessig.
    """
    eintraege = []
    for p in polygone:
        punkte = list(p.get('mengen_punkte', p.get('punkte', [])))
        if len(punkte) < 3:
            continue
        besitzer = p.get('besitzer')
        if isinstance(besitzer, (tuple, list, set)):
            nummern = set(nr for nr in besitzer if nr is not None)
        elif besitzer is None:
            nummern = set()
        else:
            nummern = {besitzer}
        eintraege.append({'punkte': punkte, 'besitzer': nummern})
    if not eintraege:
        return {}

    alle_werte = [wert for e in eintraege for q in e['punkte'] for wert in q]
    mass = max([1.0] + [abs(float(wert)) for wert in alle_werte])
    tol = max(1e-10, mass * 1e-12)

    def kanten(punkte):
        return list(zip(punkte, punkte[1:] + punkte[:1]))

    def schnitt_x(a, b, c, d):
        rx, ry = b[0] - a[0], b[1] - a[1]
        sx, sy = d[0] - c[0], d[1] - c[1]
        nenner = rx * sy - ry * sx
        if abs(nenner) <= tol:
            return None
        qx, qy = c[0] - a[0], c[1] - a[1]
        t = (qx * sy - qy * sx) / nenner
        u = (qx * ry - qy * rx) / nenner
        if -tol <= t <= 1.0 + tol and -tol <= u <= 1.0 + tol:
            return a[0] + t * rx
        return None

    # Neben allen Polygonknoten sind auch Kantenkreuzungen Ereignisse, weil
    # sich dort die vertikale Reihenfolge der Flaechenbegrenzungen aendert.
    x_werte = [q[0] for e in eintraege for q in e['punkte']]
    for i, e1 in enumerate(eintraege):
        minx1 = min(q[0] for q in e1['punkte'])
        maxx1 = max(q[0] for q in e1['punkte'])
        miny1 = min(q[1] for q in e1['punkte'])
        maxy1 = max(q[1] for q in e1['punkte'])
        for e2 in eintraege[i + 1:]:
            minx2 = min(q[0] for q in e2['punkte'])
            maxx2 = max(q[0] for q in e2['punkte'])
            miny2 = min(q[1] for q in e2['punkte'])
            maxy2 = max(q[1] for q in e2['punkte'])
            if (maxx1 < minx2 - tol or maxx2 < minx1 - tol or
                    maxy1 < miny2 - tol or maxy2 < miny1 - tol):
                continue
            for a, b in kanten(e1['punkte']):
                for c, d in kanten(e2['punkte']):
                    wert = schnitt_x(a, b, c, d)
                    if wert is not None:
                        x_werte.append(wert)
    x_werte.sort()
    xs = []
    for wert in x_werte:
        if not xs or abs(wert - xs[-1]) > tol:
            xs.append(wert)

    def vertikal_intervall(eintrag, x):
        treffer = []
        for a, b in kanten(eintrag['punkte']):
            dx = b[0] - a[0]
            if abs(dx) <= tol:
                continue
            if x < min(a[0], b[0]) - tol or x > max(a[0], b[0]) + tol:
                continue
            m = (b[1] - a[1]) / dx
            n = a[1] - m * a[0]
            treffer.append((m * x + n, m, n))
        if len(treffer) < 2:
            return None
        treffer.sort(key=lambda q: q[0])
        return treffer[0], treffer[-1]

    flaechen = {}
    for x0, x1 in zip(xs, xs[1:]):
        dx = x1 - x0
        if dx <= tol:
            continue
        xm = (x0 + x1) / 2.0
        aktiv = []
        grenzen = []
        for e in eintraege:
            intervall = vertikal_intervall(e, xm)
            if intervall is None:
                continue
            unten, oben = intervall
            if oben[0] - unten[0] <= tol:
                continue
            aktiv.append((unten, oben, e['besitzer']))
            grenzen.extend((unten, oben))
        grenzen.sort(key=lambda q: q[0])
        eindeutig = []
        for grenze in grenzen:
            if not eindeutig or abs(grenze[0] - eindeutig[-1][0]) > tol:
                eindeutig.append(grenze)
        for unten, oben in zip(eindeutig, eindeutig[1:]):
            if oben[0] - unten[0] <= tol:
                continue
            ym = (unten[0] + oben[0]) / 2.0
            nummern = set()
            for tief, hoch, besitzer in aktiv:
                if tief[0] - tol <= ym <= hoch[0] + tol:
                    nummern.update(besitzer)
            if not nummern:
                continue
            h0 = (oben[1] * x0 + oben[2]) - (unten[1] * x0 + unten[2])
            h1 = (oben[1] * x1 + oben[2]) - (unten[1] * x1 + unten[2])
            teil = max(0.0, (h0 + h1) * dx / 2.0)
            anteil = teil / float(len(nummern))
            for nr in nummern:
                flaechen[nr] = flaechen.get(nr, 0.0) + anteil
    return flaechen


def setze_winkel_eckmengen(elements, pl_pts, st_tab, p, reverse=False):
    """Fundament-Aufsicht und Folgemengen je Element um Ecken korrigieren.

    Die Rechnung verwendet dieselben Rechtecke, Innenueberdeckungen und
    Aussengehrungen wie die Aufsicht, ist aber nicht von AddSurface oder vom
    eingeschalteten Zeichnen der Aufsicht abhaengig.
    """
    for e in elements:
        e.pop('_fund_eck_faktor', None)
    if not elements or len(pl_pts or []) < 2 or len(st_tab or []) < 2:
        return 0.0
    total = st_tab[-1]

    def station(sw):
        return total - sw if reverse else sw

    fundamente = winkel_fundamente(elements, p)
    abschnitte = [
        (station(fund['s0']), station(fund['s1']),
         U.cm(fund['fuss_cm'] + fund['ueberstand_cm']), nr)
        for nr, fund in enumerate(fundamente)]
    vorne = U.cm(max(
        (float(fund['ueberstand_cm']) for fund in fundamente), default=0.0))
    sign = 1.0 if p.get('seite', 0) == 0 else -1.0
    polygone = band_primitiven(pl_pts, st_tab, abschnitte, vorne, sign)
    je_element = band_flaechen_je_besitzer(polygone)
    gesamt = 0.0
    for nr, (e, fund) in enumerate(zip(elements, fundamente)):
        nenn = float(fund.get('aufsicht_m2', 0.0))
        ist = je_element.get(nr)
        if ist is None or nenn <= 1e-12:
            gesamt += nenn
            continue
        ist_m2 = ist / (U.factor * U.factor)
        e['_fund_eck_faktor'] = max(0.0, ist_m2 / nenn)
        gesamt += ist_m2
    return gesamt


def gab_fundament_primitiven(zellen, pl_pts, st_tab, p, reverse=False):
    """Primitive der allseitig ueberstehenden Gabionenfundament-Aufsicht."""
    fundamente = gab_fundamente(zellen, p)
    if not fundamente or len(pl_pts or []) < 2 or len(st_tab or []) < 2:
        return [], [], [], []
    total = st_tab[-1]
    ueber = U.cm(gab_fund_ueberstand_cm(p))
    def station(sw):
        return total - sw if reverse else sw

    # OK/UK duerfen kuerzer als die gewaehlte Aufsichtslinie sein. Der
    # allseitige Ueberstand gehoert dann an die tatsaechlich belegten
    # Mauerenden und nicht an die Enden der laengeren Bezugslinie.
    gemappt = [station(wert) for fund in fundamente
               for wert in (fund['s0'], fund['s1'])]
    plan_s0, plan_s1 = min(gemappt), max(gemappt)
    plan_belegt = teilstueck(pl_pts, st_tab, plan_s0, plan_s1)
    plan_erweitert = verlaengere_linie(plan_belegt, ueber, ueber)
    stationen_erweitert = station_table(plan_erweitert)
    belegte_laenge = plan_s1 - plan_s0

    abschnitte = []
    for nr, fund in enumerate(fundamente):
        a = station(fund['s0']) - plan_s0 + ueber
        b = station(fund['s1']) - plan_s0 + ueber
        s0, s1 = min(a, b), max(a, b)
        if s0 <= ueber + 1e-8:
            s0 = 0.0
        if s1 >= belegte_laenge + ueber - 1e-8:
            s1 = stationen_erweitert[-1]
        abschnitte.append((
            s0, s1, U.cm(fund['gab_b_cm'] + fund['ueberstand_cm']), nr))
    sign = 1.0 if p.get('seite', 0) == 0 else -1.0
    polygone = band_primitiven(
        plan_erweitert, stationen_erweitert, abschnitte, ueber, sign)
    return fundamente, plan_erweitert, stationen_erweitert, polygone


def setze_gabionen_eckmengen(zellen, pl_pts, st_tab, p, reverse=False):
    """Gabionen-Fundamentmengen an Ecken mit der Aufsicht vereinigen."""
    for z in zellen:
        z.pop('_gab_fund_eck_faktor', None)
    fundamente, _plan, _stationen, polygone = gab_fundament_primitiven(
        zellen, pl_pts, st_tab, p, reverse)
    if not fundamente:
        return 0.0
    je_fundament = band_flaechen_je_besitzer(polygone)
    saeulen = gab_saeulen(zellen)
    schluessel = sorted(saeulen)
    gesamt = 0.0
    for nr, (fund, sch) in enumerate(zip(fundamente, schluessel)):
        nenn = float(fund.get('flaeche_m2', 0.0))
        ist = je_fundament.get(nr)
        if ist is None or nenn <= 1e-12:
            gesamt += nenn
            continue
        ist_m2 = ist / (U.factor * U.factor)
        saeulen[sch][-1]['_gab_fund_eck_faktor'] = max(0.0, ist_m2 / nenn)
        gesamt += ist_m2
    return gesamt


def _surface_union_handles(polygone):
    """Nicht registrierte Flaechenprimitive erzeugen und vereinigen."""
    flaechenteile = []
    for eintrag in polygone:
        punkte = eintrag.get('punkte', eintrag)
        if len(punkte) < 3:
            continue
        vs.ClosePoly()
        vs.Poly(*[c for q in punkte for c in q])
        h = vs.LNewObj()
        if handle_valid(h) and get_type(h) > 0:
            flaechenteile.append(h)

    vereinigt = []
    for h in flaechenteile:
        aktuell = h
        nochmal = True
        while nochmal:
            nochmal = False
            for nr, vorhanden in enumerate(vereinigt):
                try:
                    neu = vs.AddSurface(vorhanden, aktuell)
                except Exception:
                    neu = None
                if (handle_valid(neu) and get_type(neu) > 0 and
                        neu != aktuell and neu != vorhanden):
                    vereinigt.pop(nr)
                    aktuell = neu
                    nochmal = True
                    break
        vereinigt.append(aktuell)
    return vereinigt


def _finalisiere_surface_handles(handles, cls, rgb, solid, opacity_pct,
                                 line_style=''):
    """Flaechenhandles formatieren, registrieren und Flaeche summieren."""
    flaeche = 0.0
    for h in handles:
        _reg(h)
        force_attrs(h, cls, rgb, solid)
        set_obj_opacity(h, opacity_pct)
        try:
            if line_style:
                linientyp = int(vs.Name2Index(line_style))
                vs.SetLSN(h, -linientyp if linientyp > 0 else 4)
            else:
                vs.SetLSN(h, 2)
        except Exception:
            pass
        try:
            flaeche += abs(float(vs.HAreaN(h)))
        except Exception:
            pass
    return handles, flaeche


def draw_surface_union(polygone, cls, rgb, solid, opacity_pct,
                       line_style=''):
    """Teilpolygone zeichnen und ueber AddSurface soweit moeglich vereinigen."""
    handles = _surface_union_handles(polygone)
    return _finalisiere_surface_handles(
        handles, cls, rgb, solid, opacity_pct, line_style)


def draw_ring_surface(pl_pts, st_tab, s0, s1, innen, aussen, sign,
                      cls, rgb, opacity_pct):
    """Disjunktes Gabionen-Farbband als Aussenflaeche minus Innenflaeche.

    ClipSurfaceN belaesst laut Vectorworks-API beide Operanden und liefert
    die neue Differenzflaeche. Dadurch bleiben auch transparente Farbringe an
    Innen- und Aussenecken frei von Ueberlagerungen.
    """
    abschnitt = [(min(s0, s1), max(s0, s1), aussen, None)]
    aussen_polygone = band_primitiven(pl_pts, st_tab, abschnitt, 0.0, sign)
    aussen_handles = _surface_union_handles(aussen_polygone)
    if innen <= 1e-12:
        return _finalisiere_surface_handles(
            aussen_handles, cls, rgb, True, opacity_pct)

    innen_abschnitt = [(min(s0, s1), max(s0, s1), innen, None)]
    innen_polygone = band_primitiven(
        pl_pts, st_tab, innen_abschnitt, 0.0, sign)
    innen_handles = _surface_union_handles(innen_polygone)
    ergebnis = []
    try:
        for h_aussen in aussen_handles:
            aktuell = h_aussen
            for h_innen in innen_handles:
                try:
                    neu = vs.ClipSurfaceN(aktuell, h_innen)
                except Exception:
                    neu = None
                if (handle_valid(neu) and get_type(neu) > 0 and
                        neu != aktuell and neu != h_innen):
                    delete_objects([aktuell])
                    aktuell = neu
            ergebnis.append(aktuell)
    finally:
        delete_objects(innen_handles)
    return _finalisiere_surface_handles(
        ergebnis, cls, rgb, True, opacity_pct)


def verlaengere_linie(pts, anfang=0.0, ende=0.0):
    """Offenen Linienzug tangential an Anfang und Ende verlaengern."""
    if len(pts) < 2:
        return list(pts)
    ausgabe = list(pts)
    if anfang > 1e-12:
        dx = pts[1][0] - pts[0][0]
        dy = pts[1][1] - pts[0][1]
        laenge = math.hypot(dx, dy)
        if laenge > 1e-12:
            ausgabe[0] = (pts[0][0] - dx / laenge * anfang,
                          pts[0][1] - dy / laenge * anfang)
    if ende > 1e-12:
        dx = pts[-1][0] - pts[-2][0]
        dy = pts[-1][1] - pts[-2][1]
        laenge = math.hypot(dx, dy)
        if laenge > 1e-12:
            ausgabe[-1] = (pts[-1][0] + dx / laenge * ende,
                           pts[-1][1] + dy / laenge * ende)
    return ausgabe


def gab_klassen(prefix, zellen, farb_modus, force, transparenz,
                colors_cfg=None, fundament_cfg=DEFAULT_FUNDAMENT_FARBE):
    """Je Gabionenbreite eine eigene, manuelle oder automatische Farbe."""
    colors_cfg = colors_cfg if isinstance(colors_cfg, dict) else {}
    breiten = sorted(set(int(round(z['b_cm'])) for z in zellen))
    standard = []
    for _tiefe, wert in GAB_BREITEN:
        wert = int(round(wert))
        if wert not in standard:
            standard.append(wert)
    sonder = [b for b in breiten if b not in standard]
    farbreihe = sorted(set(standard + breiten + [
        int(round(float(k))) for k in colors_cfg
        if str(k).replace('.', '', 1).isdigit()]))
    farben = {}
    for reihe, b in enumerate(breiten):
        idx = standard.index(b) if b in standard else len(standard) + sonder.index(b)
        if farb_modus:
            rgb = verlauf_farbe(farbreihe.index(b), len(farbreihe),
                                int(farb_modus))
        elif str(b) in colors_cfg:
            rgb = parse_color(colors_cfg.get(str(b)), b)
        elif idx < len(GAB_TYP_FARBEN):
            rgb8 = GAB_TYP_FARBEN[idx]
            rgb = tuple(kanal * 257 for kanal in rgb8)
        else:
            # Zusaetzliche freie Katalogbreiten erhalten weitere, gleichmaessig
            # verteilte Farbtone ohne eine Standardfarbe neu zu belegen.
            rgb = hsv_rgb((0.61803398875 * idx) % 1.0, 0.62, 0.88)
        cls = '%s%03d' % (prefix, b)
        ensure_class(cls, rgb, True, force)
        set_class_opacity(cls, max(0.0, 100.0 - transparenz))
        farben[b] = rgb
    ensure_class(prefix + 'FUNDAMENT', parse_color(fundament_cfg, 0.0),
                 True, True)
    set_class_opacity(prefix + 'FUNDAMENT',
                      max(0.0, 100.0 - transparenz))
    for zusatz in ('TXT', 'BEM', 'FUNDAMENT-BEM', 'KOTE', 'TABELLE',
                   'HILFE', 'UMRISS'):
        ensure_class(prefix + zusatz, (0, 0, 0), False, True)
    return farben


def gab_ansicht(zellen, p, farben, corners=None):
    """Ansicht (Abwicklung): Front der Wand, Lage fuer Lage."""
    prefix = p['gab_prefix']
    txt_cls = prefix + 'TXT'
    bem_cls = prefix + 'BEM'
    fund_bem_cls = prefix + 'FUNDAMENT-BEM'
    th = text_metrics(p)[0]
    deckkraft = max(0.0, 100.0 - p.get('transparenz', 0.0))

    # Fundament zuerst zeichnen, damit die farbigen Gabionen davor liegen.
    fundamente = gab_fundamente(zellen, p)
    for fund in fundamente:
        punkte = list(fund['basis_pts']) + list(reversed(fund['top_pts']))
        make_filled_poly(punkte, prefix + 'FUNDAMENT', fundament_rgb(p),
                         deckkraft)

    for z in zellen:
        b = int(round(z['b_cm']))
        cls = '%s%03d' % (prefix, b)
        rgb = farben.get(b, (52000, 52000, 52000))
        make_filled_poly([(z['x0'], z['ybot']), (z['x1'], z['ybot']),
                          (z['x1'], z['ytop']), (z['x0'], z['ytop'])],
                         cls, rgb, deckkraft)
        set_text_style(p['font'], p['font_size'])
        # Breite der Gabione - waagerecht, solange die Gabione breit genug ist
        label = 'B %g' % z['b_cm']
        if z.get('is_corner'):
            label = 'Ecke ' + label
        platz = z['width'] > len(label) * th * 0.62 * 1.15
        make_text(label, (z['x0'] + z['x1']) / 2.0,
                  (z['ybot'] + z['ytop']) / 2.0,
                  0.0 if platz else 90.0, 2, 2, txt_cls)
        if z['lage'] == 1:
            make_text(str(z['nr']), z['x0'] + th * 0.2, z['ytop'] - th * 0.2,
                      0, 1, 1, txt_cls)

    if p.get('bemassung'):
        # Lagenhoehe je Saeule links, Laenge unten - im Element, ohne Masslinien
        saeulen = {}
        for z in zellen:
            saeulen.setdefault((round(z['s0'], 6), round(z['s1'], 6)), []).append(z)
        for lagen in saeulen.values():
            lagen.sort(key=lambda q: -q['ytop'])
            unten = lagen[-1]
            make_text('-%s-' % fmt_cm(unten['width_cm']),
                      (unten['x0'] + unten['x1']) / 2.0,
                      unten['ybot'] + th * 0.55, 0, 2, 2, bem_cls)
            for z in lagen:
                make_text('-%s-' % fmt_cm(z['h_cm']),
                          z['x0'] + th * 0.45,
                          (z['ybot'] + z['ytop']) / 2.0, 90.0, 2, 2, bem_cls)
        x_a = min(z['x0'] for z in zellen)
        x_b = max(z['x1'] for z in zellen)
        y_fund = min(q[1] for f in fundamente for q in f['basis_pts'])
        d = dim_abstand_units(p)
        eck_stationen = sorted(set(
            max(0.0, min(float(c['s']), x_b - x_a)) for c in (corners or [])))
        grenzen = [0.0] + [s for s in eck_stationen
                            if 1e-9 < s < (x_b - x_a) - 1e-9] + [x_b - x_a]
        for sa, sb in zip(grenzen, grenzen[1:]):
            if sb - sa <= 1e-9:
                continue
            dim_between((x_a + sa, y_fund), (x_a + sb, y_fund), -d,
                        'L = %.2f m' % U.to_m(sb - sa), bem_cls, p)
        if len(grenzen) > 2:
            dim_between((x_a, y_fund), (x_b, y_fund), -d * 2.2,
                        'Gesamt L = %.2f m' % U.to_m(x_b - x_a),
                        bem_cls, p)
        draw_fundament_staerken(fundamente, p, fund_bem_cls)

    if p.get('ref_aktiv'):
        kote_cls = prefix + 'KOTE'
        set_text_style(p['font'], p['font_size'])
        saeulen = {}
        for z in zellen:
            saeulen.setdefault((round(z['s0'], 6), round(z['s1'], 6)), []).append(z)
        for lagen in saeulen.values():
            lagen.sort(key=lambda q: -q['ytop'])
            x = (lagen[0]['x0'] + lagen[0]['x1']) / 2.0
            make_text(kote_text(p, lagen[0]['ytop']), x,
                      lagen[0]['ytop'] + th * 0.2, 90.0, 1, 2, kote_cls)
            make_text(kote_text(p, lagen[-1]['ybot']), x,
                      lagen[-1]['ybot'] - th * 0.2, 90.0, 3, 2, kote_cls)


def gab_aufsicht(zellen, pl_pts, st_tab, p, farben, reverse, total):
    """Aufsicht mit farbigen Rueckspruengen aller Gabionenbreiten."""
    prefix = p['gab_prefix']
    txt_cls = prefix + 'TXT'
    bem_cls = prefix + 'BEM'
    kote_cls = prefix + 'KOTE'
    um_cls = prefix + 'UMRISS'
    th = text_metrics(p)[0]
    sign = 1.0 if p['seite'] == 0 else -1.0
    deckkraft = max(0.0, 100.0 - p.get('transparenz', 0.0))

    saeulen = {}
    for z in zellen:
        saeulen.setdefault((round(z['s0'], 6), round(z['s1'], 6)), []).append(z)
    schluessel = sorted(saeulen)

    def station(sw):
        return (total - sw) if reverse else sw

    # 1. Fundament mit dem gewaehlten Ueberstand auf allen Seiten.
    fund_daten, _fund_plan, _fund_stationen, fund_polygone = \
        gab_fundament_primitiven(zellen, pl_pts, st_tab, p, reverse)
    draw_surface_union(
        fund_polygone, prefix + 'FUNDAMENT', fundament_rgb(p), True,
        deckkraft)
    fund_lauefe = []
    fund_quermasse = []
    for fund in fund_daten:
        if (fund_lauefe and
                abs(fund_lauefe[-1]['s1'] - fund['s0']) <= 1e-6 and
                abs(fund_lauefe[-1]['gab_b_cm'] - fund['gab_b_cm']) <= 1e-6):
            fund_lauefe[-1]['s1'] = fund['s1']
            fund_lauefe[-1]['flaeche_m2'] += fund['flaeche_m2']
        else:
            fund_lauefe.append(dict(fund))
    for fund in fund_lauefe:
        sm = station((fund['s0'] + fund['s1']) / 2.0)
        q, richt = point_at_station(pl_pts, st_tab, sm)
        ux, uy = richt
        nx, ny = -uy * sign, ux * sign
        fund_quermasse.append((
            (q[0] - nx * fund['ueberstand_units'],
             q[1] - ny * fund['ueberstand_units']),
            (q[0] + nx * U.cm(fund['gab_b_cm'] +
                               fund['ueberstand_cm']),
             q[1] + ny * U.cm(fund['gab_b_cm'] +
                               fund['ueberstand_cm'])),
            fund['breite_cm']))

    # 2. Sichtbare Baender aller Lagen. Die Baender ueberlappen sich nicht;
    # dadurch bleiben die Farben auch bei transparenter Darstellung rein.
    band_intervalle = {}
    for sch in schluessel:
        innen = 0.0
        for z in sorted(saeulen[sch], key=lambda q: -q['ytop']):
            aussen = float(z['b_cm'])
            if aussen > innen + 1e-9:
                key = (round(innen, 6), round(aussen, 6), int(round(aussen)))
                band_intervalle.setdefault(key, []).append([sch[0], sch[1]])
                innen = aussen
            else:
                innen = max(innen, aussen)

    for (innen, aussen, b), intervalle in sorted(
            band_intervalle.items(), key=lambda item: item[0][1]):
        laeufe = []
        for s_a, s_b in sorted(intervalle):
            if laeufe and abs(laeufe[-1][1] - s_a) <= 1e-6:
                laeufe[-1][1] = s_b
            else:
                laeufe.append([s_a, s_b])
        for s_a, s_b in laeufe:
            sa, sb = station(s_a), station(s_b)
            draw_ring_surface(
                pl_pts, st_tab, sa, sb, U.cm(innen), U.cm(aussen), sign,
                '%s%03d' % (prefix, b),
                farben.get(b, (52000, 52000, 52000)), deckkraft)

    # 3. Trennstriche zwischen den Gabionen
    for sch in schluessel[:-1]:
        tiefst = U.cm(max(z['b_cm'] for z in saeulen[sch]))
        q, richt = point_at_station(pl_pts, st_tab, station(sch[1]))
        ux, uy = richt
        nx, ny = -uy * sign, ux * sign
        apply_attrs(um_cls, None, False)
        try:
            vs.MoveTo(q[0], q[1])
            vs.LineTo(q[0] + nx * tiefst, q[1] + ny * tiefst)
            _reg(vs.LNewObj())
        except Exception:
            pass

    # 4. Beschriftung je Saeule
    for sch in schluessel:
        lagen = sorted(saeulen[sch], key=lambda q: -q['ytop'])
        sa, sb = station(sch[0]), station(sch[1])
        pa, _r = point_at_station(pl_pts, st_tab, min(sa, sb))
        pb, _r = point_at_station(pl_pts, st_tab, max(sa, sb))
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        L = math.hypot(dx, dy)
        if L < 1e-12:
            continue
        ux, uy = dx / L, dy / L
        nx, ny = -uy * sign, ux * sign
        ang = math.degrees(math.atan2(uy, ux))
        if ang > 90.0:
            ang -= 180.0
        if ang < -90.0:
            ang += 180.0
        oben = lagen[0]
        tief_oben = U.cm(oben['b_cm'])
        tiefst = U.cm(max(z['b_cm'] for z in lagen))
        mx, my = (pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0
        set_text_style(p['font'], p['font_size'])
        make_text('%d | B %g' % (oben['nr'], oben['b_cm']),
                  mx + nx * tief_oben / 2.0, my + ny * tief_oben / 2.0,
                  ang, 2, 2, txt_cls)
        if p.get('bemassung'):
            make_text('-%s-' % fmt_cm(U.to_cm(L)),
                      mx + nx * (tiefst - th * 0.6),
                      my + ny * (tiefst - th * 0.6), ang, 2, 2, bem_cls)
        if p.get('ref_aktiv'):
            # Unterkante VOR der Gabione, Oberkante direkt HINTER der
            # obersten Gabione - beide parallel zur Mauer.
            make_text('UK %s' % kote_text(p, lagen[-1]['ybot']),
                      mx - nx * th * 0.8, my - ny * th * 0.8,
                      ang, 2, 2, kote_cls)
            make_text('OK %s' % kote_text(p, oben['ytop']),
                      mx + nx * (tief_oben + th * 0.8),
                      my + ny * (tief_oben + th * 0.8),
                      ang, 2, 2, kote_cls)

    if p.get('bemassung'):
        set_text_style(p['font'], p['font_size'])
        fund_cls = prefix + 'FUNDAMENT-BEM'
        for pa, pb, breite_cm in eindeutige_fundament_quermasse(
                fund_quermasse):
            dim_between(pa, pb, dim_abstand_units(p) * 0.65,
                        'B Fund. = %s cm' % fmt_cm(breite_cm),
                        fund_cls, p, kurz=True)
        draw_gab_aufsicht_stationsmasse(pl_pts, p, sign)


def _station_auf_plan(punkt, pl_pts, st_tab):
    """Station of a known point on the piecewise-linear plan path."""
    beste = None
    for index, (a, b) in enumerate(zip(pl_pts, pl_pts[1:])):
        dx, dy = b[0] - a[0], b[1] - a[1]
        laenge2 = dx * dx + dy * dy
        if laenge2 <= 1e-18:
            continue
        t = max(0.0, min(1.0,
            ((punkt[0] - a[0]) * dx + (punkt[1] - a[1]) * dy) / laenge2))
        q = a[0] + t * dx, a[1] + t * dy
        abstand = math.dist(tuple(punkt), q)
        kandidat = st_tab[index] + t * math.sqrt(laenge2)
        if beste is None or abstand < beste[0]:
            beste = abstand, kandidat
    if beste is None:
        raise ValueError('Eine 3D-Planstation konnte nicht bestimmt werden.')
    return beste[1]


def _besitzer_liste(wert, anzahl):
    if isinstance(wert, (tuple, list, set)):
        kandidaten = wert
    else:
        kandidaten = (wert,)
    return tuple(sorted(set(
        int(index) for index in kandidaten
        if index is not None and 0 <= int(index) < anzahl)))


def _band_meshes(polygone, daten, pl_pts, st_tab, profil, stil):
    """Publish the same plan primitives as chamfered 3D wall bodies.

    ``profil(record, plan_station)`` returns local bottom/top Z. ``stil``
    returns class, colour and opacity. Exterior corner wedges use the mean of
    their adjoining records; segment bodies retain their exact linear height
    profile.
    """
    erzeugt = []
    for nummer, primitive in enumerate(polygone, 1):
        punkte = primitive.get('punkte', primitive)
        if len(punkte) < 3:
            continue
        besitzer = _besitzer_liste(primitive.get('besitzer'), len(daten))
        if not besitzer:
            continue
        linie = primitive.get('linie')
        if linie:
            station_a = _station_auf_plan(linie[0], pl_pts, st_tab)
            station_b = _station_auf_plan(linie[1], pl_pts, st_tab)
            unten_a, oben_a = profil(daten[besitzer[0]], station_a)
            unten_b, oben_b = profil(daten[besitzer[0]], station_b)
        else:
            station = sum(_station_auf_plan(q, pl_pts, st_tab)
                          for q in punkte) / float(len(punkte))
            werte = [profil(daten[index], station) for index in besitzer]
            unten_a = unten_b = sum(q[0] for q in werte) / len(werte)
            oben_a = oben_b = sum(q[1] for q in werte) / len(werte)
            linie = punkte[0], punkte[1]
        if min(oben_a - unten_a, oben_b - unten_b) <= U.cm(CHAMFER_CM * 2.0001):
            raise ValueError(
                '3D-Koerper %d ist fuer eine umlaufende 5x5-mm-Fase zu niedrig.' %
                nummer)
        cls, rgb, opacity = stil(daten[besitzer[0]])
        handle = make_chamfered_mesh(
            punkte, min(unten_a, unten_b), max(oben_a, oben_b),
            cls, rgb, opacity,
            (linie[0], linie[1], unten_a, unten_b, oben_a, oben_b))
        erzeugt.append((handle, besitzer))
    return erzeugt


def _winkel_elementgruppen(staemme, fuesse, elements):
    """Keep each 3D L-element's stem and foot together after outer ungrouping."""
    nach_element = {}
    for art, zeilen in (('wand', staemme), ('fuss', fuesse)):
        for handle, besitzer in zeilen:
            if handle is None or len(besitzer) != 1:
                continue
            nach_element.setdefault(besitzer[0], {}).setdefault(art, []).append(handle)
    gruppen = []
    for index in sorted(nach_element):
        teile = nach_element[index]
        if not teile.get('wand') or not teile.get('fuss'):
            continue
        handles = teile['wand'] + teile['fuss']
        gruppe = group_objects(handles)
        if gruppe is None:
            continue
        for handle in handles:
            try:
                NEW_OBJS.remove(handle)
            except ValueError:
                pass
        NEW_OBJS.append(gruppe)
        try:
            nr = int(elements[index].get('nr', index + 1))
            vs.SetName(gruppe, unique_name('PD-MWL-ELEMENT-%03d-' % nr))
        except Exception:
            pass
        gruppen.append(gruppe)
    return gruppen


def draw_winkel_3d(elements, pl_pts, st_tab, p, colors, reverse):
    """Automatic hybrid 3D output for wall stems, L-feet and foundations."""
    if not elements or len(pl_pts or ()) < 2:
        return
    total = st_tab[-1]
    sign = 1.0 if p.get('seite', 0) == 0 else -1.0
    deckkraft = max(0.0, 100.0 - p.get('transparenz', 0.0))
    dicke = U.cm(float(p.get('dicke_cm', 0.0)))

    def plan_station(wandstation):
        return total - wandstation if reverse else wandstation

    def wand_x(e, plan_s):
        wand_s = total - plan_s if reverse else plan_s
        wand_s = max(e['s0'], min(e['s1'], wand_s))
        return e['x0'] + wand_s - e['s0']

    abschnitte = [(plan_station(e['s0']), plan_station(e['s1']), dicke, index)
                  for index, e in enumerate(elements)]
    koerper = band_primitiven(pl_pts, st_tab, abschnitte, 0.0, sign)

    def wand_profil(e, plan_s):
        x = wand_x(e, plan_s)
        top = e.get('top_pts') or [(e['x0'], e['ytop']), (e['x1'], e['ytop'])]
        return _z3d(p, e['ybot']), _z3d(p, y_at(top, x))

    def wand_stil(e):
        cls = _klasse_3d(class_name_for_height(p['prefix'], e['h_cm']))
        rgb = colors.get(int(round(e['h_cm'])), (52000, 52000, 52000))
        return cls, rgb, deckkraft

    staemme = _band_meshes(
        koerper, elements, pl_pts, st_tab, wand_profil, wand_stil)

    fuss_abschnitte = [(
        plan_station(e['s0']), plan_station(e['s1']),
        U.cm(max(float(p.get('dicke_cm', 0.0)), float(e.get('fuss_cm', 0.0)))),
        index) for index, e in enumerate(elements)]
    fuesse = winkel_fuss_primitiven(pl_pts, st_tab, fuss_abschnitte, sign)
    fuss_dicke = U.cm(float(p.get('winkel_fuss_staerke', 15.0)))

    def fuss_profil(e, _plan_s):
        return _z3d(p, e['ybot']), _z3d(p, e['ybot'] + fuss_dicke)

    def fuss_stil(e):
        rgb = colors.get(int(round(e['h_cm'])), (52000, 52000, 52000))
        return _klasse_3d(p['prefix'] + 'FUSS'), rgb, deckkraft

    fuss_koerper = _band_meshes(
        fuesse, elements, pl_pts, st_tab, fuss_profil, fuss_stil)
    _winkel_elementgruppen(staemme, fuss_koerper, elements)

    fundamente = winkel_fundamente(elements, p)
    fund_abschnitte = [(
        plan_station(fund['s0']), plan_station(fund['s1']),
        U.cm(fund['fuss_cm'] + fund['ueberstand_cm']), index)
        for index, fund in enumerate(fundamente)]
    vorne = U.cm(max((fund['ueberstand_cm'] for fund in fundamente), default=0.0))
    fund_polygone = band_primitiven(
        pl_pts, st_tab, fund_abschnitte, vorne, sign)

    def fund_profil(fund, plan_s):
        wand_s = total - plan_s if reverse else plan_s
        wand_s = max(fund['s0'], min(fund['s1'], wand_s))
        x = fund['basis_pts'][0][0] + wand_s - fund['s0']
        return (_z3d(p, y_at(fund['basis_pts'], x)),
                _z3d(p, y_at(fund['top_pts'], x)))

    def fund_stil(_fund):
        return (_klasse_3d(p['prefix'] + 'FUNDAMENT'),
                fundament_rgb(p), deckkraft)

    _band_meshes(
        fund_polygone, fundamente, pl_pts, st_tab, fund_profil, fund_stil)


def draw_gabione_3d(zellen, pl_pts, st_tab, p, farben, reverse):
    """Automatic chamfered 3D gabion cells and their foundation."""
    if not zellen or len(pl_pts or ()) < 2:
        return
    total = st_tab[-1]
    sign = 1.0 if p.get('seite', 0) == 0 else -1.0
    deckkraft = max(0.0, 100.0 - p.get('transparenz', 0.0))

    def plan_station(wandstation):
        return total - wandstation if reverse else wandstation

    abschnitte = [(plan_station(z['s0']), plan_station(z['s1']),
                   U.cm(float(z['b_cm'])), index)
                  for index, z in enumerate(zellen)]
    koerper = band_primitiven(pl_pts, st_tab, abschnitte, 0.0, sign)

    def gab_profil(z, _plan_s):
        return _z3d(p, z['ybot']), _z3d(p, z['ytop'])

    def gab_stil(z):
        b = int(round(z['b_cm']))
        return (_klasse_3d('%s%03d' % (p['gab_prefix'], b)),
                farben.get(b, (52000, 52000, 52000)), deckkraft)

    _band_meshes(koerper, zellen, pl_pts, st_tab, gab_profil, gab_stil)

    fundamente, fund_plan, fund_stationen, fund_polygone = \
        gab_fundament_primitiven(zellen, pl_pts, st_tab, p, reverse)
    if not fundamente:
        return
    ueber = U.cm(gab_fund_ueberstand_cm(p))
    mapped = [plan_station(wert) for fund in fundamente
              for wert in (fund['s0'], fund['s1'])]
    plan_start = min(mapped)
    occupied = max(mapped) - plan_start
    owner_ranges = []
    for fund in fundamente:
        a = plan_station(fund['s0']) - plan_start + ueber
        b = plan_station(fund['s1']) - plan_start + ueber
        a, b = min(a, b), max(a, b)
        if a <= ueber + 1e-8:
            a = 0.0
        if b >= occupied + ueber - 1e-8:
            b = fund_stationen[-1]
        owner_ranges.append((a, b))
    owner_index = dict((id(fund), index)
                       for index, fund in enumerate(fundamente))

    def fund_profil(fund, fund_plan_s):
        index = owner_index[id(fund)]
        a, b = owner_ranges[index]
        fraction = 0.0 if b - a <= 1e-12 else max(
            0.0, min(1.0, (fund_plan_s - a) / (b - a)))
        xa, xb = fund['basis_pts'][0][0], fund['basis_pts'][-1][0]
        x = xa + (xb - xa) * fraction
        return (_z3d(p, y_at(fund['basis_pts'], x)),
                _z3d(p, y_at(fund['top_pts'], x)))

    def fund_stil(_fund):
        return (_klasse_3d(p['gab_prefix'] + 'FUNDAMENT'),
                fundament_rgb(p), deckkraft)

    _band_meshes(
        fund_polygone, fundamente, fund_plan, fund_stationen,
        fund_profil, fund_stil)


def gab_tabelle_zeichnen(zellen, p, x, y):
    """Auswertung der Gabionenwand als Tabelle in der Zeichnung."""
    cls = p['gab_prefix'] + 'TABELLE'
    reihen = gab_summen(zellen, p)
    th, line_h, cw = text_metrics(p)
    spalten = [('Breite [cm]', 12, lambda r: '%g' % r['b_cm']),
               ('Anzahl', 8, lambda r: '%d' % r['anzahl']),
               ('Laenge [m]', 11, lambda r: '%.2f' % r['laenge_m']),
               ('Front ges [m2]', 15, lambda r: '%.2f' % r['front_m2']),
               ('Front sichtb [m2]', 18, lambda r: '%.2f' % r['sicht_m2']),
               ('Kopf [m2]', 11, lambda r: '%.2f' % r['kopf_m2']),
               ('Gab.-Vol. [m3]', 15, lambda r: '%.2f' % r['volumen_m3']),
               ('Rueckseite [m2]', 16, lambda r: '%.2f' % r['rueck_m2']),
               ('Fund.-Aufsicht [m2]', 20,
                lambda r: '%.2f' % r['fund_m2']),
               ('Fundament [m3]', 16,
                lambda r: '%.2f' % r['fund_volumen_m3']),
               ('Gab. < UK [m3]', 16,
                lambda r: '%.2f' % r['gab_unter_gel_m3']),
               ('Aushub [m3]', 13, lambda r: '%.2f' % r['aushub_m3'])]
    spalten = [(t, max(br, len(t) + 2), fn) for t, br, fn in spalten]
    cols, acc = [], 0.0
    for _t, br, _f in spalten:
        cols.append(acc)
        acc += br * cw
    gesamt = acc
    set_text_style(p['font'], p['font_size'])

    yy = y
    make_text('GABIONENWAND - AUSWERTUNG', x, yy, 0, 1, 4, cls, kollision=False)
    yy -= line_h * 1.6
    for i, (t, _b, _f) in enumerate(spalten):
        make_text(t, x + cols[i], yy, 0, 1, 4, cls, kollision=False)
    yy -= line_h * 0.35
    _dline(x, yy, x + gesamt, yy, cls)
    yy -= line_h

    su = {}
    for r in reihen:
        for i, (_t, _b, fn) in enumerate(spalten):
            make_text(fn(r), x + cols[i], yy, 0, 1, 4, cls, kollision=False)
        for k, v in r.items():
            if k != 'b_cm':
                su[k] = su.get(k, 0.0) + v
        yy -= line_h

    yy -= line_h * 0.25
    _dline(x, yy, x + gesamt, yy, cls)
    yy -= line_h
    werte = ['SUMME', '%d' % su.get('anzahl', 0),
             '%.2f' % su.get('laenge_m', 0.0), '%.2f' % su.get('front_m2', 0.0),
             '%.2f' % su.get('sicht_m2', 0.0), '%.2f' % su.get('kopf_m2', 0.0),
             '%.2f' % su.get('volumen_m3', 0.0),
             '%.2f' % su.get('rueck_m2', 0.0),
             '%.2f' % su.get('fund_m2', 0.0),
             '%.2f' % su.get('fund_volumen_m3', 0.0),
             '%.2f' % su.get('gab_unter_gel_m3', 0.0),
             '%.2f' % su.get('aushub_m3', 0.0)]
    for i, t in enumerate(werte):
        make_text(t, x + cols[i], yy, 0, 1, 4, cls, kollision=False)
    unten = yy - line_h * 0.35
    table_frame(x, y + line_h * 0.9, gesamt, unten, cols, cw, cls)
    return unten


def gab_csv(zellen, p):
    """Auswertung zusaetzlich als CSV neben der Zeichnung."""
    reihen = gab_summen(zellen, p)
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')
    f = os.path.join(doc_dir(), '%s_PD-GAB_Auswertung_%s_%s.csv'
                     % (doc_stem(), export_kennung(p), stamp))

    def z(v):
        return ('%.2f' % v).replace('.', ',')

    try:
        with open(f, 'w', encoding='utf-8-sig') as fp:
            fp.write('Breite [cm];Anzahl;Laenge [m];Front gesamt [m2];'
                     'Front sichtbar [m2];Aufsicht Kopf [m2];Volumen [m3];'
                     'Rueckseite [m2];Gabionensohle [m2];'
                     'Fundament Laenge [m];Fundament Aufsichtsflaeche [m2];'
                     'Fundament Volumen [m3];Gabionen unter UK Gelaende [m3];'
                     'Erdaushub gesamt [m3]\n')
            felder = ('laenge_m', 'front_m2', 'sicht_m2', 'kopf_m2',
                      'volumen_m3', 'rueck_m2', 'sohle_m2',
                      'fund_laenge_m', 'fund_m2', 'fund_volumen_m3',
                      'gab_unter_gel_m3', 'aushub_m3')
            su = dict((schl, 0.0) for schl in felder)
            su['anzahl'] = 0
            for r in reihen:
                fp.write(';'.join(['%g' % r['b_cm'], '%d' % r['anzahl']] +
                                  [z(r[schl]) for schl in felder]) + '\n')
                for schl in su:
                    su[schl] += r[schl]
            fp.write(';'.join(['SUMME', '%d' % su['anzahl']] +
                              [z(su[schl]) for schl in felder]) + '\n')
        return [f]
    except Exception:
        return []


def gab_schnittstellen(zellen, p, L_abw, variante):
    """Stationen der Systemschnitte.
    variante 0: eine Station nach Vorgabe
    variante 1: bei jedem Wechsel der Gabionenbauweise, jeweils mittig
    """
    saeulen = {}
    for z in zellen:
        saeulen.setdefault((round(z['s0'], 6), round(z['s1'], 6)), []).append(z)
    schluessel = sorted(saeulen)

    if variante == 0:
        st = U.cm(float(p.get('schnitt_station', 0.0)) * 100.0)
        return [max(0.0, min(st, L_abw))]

    # Bauweise = Folge der Breiten von oben nach unten
    def bauweise(sch):
        return tuple(round(z['b_cm'], 1)
                     for z in sorted(saeulen[sch], key=lambda q: -q['ytop']))

    stationen = []
    lauf_a, letzte = schluessel[0][0], bauweise(schluessel[0])
    for sch in schluessel[1:] + [None]:
        art = bauweise(sch) if sch else None
        if art != letzte:
            lauf_b = sch[0] if sch else schluessel[-1][1]
            stationen.append((lauf_a + lauf_b) / 2.0)
            if sch:
                lauf_a, letzte = sch[0], art
    return stationen


def _schnittnummer_aus_text(wert):
    """Schnittnummer aus 'S3 ...' oder einem Namen '*SCHNITT-S003-*'."""
    text = str(wert or '').strip().upper()
    start = None
    if len(text) >= 2 and text[0] == 'S' and text[1].isdigit():
        start = 1
    else:
        marker = 'SCHNITT-S'
        pos = text.find(marker)
        if pos >= 0:
            start = pos + len(marker)
    if start is None:
        return 0
    ende = start
    while ende < len(text) and text[ende].isdigit():
        ende += 1
    try:
        return int(text[start:ende]) if ende > start else 0
    except Exception:
        return 0


def naechste_gab_schnittnummer():
    """Naechste freie S-Nummer aus Gruppen- und Textnamen im Dokument."""
    nummern = set()

    def pruefe(h, tiefe=0):
        if h is None or tiefe > 20:
            return
        try:
            nr = _schnittnummer_aus_text(vs.GetName(h))
            if nr > 0:
                nummern.add(nr)
        except Exception:
            pass
        if get_type(h) == 10:                 # Textobjekt
            try:
                nr = _schnittnummer_aus_text(vs.GetText(h))
                if nr > 0:
                    nummern.add(nr)
            except Exception:
                pass
        if get_type(h) == 11:                 # Gruppe
            try:
                kind = vs.FInGroup(h)
            except Exception:
                kind = None
            zaehler = 0
            while handle_valid(kind) and zaehler < MAX_ITER:
                pruefe(kind, tiefe + 1)
                zaehler += 1
                try:
                    kind = vs.NextObj(kind)
                except Exception:
                    break

    try:
        vs.ForEachObjectInLayer(lambda h: pruefe(h), 0, 0, 2)
    except Exception:
        pass
    return (max(nummern) + 1) if nummern else 1


def gab_schnitte(zellen, p, x0, L_abw, pl_pts, st_tab, reverse, y_tabelle,
                 variante, farben, start_nr=1, sammlung=None):
    """Systemschnitte unterhalb der Tabellen, im Raster angeordnet.
    Die Schnittlagen werden in Ansicht und Aufsicht beschriftet."""
    prefix = p['gab_prefix']
    txt_cls = prefix + 'TXT'
    bem_cls = prefix + 'BEM'
    fund_bem_cls = prefix + 'FUNDAMENT-BEM'
    kote_cls = prefix + 'KOTE'
    th, line_h, cw = text_metrics(p)

    saeulen = {}
    for z in zellen:
        saeulen.setdefault((round(z['s0'], 6), round(z['s1'], 6)), []).append(z)
    schluessel = sorted(saeulen)

    def saeule_bei(station):
        for sch in schluessel:
            if sch[0] - 1e-9 <= station <= sch[1] + 1e-9:
                return saeulen[sch]
        return saeulen[schluessel[-1]]

    stationen = gab_schnittstellen(zellen, p, L_abw, variante)
    if not stationen:
        return 0

    fund_tiefe_cm = max(0.0, float(p.get(
        'gab_fund_tiefe', GAB_FUND_TIEFE_CM)))
    fund_ueber_cm = gab_fund_ueberstand_cm(p)
    max_tief = U.cm(max(z['b_cm'] for z in zellen) +
                    2.0 * fund_ueber_cm)
    y_oben = max(z['ytop'] for z in zellen)
    y_unten = min(
        [z['ybot'] for z in zellen] +
        [q[1] - U.cm(fund_tiefe_cm)
         for z in zellen for q in z.get('gel_uk_pts', [])] +
        [z['ybot'] - U.cm(10.0) for z in zellen])
    zell_h = (y_oben - y_unten) + 5.0 * line_h
    zell_b = max_tief + 22.0 * cw
    je_reihe = max(1, int((L_abw / zell_b) + 1e-9)) if zell_b > 0 else 1
    je_reihe = max(1, min(je_reihe, len(stationen)))
    basis_y = y_tabelle - 4.0 * line_h

    if sammlung is not None:
        sammlung.setdefault('schnitte', [])
        sammlung.setdefault('markierungen', [])

    for i, station in enumerate(stationen):
        start_schnitt = len(NEW_OBJS)
        lagen = sorted(saeule_bei(station), key=lambda q: -q['ytop'])
        spalte = i % je_reihe
        reihe = i // je_reihe
        ox = x0 + spalte * zell_b
        oy = basis_y - reihe * zell_h
        versatz = oy - y_oben          # Oberkante der Wand auf oy legen

        name = 'S%d' % (int(start_nr) + i)
        set_text_style(p['font'], p['font_size'])
        make_text('%s  -  Station %.2f m' % (name, U.to_m(station)),
                  ox, oy + line_h * 1.2, 0, 1, 4, txt_cls)

        # Fundament im Querschnitt: gewaehlter Ueberstand auf beiden Seiten,
        # Sohle im frei gewaehlten Abstand unter UK Gelaende.
        x_station = x0 + station
        profil = lagen[0].get('gel_uk_pts') or [
            (lagen[0]['x0'], lagen[0]['gel_uk']),
            (lagen[0]['x1'], lagen[0]['gel_uk'])]
        gel_uk_original = y_at(profil, x_station)
        fund_basis = min(gel_uk_original - U.cm(fund_tiefe_cm),
                         lagen[-1]['ybot'] - U.cm(10.0)) + versatz
        fund_top = max(fund_basis,
                       min(lagen[-1]['ybot'], gel_uk_original) + versatz)
        fund_vorne = ox - U.cm(fund_ueber_cm)
        fund_hinten = ox + U.cm(max(z['b_cm'] for z in lagen) +
                               fund_ueber_cm)
        make_filled_poly([(fund_vorne, fund_basis),
                          (fund_hinten, fund_basis),
                          (fund_hinten, fund_top),
                          (fund_vorne, fund_top)],
                         prefix + 'FUNDAMENT', fundament_rgb(p),
                         max(0.0, 100.0 - p.get('transparenz', 0.0)))
        make_text('Fundament B %.0f cm | Sohle %.0f cm unter UK' % (
                      max(z['b_cm'] for z in lagen) +
                      2.0 * fund_ueber_cm,
                      fund_tiefe_cm),
                  (fund_vorne + fund_hinten) / 2.0,
                  (fund_basis + fund_top) / 2.0, 0, 2, 2, fund_bem_cls)
        dim_between((fund_vorne, fund_basis), (fund_hinten, fund_basis),
                    -line_h * 0.8,
                    'B Fund. = %s cm' % fmt_cm(U.to_cm(
                        fund_hinten - fund_vorne)), fund_bem_cls, p)
        dim_between((fund_vorne, fund_basis), (fund_vorne, fund_top),
                    -line_h * 0.8,
                    'd = %s cm' % fmt_cm(U.to_cm(fund_top - fund_basis)),
                    fund_bem_cls, p)
        dim_between((fund_vorne, fund_basis),
                    (fund_vorne, gel_uk_original + versatz),
                    -line_h * 2.0,
                    'T = %s cm' % fmt_cm(U.to_cm(
                        gel_uk_original + versatz - fund_basis)),
                    fund_bem_cls, p)

        for z in lagen:
            b = int(round(z['b_cm']))
            tief = U.cm(z['b_cm'])
            yb, yt = z['ybot'] + versatz, z['ytop'] + versatz
            make_filled_poly([(ox, yb), (ox + tief, yb),
                              (ox + tief, yt), (ox, yt)],
                             '%s%03d' % (prefix, b),
                             farben.get(b, (52000, 52000, 52000)),
                             max(0.0, 100.0 - p.get('transparenz', 0.0)))
            make_text('%g/%g' % (z['b_cm'], z['h_cm']),
                      ox + tief / 2.0, (yb + yt) / 2.0, 0, 2, 2, txt_cls)

        # Gelaende: je ein 10 cm breiter Balken - UK an der Vorderseite,
        # OK hinter der obersten Gabione. Beide mit Hoehenkote.
        balken = U.cm(10.0)
        dicke = balken * 0.25
        gel_ok = lagen[0]['gel_ok'] + versatz
        gel_uk = lagen[0]['gel_uk'] + versatz
        tief_oben_s = U.cm(lagen[0]['b_cm'])

        make_filled_poly([(ox - balken, gel_uk - dicke / 2.0),
                          (ox, gel_uk - dicke / 2.0),
                          (ox, gel_uk + dicke / 2.0),
                          (ox - balken, gel_uk + dicke / 2.0)],
                         bem_cls, (0, 0, 0), 100.0)
        make_text('UK Gel. %s' % kote_text(p, lagen[0]['gel_uk']),
                  ox - balken - cw, gel_uk, 0, 3, 2, kote_cls)

        make_filled_poly([(ox + tief_oben_s, gel_ok - dicke / 2.0),
                          (ox + tief_oben_s + balken, gel_ok - dicke / 2.0),
                          (ox + tief_oben_s + balken, gel_ok + dicke / 2.0),
                          (ox + tief_oben_s, gel_ok + dicke / 2.0)],
                         bem_cls, (0, 0, 0), 100.0)
        make_text('OK Gel. %s' % kote_text(p, lagen[0]['gel_ok']),
                  ox + tief_oben_s + balken + cw, gel_ok, 0, 1, 2, kote_cls)

        if p.get('ref_aktiv'):
            make_text(kote_text(p, lagen[0]['ytop']), ox - cw,
                      lagen[0]['ytop'] + versatz, 0, 3, 2, kote_cls)
            make_text(kote_text(p, lagen[-1]['ybot']), ox - cw,
                      lagen[-1]['ybot'] + versatz, 0, 3, 2, kote_cls)

        if sammlung is not None:
            sammlung['schnitte'].append((name, list(NEW_OBJS[start_schnitt:])))

        # Schnittlage in der Ansicht
        start_markierung = len(NEW_OBJS)
        xs = x0 + station
        _dline(xs, y_unten - line_h * 1.5, xs, y_oben + line_h * 1.5, bem_cls)
        make_text(name, xs, y_oben + line_h * 1.7, 0, 2, 4, txt_cls)

        # Schnittlage in der Aufsicht
        if pl_pts and st_tab:
            ss = (st_tab[-1] - station) if reverse else station
            q, richt = point_at_station(pl_pts, st_tab, ss)
            ux, uy = richt
            sign = 1.0 if p['seite'] == 0 else -1.0
            nx, ny = -uy * sign, ux * sign
            _dline(q[0] - nx * cw * 3.0, q[1] - ny * cw * 3.0,
                   q[0] + nx * (max_tief + cw * 3.0),
                   q[1] + ny * (max_tief + cw * 3.0), bem_cls)
            ang = math.degrees(math.atan2(ny, nx))
            if ang > 90.0:
                ang -= 180.0
            if ang < -90.0:
                ang += 180.0
            make_text(name, q[0] - nx * cw * 4.5, q[1] - ny * cw * 4.5,
                      ang, 2, 2, txt_cls)
        if sammlung is not None:
            sammlung['markierungen'].extend(NEW_OBJS[start_markierung:])
    return len(stationen)


def winkel_schnittstellen(elements, p, L_abw, variante):
    """Schnittstationen der Winkelsteinwand analog zur Gabionenwand."""
    if variante == 0:
        st = U.cm(float(p.get('schnitt_station', 0.0)) * 100.0)
        return [max(0.0, min(st, L_abw))]

    def bauweise(e):
        return (round(float(e.get('h_cm', 0.0)), 1),
                round(float(e.get('fuss_cm', 0.0)), 1),
                round(float(p.get('dicke_cm', 0.0)), 1),
                round(float(p.get('winkel_fuss_staerke', 15.0)), 1))

    stationen = []
    lauf_a = elements[0]['s0']
    letzte = bauweise(elements[0])
    for i in range(1, len(elements) + 1):
        e = elements[i] if i < len(elements) else None
        art = bauweise(e) if e is not None else None
        if art != letzte:
            lauf_b = e['s0'] if e is not None else elements[-1]['s1']
            stationen.append((lauf_a + lauf_b) / 2.0)
            if e is not None:
                lauf_a, letzte = e['s0'], art
    return stationen


def winkel_schnitte(elements, p, x0, L_abw, pl_pts, st_tab, reverse,
                    y_tabelle, variante, farben, start_nr=1, sammlung=None):
    """Verschiebbare Systemschnitte einer Winkelsteinwand erzeugen."""
    prefix = p['prefix']
    txt_cls = prefix + 'TXT'
    bem_cls = prefix + 'BEM'
    fund_bem_cls = prefix + 'FUNDAMENT-BEM'
    kote_cls = prefix + 'KOTE'
    th, line_h, cw = text_metrics(p)
    fundamente = winkel_fundamente(elements, p)
    fund_nach_nr = dict((f.get('nr'), f) for f in fundamente)
    stationen = winkel_schnittstellen(elements, p, L_abw, variante)
    if not stationen:
        return 0

    def element_bei(station):
        for e in elements:
            if e['s0'] - 1e-9 <= station <= e['s1'] + 1e-9:
                return e
        return elements[-1]

    max_tief_cm = max(float(e.get('fuss_cm', 0.0)) for e in elements)
    max_tief_cm += 2.0 * float(p.get(
        'fund_ueberstand', WINKEL_FUND_UEBERSTAND_CM))
    max_tief = U.cm(max_tief_cm)
    y_oben = max(y_on_top(e.get('top_pts') or [
        (e['x0'], e['ytop']), (e['x1'], e['ytop'])], e['x1'])
        for e in elements)
    y_unten = min(q[1] for f in fundamente for q in f['basis_pts'])
    zell_h = (y_oben - y_unten) + 7.0 * line_h
    zell_b = max_tief + 24.0 * cw
    je_reihe = max(1, int((L_abw / zell_b) + 1e-9)) if zell_b > 0 else 1
    je_reihe = max(1, min(je_reihe, len(stationen)))
    basis_y = y_tabelle - 4.0 * line_h

    if sammlung is not None:
        sammlung.setdefault('schnitte', [])
        sammlung.setdefault('markierungen', [])

    for i, station in enumerate(stationen):
        start_schnitt = len(NEW_OBJS)
        e = element_bei(station)
        fund = fund_nach_nr.get(e.get('nr'))
        if not fund:
            continue
        spalte, reihe = i % je_reihe, i // je_reihe
        ox = x0 + spalte * zell_b
        x_station = e['x0'] + max(0.0, min(
            station - e['s0'], e['x1'] - e['x0']))
        top_pts = e.get('top_pts') or [(e['x0'], e['ytop']),
                                       (e['x1'], e['ytop'])]
        top_original = y_on_top(top_pts, x_station)
        oy = basis_y - reihe * zell_h
        versatz = oy - top_original
        bot = e['ybot'] + versatz
        top = top_original + versatz
        gel_original = y_at(fund.get('gel_pts') or [], x_station)
        fund_basis = y_at(fund['basis_pts'], x_station) + versatz
        fund_top = y_at(fund['top_pts'], x_station) + versatz

        name = 'S%d' % (int(start_nr) + i)
        make_text('%s  -  Station %.2f m' % (name, U.to_m(station)),
                  ox, top + line_h * 1.2, 0, 1, 4, txt_cls)

        ueber = U.cm(float(p.get(
            'fund_ueberstand', WINKEL_FUND_UEBERSTAND_CM)))
        fuss = U.cm(max(float(e.get('fuss_cm', 0.0)),
                        float(p.get('dicke_cm', 0.0))))
        dicke = U.cm(float(p.get('dicke_cm', 0.0)))
        fuss_staerke = min(U.cm(float(p.get('winkel_fuss_staerke', 15.0))),
                           max(0.0, top - bot))
        fund_vorne, fund_hinten = ox - ueber, ox + fuss + ueber
        make_filled_poly([(fund_vorne, fund_basis),
                          (fund_hinten, fund_basis),
                          (fund_hinten, fund_top),
                          (fund_vorne, fund_top)],
                         prefix + 'FUNDAMENT', fundament_rgb(p),
                         max(0.0, 100.0 - p.get('transparenz', 0.0)))

        cls = class_name_for_height(prefix, e['h_cm'])
        rgb = farben.get(int(round(e['h_cm'])), (52000, 52000, 52000))
        make_filled_poly([(ox, bot), (ox + fuss, bot),
                          (ox + fuss, bot + fuss_staerke),
                          (ox, bot + fuss_staerke)], cls, rgb,
                         max(0.0, 100.0 - p.get('transparenz', 0.0)))
        make_filled_poly([(ox, bot + fuss_staerke),
                          (ox + dicke, bot + fuss_staerke),
                          (ox + dicke, top), (ox, top)], cls, rgb,
                         max(0.0, 100.0 - p.get('transparenz', 0.0)))
        make_text('Winkelstein H %g | Fuss %.0f/%.0f cm' % (
                      e['h_cm'], U.to_cm(fuss), U.to_cm(fuss_staerke)),
                  ox + fuss / 2.0, bot + fuss_staerke / 2.0,
                  0, 2, 2, txt_cls)

        # Fundamentmasse ausschliesslich auf der eigenen Klasse.
        dim_between((fund_vorne, fund_basis), (fund_hinten, fund_basis),
                    -line_h * 0.8,
                    'B Fund. = %s cm' % fmt_cm(U.to_cm(
                        fund_hinten - fund_vorne)), fund_bem_cls, p)
        dim_between((fund_vorne, fund_basis), (fund_vorne, fund_top),
                    -line_h * 0.8,
                    'd = %s cm' % fmt_cm(U.to_cm(fund_top - fund_basis)),
                    fund_bem_cls, p)
        dim_between((fund_vorne, fund_basis),
                    (fund_vorne, gel_original + versatz),
                    -line_h * 2.0,
                    'T = %s cm' % fmt_cm(U.to_cm(
                        gel_original + versatz - fund_basis)),
                    fund_bem_cls, p)

        # Bauteilmasse: Fusslaenge/-staerke, Wanddicke und Gesamthoehe.
        dim_between((ox, bot), (ox + fuss, bot), line_h * 0.8,
                    'Fuss = %s cm' % fmt_cm(U.to_cm(fuss)), bem_cls, p)
        dim_between((ox + fuss, bot), (ox + fuss, bot + fuss_staerke),
                    line_h * 0.8,
                    'd Fuss = %s cm' % fmt_cm(U.to_cm(fuss_staerke)),
                    bem_cls, p)
        dim_between((ox, top), (ox + dicke, top), line_h * 0.8,
                    'd Wand = %s cm' % fmt_cm(U.to_cm(dicke)), bem_cls, p)
        dim_between((ox, bot), (ox, top), -line_h * 3.0,
                    'H = %s cm' % fmt_cm(U.to_cm(top - bot)), bem_cls, p)

        gel = gel_original + versatz
        balken = U.cm(10.0)
        make_filled_poly([(ox - balken, gel - th * 0.12),
                          (ox, gel - th * 0.12),
                          (ox, gel + th * 0.12),
                          (ox - balken, gel + th * 0.12)],
                         bem_cls, (0, 0, 0), 100.0)
        make_text('UK Gel. %s' % kote_text(p, gel_original),
                  ox - balken - cw, gel, 0, 3, 2, kote_cls)
        make_text('OK Mauer %s' % kote_text(p, top_original),
                  ox - cw, top, 0, 3, 2, kote_cls)
        make_text('UK Mauer %s' % kote_text(p, e['ybot']),
                  ox - cw, bot, 0, 3, 2, kote_cls)

        if sammlung is not None:
            sammlung['schnitte'].append((name, list(NEW_OBJS[start_schnitt:])))

        start_markierung = len(NEW_OBJS)
        xs = x0 + station
        _dline(xs, y_unten - line_h * 1.5, xs, y_oben + line_h * 1.5, bem_cls)
        make_text(name, xs, y_oben + line_h * 1.7, 0, 2, 4, txt_cls)
        if pl_pts and st_tab:
            ss = (st_tab[-1] - station) if reverse else station
            q, richt = point_at_station(pl_pts, st_tab, ss)
            ux, uy = richt
            sign = 1.0 if p['seite'] == 0 else -1.0
            nx, ny = -uy * sign, ux * sign
            _dline(q[0] - nx * cw * 3.0, q[1] - ny * cw * 3.0,
                   q[0] + nx * (max_tief + cw * 3.0),
                   q[1] + ny * (max_tief + cw * 3.0), bem_cls)
            ang = math.degrees(math.atan2(ny, nx))
            if ang > 90.0:
                ang -= 180.0
            if ang < -90.0:
                ang += 180.0
            make_text(name, q[0] - nx * cw * 4.5,
                      q[1] - ny * cw * 4.5, ang, 2, 2, txt_cls)
        if sammlung is not None:
            sammlung['markierungen'].extend(NEW_OBJS[start_markierung:])
    return len(stationen)


def build_gabione(h_uk, h_ok, h_pl, p, group_name=None, pts_override=None):
    """Zeichnet die Gabionenwand in Ansicht und Aufsicht."""
    LAST_BUILD.clear()
    p['wall_id'] = p.get('wall_id') or new_wall_id('GAB')
    # Klassenpraefix: der Dialogwert gilt, sonst die Vorgabe PD-MA-GAB-
    pre = (p.get('prefix') or '').strip()
    if 'GAB' not in pre.upper():
        pre = DEFAULTS['gab_prefix']
    p['gab_prefix'] = pre
    if pts_override:
        uk_raw = list(pts_override[0])
        ok_raw = list(pts_override[1])
    else:
        uk_raw = get_vertices(h_uk)
        ok_raw = get_vertices(h_ok)
    if len(uk_raw) < 2 or len(ok_raw) < 2:
        return False, 'Unterkante oder Oberkante konnte nicht gelesen werden.'

    frame = wall_frame(vs, p)
    uk_pts = sort_by_x(frame.local_points(uk_raw))
    ok_pts = sort_by_x(frame.local_points(ok_raw))
    x0 = ok_pts[0][0]
    L_ok = ok_pts[-1][0] - ok_pts[0][0]
    L_uk = uk_pts[-1][0] - uk_pts[0][0]
    if L_ok <= U.cm(1.0):
        return False, 'Die Oberkante hat keine Ausdehnung in X-Richtung.'
    if y_at(ok_pts, x0 + L_ok / 2.0) < y_at(uk_pts, x0 + L_ok / 2.0):
        return False, ('Die zuerst gewaehlte Linie liegt hoeher als die '
                       'zweite.\nReihenfolge: 1. Unterkante, 2. Oberkante.')

    corners = []
    pl_pts, st_tab = [], []
    laengen = [('Oberkante', L_ok), ('Unterkante', L_uk)]
    pl_vorgabe = pts_override[2] if pts_override else None
    if p['aufsicht'] and (h_pl is not None or pl_vorgabe):
        pl_pts = frame.local_points(list(pl_vorgabe) if pl_vorgabe else get_vertices(h_pl))
        if len(pl_pts) >= 2:
            st_tab = station_table(pl_pts)
            laengen.append(('Aufsichtslinie', st_tab[-1]))
        else:
            pl_pts = []
    L_abw = min(v for _n, v in laengen)
    x1 = x0 + L_abw
    warnung = None
    if U.to_cm(max(v for _n, v in laengen) - L_abw) > p['toleranz']:
        warnung = ('Unterschiedliche Eingabelaengen; kuerzeste Strecke gilt: %.3f m (%s)'
                   % (U.to_m(L_abw), ', '.join('%s %.3f m' % (n, U.to_m(v))
                                               for n, v in laengen)))
    if pl_pts:
        cs = corner_list(pl_pts)
        if p['aufsicht_umkehren']:
            cs = [{'s': st_tab[-1] - c['s'], 'angle': c['angle']} for c in cs]
        corners = [c for c in cs if 1e-6 < c['s'] < L_abw - 1e-6]

    zellen, warn = gab_elemente(uk_pts, ok_pts, corners, x0, x1, p)
    if not zellen:
        return False, '\n'.join(warn) or 'Keine Gabionen berechnet.'
    ref_anchor = bezugspunkt_ankern(p, zellen)
    if pl_pts:
        setze_gabionen_eckmengen(
            zellen, pl_pts, st_tab, p, p.get('aufsicht_umkehren', False))

    vorherige_ebene = ebene_vorbereiten(p)
    text_metrics(p)
    farben = gab_klassen(p['gab_prefix'], zellen,
                         int(p.get('farb_modus', 1)),
                         p.get('farben_neu', False),
                         p.get('transparenz', 0.0),
                         p.get('gab_colors', {}),
                         p.get('fundament_farbe', DEFAULT_FUNDAMENT_FARBE))

    vs.PushAttrs()
    aktive_klasse = vs.ActiveClass()
    fehler = None
    tab_gruppen = []
    rollback_objs = []
    bez_pts = []
    del NEW_OBJS[:]
    del TEXT_BOXES[:]
    try:
        gab_ansicht(zellen, p, farben, corners)
        if pl_pts:
            gab_aufsicht(zellen, pl_pts, st_tab, p, farben,
                         p['aufsicht_umkehren'], st_tab[-1])
            if p.get('draw_3d', True):
                draw_gabione_3d(
                    zellen, pl_pts, st_tab, p, farben,
                    p['aufsicht_umkehren'])
        if p.get('zeichnungs_tabelle'):
            _th, line_h, _cw = text_metrics(p)
            fundamente = gab_fundamente(zellen, p)
            ymin = min([z['ybot'] for z in zellen] +
                       [q[1] for f in fundamente for q in f['basis_pts']])
            mauer = list(NEW_OBJS)
            rollback_objs.extend(mauer)
            del NEW_OBJS[:]
            gab_tabelle_zeichnen(zellen, p, x0, ymin - line_h * 3.0)
            tab_gruppen.append(('PD-MA-GAB-TABELLE-', list(NEW_OBJS)))
            del NEW_OBJS[:]
            NEW_OBJS.extend(mauer)
        if ref_anchor is not None:
            mauer = list(NEW_OBJS)
            rollback_objs.extend(mauer)
            del NEW_OBJS[:]
            bez_pts = draw_bezugspunkt(p, ref_anchor[0], ref_anchor[1])
            tab_gruppen.append(('PD-MA-GAB-BEZUG-', list(NEW_OBJS)))
            del NEW_OBJS[:]
            NEW_OBJS.extend(mauer)
        frame.rotate_created(vs, list(NEW_OBJS) +
                             [h for _pre, objs in tab_gruppen for h in objs])
    except Exception:
        fehler = traceback.format_exc()
    finally:
        try:
            vs.NameClass(aktive_klasse)
        except Exception:
            pass
        vs.PopAttrs()

    erzeugt = list(NEW_OBJS)
    del NEW_OBJS[:]
    if fehler:
        delete_objects(erzeugt + rollback_objs +
                       [h for _pre, objs in tab_gruppen for h in objs])
        ebene_wiederherstellen(vorherige_ebene)
        return False, 'Fehler beim Zeichnen:\n\n' + fehler

    bez_name = ''
    bez_bbox = None
    tab_names = []
    for praefix, objs in tab_gruppen:
        g = group_objects(objs)
        if g is not None:
            try:
                nm = unique_name(praefix)
                vs.SetName(g, nm)
                if 'BEZUG' in praefix:
                    bez_name = nm
                    bez_bbox = bbox_of(g)
                else:
                    tab_names.append(nm)
            except Exception:
                pass

    grp = group_objects(erzeugt)
    gname = group_name or unique_name('PD-MA-GAB-GRP-')
    data = dict((k, v) for k, v in p.items() if not str(k).startswith('_'))
    data['bauart'] = 'gabione'
    data['wall_id'] = p['wall_id']
    data['gruppe'] = gname
    data['doc'] = doc_name()
    data['doc_key'] = doc_key()
    data['schema_version'] = DATA_VERSION
    data['tab_names'] = tab_names
    data['bez_name'] = bez_name
    data['bez_bbox'] = bez_bbox
    data['bez_pts'] = frame.model_points(bez_pts) if bez_pts else []
    data['ref_y'] = p.get('ref_y', 0.0)
    data['uk_name'] = ensure_name(h_uk, 'PD-MA-GAB-UK-') if h_uk is not None else ''
    data['ok_name'] = ensure_name(h_ok, 'PD-MA-GAB-OK-') if h_ok is not None else ''
    data['pl_name'] = ensure_name(h_pl, 'PD-MA-GAB-AUF-') if h_pl is not None else ''
    data['uk_pts'] = [[q[0], q[1]] for q in uk_raw]
    data['ok_pts'] = [[q[0], q[1]] for q in ok_raw]
    data['pl_pts'] = frame.model_points(pl_pts)
    data['stand'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    if grp is not None:
        for fn, args in (('SendToBack', (grp,)), ('SetName', (grp, gname))):
            try:
                getattr(vs, fn)(*args)
            except Exception:
                pass
        attach_data(grp, data)
    else:
        for h in erzeugt:
            attach_data(h, data)
    if grp is not None and not p.get('_native_plain'):
        from PD_ToolsPD.ddvw.vw import wall_object
        grp = wall_object.convert(grp)
    if not p.get('_defer_registry') and not registry_add(data):
        delete_objects(([grp] if grp is not None else erzeugt) +
                       [get_object(name) for name in
                        list(tab_names) + ([bez_name] if bez_name else [])])
        ebene_wiederherstellen(vorherige_ebene)
        return False, ('Die Mauer wurde nicht angelegt, weil ihre Verwaltung '
                       'nicht sicher gespeichert werden konnte.')
    LAST_BUILD.update({'gruppe': grp, 'handles': [grp] if grp is not None else erzeugt,
                       'data': data,
                       'aux_names': (list(tab_names) +
                                     ([bez_name] if bez_name else []))})
    ebene_wiederherstellen(vorherige_ebene)

    csv_pfade = gab_csv(zellen, p)
    reihen = gab_summen(zellen, p)
    su = dict((schl, 0.0) for schl in reihen[0] if schl != 'b_cm')
    txt = ['Gabionenwand erzeugt.', '',
           'Ebene             : %s' % p.get('ebene_name', '?'),
           'Wandlaenge        : %.3f m' % U.to_m(L_abw),
           'Gabionen          : %d' % len(zellen),
           'Lagenhoehe        : %.2f m' % float(p.get('gab_lage', 0.5)),
           'Fundament         : %.0f cm Ueberstand auf allen Seiten, '
           'Sohle %.0f cm unter UK Gelaende' % (
               gab_fund_ueberstand_cm(p), float(p.get(
                   'gab_fund_tiefe', GAB_FUND_TIEFE_CM))), '',
           'Breite Anzahl Laenge Front sichtbar Gab.Vol Fund.Vol Gab.<UK Aushub',
           '  [cm]          [m]   [m2]    [m2]    [m3]    [m3]    [m3]   [m3]']
    for r in reihen:
        txt.append('%6g %6d %6.2f %6.2f %8.2f %7.2f %7.2f %7.2f %7.2f'
                   % (r['b_cm'], r['anzahl'], r['laenge_m'], r['front_m2'],
                      r['sicht_m2'], r['volumen_m3'],
                      r['fund_volumen_m3'], r['gab_unter_gel_m3'],
                      r['aushub_m3']))
        for schl in su:
            su[schl] = su.get(schl, 0.0) + r.get(schl, 0.0)
    txt.append('%6s %6d %6.2f %6.2f %8.2f %7.2f %7.2f %7.2f %7.2f'
               % ('SUMME', su['anzahl'], su['laenge_m'], su['front_m2'],
                  su['sicht_m2'], su['volumen_m3'],
                  su['fund_volumen_m3'], su['gab_unter_gel_m3'],
                  su['aushub_m3']))
    txt.append('')
    txt.append('Rueckseite einschl. offener Kopfflaechen: %.2f m2'
               % su['rueck_m2'])
    txt.append('Fundament: %.2f m Laenge, %.2f m2 Aufsichtsflaeche, '
               '%.2f m3 Volumen'
               % (su['fund_laenge_m'], su['fund_m2'],
                  su['fund_volumen_m3']))
    txt.append('Gabionen unter UK Gelaende: %.2f m3'
               % su['gab_unter_gel_m3'])
    txt.append('Erdaushub gesamt: %.2f m3' % su['aushub_m3'])
    if csv_pfade:
        txt += ['', 'Auswertung als CSV:', '  ' + csv_pfade[0]]
    else:
        txt += ['', 'WARNUNG: Die CSV-Auswertung konnte nicht gespeichert werden.']
    if warnung:
        txt += ['', 'HINWEIS: ' + warnung]
    if warn:
        txt += ['', 'WARNUNGEN:'] + ['  ' + w for w in warn]
    return True, '\n'.join(txt)


def build_wall(h_uk, h_ok, h_pl, p, group_name=None, pts_override=None):
    """Zeichnet Abwicklung (+ Aufsicht) und liefert (ok, meldung).
    pts_override = (uk_pts, ok_pts, pl_pts) - dann werden diese Punkte
    verwendet statt die Objekte auszulesen (schrittweise Auswahl)."""
    LAST_BUILD.clear()
    p['wall_id'] = p.get('wall_id') or new_wall_id('MW')
    if pts_override:
        uk_raw = list(pts_override[0])
        ok_raw = list(pts_override[1])
    else:
        uk_raw = get_vertices(h_uk)
        ok_raw = get_vertices(h_ok)
    if len(uk_raw) < 2 or len(ok_raw) < 2:
        return False, 'Unterkante oder Oberkante konnte nicht gelesen werden.'

    frame = wall_frame(vs, p)
    uk_pts = sort_by_x(frame.local_points(uk_raw))
    ok_pts = sort_by_x(frame.local_points(ok_raw))

    # Massgebend ist die OBERKANTE; sind Unterkante oder Aufsichtslinie
    # kuerzer, gilt die kuerzeste der drei Strecken.
    x0 = ok_pts[0][0]
    L_ok = ok_pts[-1][0] - ok_pts[0][0]
    L_uk = uk_pts[-1][0] - uk_pts[0][0]
    if L_ok <= U.cm(1.0):
        return False, 'Die Oberkante hat keine Ausdehnung in X-Richtung.'

    # Plausibilitaet: Oberkante muss ueber Unterkante liegen
    x_mitte = x0 + L_ok / 2.0
    if y_at(ok_pts, x_mitte) < y_at(uk_pts, x_mitte):
        return False, ('Die zuerst gewaehlte Linie liegt hoeher als die zweite.\n'
                       'Reihenfolge: 1. Unterkante, 2. Oberkante.')

    breaks = []            # Liste von {'s': Station, 'angle': Innenwinkel}
    pl_pts, st_tab = [], []
    laengen = [('Oberkante', L_ok), ('Unterkante', L_uk)]

    pl_vorgabe = pts_override[2] if pts_override else None
    if p['aufsicht'] and (h_pl is not None or pl_vorgabe):
        pl_pts = frame.local_points(list(pl_vorgabe) if pl_vorgabe else get_vertices(h_pl))
        if len(pl_pts) < 2:
            return False, 'Die Aufsichtslinie konnte nicht gelesen werden.'
        st_tab = station_table(pl_pts)
        laengen.append(('Aufsichtslinie', st_tab[-1]))

    L_abw = min(v for _n, v in laengen)
    x1 = x0 + L_abw
    # Jede Abweichung der Eingabelaengen ist vor der Auswertung sichtbar.
    laengen_warnung = None
    if U.to_cm(max(v for _n, v in laengen) - L_abw) > p['toleranz']:
        laengen_warnung = ('Unterschiedliche Eingabelaengen - es gilt die '
                           'kuerzeste Strecke: %.3f m (%s)'
                           % (U.to_m(L_abw),
                              ', '.join('%s %.3f m' % (n, U.to_m(v))
                                        for n, v in laengen)))

    if pl_pts:
        cs = corner_list(pl_pts)
        if p['aufsicht_umkehren']:
            cs = [{'s': st_tab[-1] - c['s'], 'angle': c['angle']} for c in cs]
        breaks = [c for c in cs if 1e-6 < c['s'] < L_abw - 1e-6]

    _dbg('9a - Elemente berechnen')
    elements, warn = compute_elements(uk_pts, ok_pts, breaks, x0, x1, p)
    if not elements:
        return False, 'Es konnten keine Elemente gebildet werden.'
    ref_anchor = bezugspunkt_ankern(p, elements)
    if pl_pts:
        setze_winkel_eckmengen(
            elements, pl_pts, st_tab, p, p.get('aufsicht_umkehren', False))

    _dbg('9a2 - Zeichenebene vorbereiten')
    vorherige_ebene = ebene_vorbereiten(p)
    text_metrics(p)              # setzt den Massstab fuer alle Beschriftungen

    _dbg('9b - %d Elemente, Klassen anlegen' % len(elements))
    colors = prepare_classes(p['prefix'], p['heights'],
                             p.get('colors', {}), p.get('farben_neu', False),
                             p.get('transparenz', 0.0),
                             int(p.get('farb_modus', 0)),
                             p.get('fundament_farbe', DEFAULT_FUNDAMENT_FARBE))
    _dbg('9c - Klassen fertig')

    vs.PushAttrs()
    active_class = vs.ActiveClass()
    zeichenfehler = None
    tab_gruppen = []
    rollback_objs = []
    bez_pts = []
    del TEXT_BOXES[:]
    del NEW_OBJS[:]
    try:
        # Bewusst OHNE BeginGroup zeichnen: innerhalb einer offenen Gruppe
        # liefert LNewObj kein gueltiges Handle, dadurch gingen Klasse und
        # Farbe der Objekte verloren. Gruppiert wird erst danach.
        _dbg('Abwicklung zeichnen')
        draw_abwicklung(elements, p, colors)
        if p['aufsicht'] and pl_pts:
            _dbg('Aufsicht zeichnen')
            draw_aufsicht(elements, pl_pts, st_tab, p, colors,
                          p['aufsicht_umkehren'],
                          [c['s'] for c in breaks], L_abw)
            if p.get('draw_3d', True):
                draw_winkel_3d(
                    elements, pl_pts, st_tab, p, colors,
                    p['aufsicht_umkehren'])
        if p['zeichnungs_tabelle']:
            _dbg('Tabelle zeichnen')
            fundamente = winkel_fundamente(elements, p)
            ymin = min([e['ybot'] for e in elements] +
                       [q[1] for f in fundamente for q in f['basis_pts']])
            _th, line_h, _cw = text_metrics(p)
            # Die Mauerobjekte zwischenspeichern, damit die Tabellen als
            # eigene, frei verschiebbare Gruppen entstehen.
            mauer_objs = list(NEW_OBJS)
            rollback_objs.extend(mauer_objs)
            del NEW_OBJS[:]
            y_tab = draw_table(elements, p, x0, ymin - line_h * 3.0)
            tab_gruppen.append(('PD-MWL-SUMMENLISTE-', list(NEW_OBJS)))
            del NEW_OBJS[:]
            if p.get('einzelliste'):
                draw_element_table(elements, p, x0, y_tab - line_h * 3.0)
                tab_gruppen.append(('PD-MWL-EINZELLISTE-', list(NEW_OBJS)))
                del NEW_OBJS[:]
            NEW_OBJS.extend(mauer_objs)

        if ref_anchor is not None:
            _dbg('Bezugshoehenpunkt zeichnen')
            mauer_objs = list(NEW_OBJS)
            rollback_objs.extend(mauer_objs)
            del NEW_OBJS[:]
            bez_pts = draw_bezugspunkt(p, ref_anchor[0], ref_anchor[1])
            tab_gruppen.append(('PD-MWL-BEZUG-', list(NEW_OBJS)))
            del NEW_OBJS[:]
            NEW_OBJS.extend(mauer_objs)
        frame.rotate_created(vs, list(NEW_OBJS) +
                             [h for _pre, objs in tab_gruppen for h in objs])
    except Exception:
        zeichenfehler = traceback.format_exc()
    finally:
        try:
            vs.NameClass(active_class)
        except Exception:
            pass
        vs.PopAttrs()

    erzeugt = list(NEW_OBJS)
    del NEW_OBJS[:]

    if zeichenfehler:
        delete_objects(erzeugt + rollback_objs +
                       [h for _pre, objs in tab_gruppen for h in objs])
        ebene_wiederherstellen(vorherige_ebene)
        return False, 'Fehler beim Zeichnen:\n\n' + zeichenfehler

    _dbg('Tabellen gruppieren')
    bez_name = ''
    bez_bbox = None
    tab_names = []
    for praefix, objs in tab_gruppen:
        g = group_objects(objs)
        if g is not None:
            nm = unique_name(praefix)
            try:
                vs.SetName(g, nm)
                if 'BEZUG' in praefix:
                    bez_name = nm
                    bez_bbox = bbox_of(g)
                else:
                    tab_names.append(nm)
            except Exception:
                pass

    _dbg('Objekte gruppieren')
    data = dict((k, v) for k, v in p.items() if not str(k).startswith('_'))
    data['wall_id'] = p['wall_id']
    data['uk_name'] = ensure_name(h_uk, 'PD-MWL-UK-') if h_uk is not None else ''
    data['ok_name'] = ensure_name(h_ok, 'PD-MWL-OK-') if h_ok is not None else ''
    data['pl_name'] = ensure_name(h_pl, 'PD-MWL-AUF-') if h_pl is not None else ''
    data['stand'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    data['uk_pts'] = [[q[0], q[1]] for q in uk_raw]
    data['ok_pts'] = [[q[0], q[1]] for q in ok_raw]
    data['pl_pts'] = frame.model_points(pl_pts)
    data['ref_y'] = p.get('ref_y', 0.0)
    data['bez_pts'] = frame.model_points(bez_pts) if bez_pts else []
    data['bez_bbox'] = bez_bbox

    grp = group_objects(erzeugt)
    gname = group_name or unique_name('PD-MWL-GRP-')
    data['gruppe'] = gname
    data['bez_name'] = bez_name
    data['doc'] = doc_name()
    data['doc_key'] = doc_key()
    data['schema_version'] = DATA_VERSION
    data['tab_names'] = tab_names
    ws_names = []
    if p.get('ws_tabelle'):
        arbeitsblaetter = [create_worksheet(elements, p)]
        if p.get('einzelliste'):
            arbeitsblaetter.append(create_element_worksheet(elements, p))
        if any(not handle_valid(ws) for ws in arbeitsblaetter):
            delete_objects(([grp] if grp is not None else erzeugt) +
                           [get_object(n) for n in
                            list(tab_names) + ([bez_name] if bez_name else [])] +
                           [ws for ws in arbeitsblaetter if handle_valid(ws)])
            ebene_wiederherstellen(vorherige_ebene)
            return False, ('Die angeforderten Vectorworks-Arbeitsblaetter '
                           'konnten nicht vollstaendig erzeugt werden.')
        for ws in arbeitsblaetter:
            try:
                nm = _gueltiger_objektname(vs.GetName(ws))
                if nm:
                    ws_names.append(nm)
            except Exception:
                pass
    data['ws_names'] = ws_names
    if grp is not None:
        for fn, args in (('SendToBack', (grp,)), ('SetName', (grp, gname))):
            try:
                getattr(vs, fn)(*args)
            except Exception:
                pass
        attach_data(grp, data)
    else:
        # Gruppieren nicht moeglich - Datensatz an jedes Objekt haengen
        for h in erzeugt:
            attach_data(h, data)
    if grp is not None and not p.get('_native_plain'):
        from PD_ToolsPD.ddvw.vw import wall_object
        grp = wall_object.convert(grp)
    # Commit only after the native replacement and all auxiliary outputs exist.
    if not p.get('_defer_registry') and not registry_add(data):
        auxiliary = list(tab_names) + list(ws_names) + ([bez_name] if bez_name else [])
        delete_objects(([grp] if grp is not None else erzeugt) +
                       [get_object(name) for name in auxiliary])
        ebene_wiederherstellen(vorherige_ebene)
        return False, ('Die Mauer wurde nicht angelegt, weil ihre Verwaltung '
                       'nicht sicher gespeichert werden konnte.')
    LAST_BUILD.update({'gruppe': grp, 'handles': [grp] if grp is not None else erzeugt,
                       'data': data,
                       'aux_names': (list(tab_names) + list(ws_names) +
                                     ([bez_name] if bez_name else []))})
    ebene_wiederherstellen(vorherige_ebene)

    csv_pfade = csv_export(elements, p)

    rows = summarize(elements, p)
    fund_aufsicht = sum(r['fund_aufsicht_m2'] for r in rows)
    fund_volumen = sum(r['fund_volumen_m3'] for r in rows)
    fund_aushub = sum(r['aushub_m3'] for r in rows)
    txt = ['Mauer erzeugt.', '',
           'Mauertyp          : %s' % STEIN_TYPEN[int(p.get('stein_typ', 0))
                                                  ].split(' (')[0],
           'Ebene             : %s' % ((p.get('ebene_name') or '?')
                                        if p.get('ebene_aktiv', True)
                                        else 'aktive Ebene'),
           'Abwicklungslaenge : %.3f m' % U.to_m(L_abw),
           'Anzahl Elemente   : %d' % len(elements),
           'davon Passstuecke : %d' % sum(1 for e in elements if e['is_pass']),
           'Eckschenkel      : %d' % sum(1 for e in elements
                                          if e.get('is_corner')),
           'Fundament         : %.0f cm Ueberstand vorne/hinten, '
           'Sohle %.0f cm unter UK Gelaende' % (
               p.get('fund_ueberstand', WINKEL_FUND_UEBERSTAND_CM),
               p.get('fund_tiefe', WINKEL_FUND_TIEFE_CM)), '',
           'Summenliste:']
    for r in rows:
        txt.append('  %-13s H %-6g B %-6.1f  x %3d   = %6.2f m'
                   % (r['typ'], r['h_cm'], r['b_cm'], r['anzahl'], r['laenge_m']))
    txt += ['', 'Fundament-Aufsichtsflaeche: %.2f m2' % fund_aufsicht,
            'Fundamentvolumen: %.2f m3' % fund_volumen,
            'Erdaushub bis UK Gelaende: %.2f m3' % fund_aushub]
    if csv_pfade:
        txt.append('')
        ziel = os.path.dirname(csv_pfade[0])
        if ziel == settings_dir():
            txt.append('Listen als CSV (Zeichnung noch nicht gesichert - '
                       'daher im Anwenderordner):')
        else:
            txt.append('Listen als CSV im Ordner der Zeichnung:')
        txt.append('  ' + ziel)
        for f in csv_pfade:
            txt.append('  - ' + os.path.basename(f))
    erwartet = 1 + (1 if p.get('einzelliste') else 0)
    if len(csv_pfade) < erwartet:
        txt.append('')
        txt.append('WARNUNG: Nicht alle angeforderten CSV-Listen konnten '
                   'gespeichert werden.')
    txt.append('')
    txt.append('Klassenfarben aus dem Katalog: %d gesetzt, %d fehlgeschlagen (%s)'
               % (CLASS_COLOR_INFO['ok'], CLASS_COLOR_INFO['fehl'],
                  ', '.join(sorted(CLASS_COLOR_INFO['wege'])) or '-'))
    if p.get('transparenz', 0) > 0 and not (OPACITY_INFO['objekt']
                                            or OPACITY_INFO['klasse']):
        txt.append('')
        txt.append('HINWEIS: Die Transparenz konnte nicht gesetzt werden.')
        txt.append('  Bitte in den Klassen %s... die Deckkraft einstellen.'
                   % p.get('winkel_prefix', p.get('prefix', 'PD-MWL-')))
    if laengen_warnung:
        warn.insert(0, laengen_warnung)
    if warn:
        txt.append('')
        txt.append('WARNUNGEN:')
        txt.extend('  ' + w for w in warn)
    return True, '\n'.join(txt)


# ---------------------------------------------------------------------------
# Aktualisieren
# ---------------------------------------------------------------------------


def collect_walls():
    """Alle Mauern dieses Werkzeugs: Liste von (Handles, Daten)."""
    gefunden = {}
    reihenfolge = []

    def cb(h):
        d = read_data(h)
        if d:
            # Alte Zeitstempel-IDs konnten bei mehreren Mauern derselben
            # Sekunde kollidieren. Der Gruppenname trennt diese Altfaelle.
            key = (d.get('wall_id') or 'ohne-id',
                   d.get('gruppe') or 'objekt-%d' % len(reihenfolge))
            if key not in gefunden:
                gefunden[key] = (d, [])
                reihenfolge.append(key)
            gefunden[key][1].append(h)

    try:
        vs.ForEachObjectInLayer(cb, 0, 0, 2)
    except Exception:
        pass
    return [(gefunden[k][1], gefunden[k][0]) for k in reihenfolge]


def zeichne_bauteil(h_uk, h_ok, h_pl, p, group_name=None, pts_override=None):
    """Weiche zwischen den Bauarten."""
    fehler = validate_params(p)
    if fehler:
        return False, 'Ungueltige Einstellungen:\n\n' + '\n'.join(fehler)
    register_prefix(p.get('prefix'))
    register_prefix(p.get('gab_prefix'))
    if int(p.get('stein_typ', 0)) == TYP_GABIONE or p.get('bauart') == 'gabione':
        return build_gabione(h_uk, h_ok, h_pl, p, group_name, pts_override)
    return build_wall(h_uk, h_ok, h_pl, p, group_name, pts_override)


UPDATE_COMMON_FIELDS = {
    'font', 'font_size', 'txt_rot', 'bemassung', 'dim_abstand',
    'transparenz', 'farben_neu', 'farb_modus', 'ref_aktiv', 'ref_hoehe',
    'ws_tabelle', 'zeichnungs_tabelle', 'aufsicht', 'aufsicht_umkehren',
    'seite', 'toleranz', 'ebene_aktiv', 'unit', 'schnitt_station',
    'fundament_farbe',
}


UPDATE_WINKEL_FIELDS = {
    'ueber_ok', 'unter_uk', 'fund_ueberstand', 'fund_tiefe',
    'winkel_fuss_staerke', 'pass_min', 'eck_schenkel', 'ecke_abstufen',
    'stufe_min', 'pass_lage', 'hoehen_mode', 'ok_abstand', 'dicke_mode',
    'dicke_frei', 'einzelliste', 'fuss_zeichnen', 'fuss_ls',
    'winkel_prefix', 'winkel_ebene_name', 'winkel_ebene_massstab',
}


# Regelbreite und Katalog unterscheiden sich zwischen armierten und
# unarmierten Winkelsteinen. Sie duerfen deshalb nur auf denselben Untertyp
# uebertragen werden; die uebrigen Winkelsteinparameter gelten fuer beide.
UPDATE_WINKEL_TYP_FIELDS = {
    'breite_mode', 'breite_frei', 'heights', 'feet', 'colors',
    'catalog_armiert', 'catalog_unarmiert',
    'catalog_armiert_custom', 'catalog_unarmiert_custom',
}


UPDATE_GABIONEN_FIELDS = {
    'gab_laenge', 'gab_lage', 'gab_einbinde', 'gab_ueber', 'gab_staffel',
    'gab_lage_min', 'gab_breiten', 'gab_fund_tiefe',
    'gab_fund_ueberstand', 'gab_prefix', 'gab_ebene_name',
    'gab_ebene_massstab', 'gab_colors', 'gab_catalog_custom',
}


UPDATE_FIELDS = (UPDATE_COMMON_FIELDS | UPDATE_WINKEL_FIELDS |
                 UPDATE_WINKEL_TYP_FIELDS | UPDATE_GABIONEN_FIELDS)


def bestands_mauertyp(data):
    """Bauart eines gespeicherten Datensatzes robust bestimmen."""
    if (data or {}).get('bauart') == 'gabione':
        return TYP_GABIONE
    try:
        typ = int((data or {}).get('stein_typ', 0))
    except Exception:
        typ = 0
    return typ if typ in (0, 1, TYP_GABIONE) else 0


def sichere_update_vorgaben(override, data=None):
    """Wirksame Dialogwerte typensicher fuer eine Bestandsmauer filtern.

    Der Mauertyp selbst wird niemals geaendert. Allgemeine Werte gelten fuer
    jede Mauer. Winkelstein- bzw. Gabionengeometrie wird nur uebernommen, wenn
    im Dialog dieselbe Bauart aktiv ist. Damit funktionieren auch Abtreppung,
    Fundamente und Aufsichtsaenderungen, ohne dass "Alle aktualisieren" einen
    gemischten Bestand versehentlich in eine andere Bauart umwandelt.
    """
    vorgaben = dict(override or {})
    ziel_typ = bestands_mauertyp(data if data is not None else vorgaben)
    try:
        dialog_typ = int(vorgaben.get('stein_typ', ziel_typ))
    except Exception:
        dialog_typ = ziel_typ

    erlaubt = set(UPDATE_COMMON_FIELDS)
    if ziel_typ == TYP_GABIONE:
        if dialog_typ == TYP_GABIONE:
            erlaubt.update(UPDATE_GABIONEN_FIELDS)
    elif dialog_typ in (0, 1):
        erlaubt.update(UPDATE_WINKEL_FIELDS)
        if dialog_typ == ziel_typ:
            erlaubt.update(UPDATE_WINKEL_TYP_FIELDS)

    return dict((k, v) for k, v in vorgaben.items() if k in erlaubt)


def update_parameter_aktivieren(p, data, aktualisiert):
    """Aktive Praefix-/Ebenenwerte und abgeleitete Masse konsistent setzen."""
    typ = bestands_mauertyp(data)
    p['stein_typ'] = typ
    if typ == TYP_GABIONE:
        p['bauart'] = 'gabione'
        if 'gab_prefix' in aktualisiert or 'gab_prefix' in data:
            p['prefix'] = p.get('gab_prefix') or DEFAULTS['gab_prefix']
        if ('gab_ebene_name' in aktualisiert or
                'gab_ebene_name' in data):
            p['ebene_name'] = (p.get('gab_ebene_name') or
                               DEFAULTS['gab_ebene_name'])
        else:
            p['ebene_name'] = (data.get('ebene_name') or
                               p.get('ebene_name') or
                               DEFAULTS['gab_ebene_name'])
        if ('gab_ebene_massstab' in aktualisiert or
                'gab_ebene_massstab' in data):
            p['ebene_massstab'] = float(p.get(
                'gab_ebene_massstab', DEFAULTS['gab_ebene_massstab']))
        else:
            p['ebene_massstab'] = float(data.get(
                'ebene_massstab', p.get(
                    'ebene_massstab', DEFAULTS['gab_ebene_massstab'])))
    else:
        # Ein eventuell fehlerhafter alter Gabionenmarker darf den durch den
        # Datensatz festgestellten Winkelsteintyp nicht wieder ueberschreiben.
        p.pop('bauart', None)
        if 'winkel_prefix' in aktualisiert or 'winkel_prefix' in data:
            p['prefix'] = p.get('winkel_prefix') or DEFAULTS['winkel_prefix']
        if ('winkel_ebene_name' in aktualisiert or
                'winkel_ebene_name' in data):
            p['ebene_name'] = (p.get('winkel_ebene_name') or
                               DEFAULTS['winkel_ebene_name'])
        else:
            p['ebene_name'] = (data.get('ebene_name') or
                               p.get('ebene_name') or
                               DEFAULTS['winkel_ebene_name'])
        if ('winkel_ebene_massstab' in aktualisiert or
                'winkel_ebene_massstab' in data):
            p['ebene_massstab'] = float(p.get(
                'winkel_ebene_massstab', DEFAULTS['winkel_ebene_massstab']))
        else:
            p['ebene_massstab'] = float(data.get(
                'ebene_massstab', p.get(
                    'ebene_massstab', DEFAULTS['winkel_ebene_massstab'])))
        if any(k in aktualisiert for k in ('breite_mode', 'breite_frei')):
            p.pop('breite_cm', None)
        if any(k in aktualisiert for k in ('dicke_mode', 'dicke_frei')):
            p.pop('dicke_cm', None)
    derive_params(p)
    return p


def verwaltete_hilfsnamen(data):
    """Alle gespeicherten Tabellen-/Bezugspunktnamen einer Mauer.

    Aeltere Datensaetze an der Zeichnungsgruppe koennen unvollstaendig sein,
    obwohl die Merkliste bereits die Namen enthaelt. Beide Quellen werden
    deshalb zusammengefuehrt, ohne Eintraege anderer Mauern anzutasten.
    """
    daten = [data]
    wall_id = data.get('wall_id')
    gruppe = data.get('gruppe')
    stabile_id = str(wall_id or '').startswith(('MW-', 'GAB-'))
    for eintrag in load_registry():
        if not daten_gehoeren_zum_dokument(eintrag):
            continue
        # Sekundenbasierte Alt-IDs konnten kollidieren; nur die neuen UUID-IDs
        # duerfen unabhaengig vom Gruppennamen als Identitaet dienen.
        gleiche_id = bool(stabile_id and eintrag.get('wall_id') == wall_id)
        gleiche_gruppe = bool(gruppe and eintrag.get('gruppe') == gruppe)
        if gleiche_id or gleiche_gruppe:
            daten.append(eintrag)
    namen = []
    for d in daten:
        kandidaten = ([d.get('bez_name', '')] + list(d.get('tab_names') or []) +
                      list(d.get('ws_names') or []))
        for name in kandidaten:
            name = _gueltiger_objektname(name)
            if name and name not in namen:
                namen.append(name)
    return namen


def rebuild(handles, data, override=None):
    from PD_ToolsPD.ddvw.vw import wall_object
    native = len(handles) == 1 and wall_object.is_wall(handles[0])
    p = dict(DEFAULTS)
    p.update(data)
    # Pre-1.9.2 walls were constructed along model axes. Never reinterpret
    # their profiles merely because the view has since been rotated.
    p.setdefault('plan_angle_deg', 0.0)
    frame = PlanFrame(p['plan_angle_deg'])
    aktualisiert = sichere_update_vorgaben(override, data)
    p.update(aktualisiert)
    update_parameter_aktivieren(p, data, aktualisiert)
    U.set(p.get('unit', 'm'))
    def punkte(name, gespeicherte):
        """Liefert (Handle, Punktliste).
        Erst ueber den Objektnamen, dann ueber die gespeicherte Geometrie.
        Laesst sich das Objekt gar nicht mehr aufloesen, werden die beim
        Zeichnen gespeicherten Punkte verwendet - damit funktioniert z. B.
        das Aendern der Bezugshoehe auch dann noch.
        """
        gespeicherte = [(q[0], q[1]) for q in (gespeicherte or [])]
        # Erst ueber die Geometrie (immer gueltige Handles), dann ueber
        # den Namen - so entstehen keine Zugriffe auf NIL-Handles.
        h = find_by_pts(gespeicherte) if gespeicherte else None
        if h is None:
            h = get_object(name)
            if h is not None and not sane_pts(get_vertices(h)):
                h = None
        if h is not None:
            pts = [(q[0], q[1]) for q in get_vertices(h)]
            if sane_pts(pts):
                return h, pts
        return None, gespeicherte

    h_uk, uk_neu = punkte(p.get('uk_name', ''), p.get('uk_pts'))
    h_ok, ok_neu = punkte(p.get('ok_name', ''), p.get('ok_pts'))
    h_pl, pl_neu = punkte(p.get('pl_name', ''), p.get('pl_pts'))

    # Bezugshoehenpunkt: wurde die Kote in der Zeichnung verschoben, gilt
    # ihre neue Hoehe als Bezugsebene. Der Punkt liegt in einer eigenen
    # Gruppe - gemessen wird deshalb die Verschiebung des Gruppenrahmens.
    h_bez = get_object(p.get('bez_name', ''))
    if h_bez is not None:
        jetzt = bbox_of(h_bez)
        frueher = p.get('bez_bbox')
        if jetzt and frueher and len(frueher) == 4:
            _dx, dy = frame.local((jetzt[0] - float(frueher[0]),
                                   jetzt[1] - float(frueher[1])))
            if abs(dy) > 1e-9:
                p['ref_y'] = p.get('ref_y', 0.0) + dy
        elif jetzt and not frueher:
            # Aeltere Mauer ohne gespeicherte Lage: Punkte der Bezugslinie
            alt_bez = [(q[0], q[1]) for q in (p.get('bez_pts') or [])]
            if alt_bez:
                p['ref_y'] = p.get('ref_y', 0.0)

    # Vor dem Neuaufbau die gespeicherte Grundgeometrie pruefen.
    if not sane_pts(uk_neu) or not sane_pts(ok_neu):
        return False, ('Fuer die Mauer %s sind weder die Bezugslinien noch '
                       'gespeicherte Punkte verwendbar - nichts geaendert.'
                       % (p.get('gruppe') or p.get('wall_id') or '?'))
    ok_test = sort_by_x(frame.local_points(ok_neu))
    if (ok_test[-1][0] - ok_test[0][0]) <= U.cm(1.0):
        return False, ('Die Oberkante der Mauer %s hat keine Ausdehnung in '
                       'X-Richtung - nichts geaendert.'
                       % (p.get('gruppe') or p.get('wall_id') or '?'))

    if not handles:
        if not vs.YNDialog(
                'Die vorhandene Zeichnung der Mauer %s wurde nicht gefunden.\n\n'
                'Mauer trotzdem neu zeichnen? Die alte Zeichnung muss dann von '
                'Hand geloescht werden.' % (p.get('gruppe') or '?')):
            return False, 'Uebersprungen - alte Zeichnung nicht gefunden.'

    name = ''
    for h in handles:
        if not name:
            try:
                name = vs.GetName(h) or ''
            except Exception:
                name = ''
    zielname = name or p.get('gruppe') or unique_name('PD-MW-GRP-')
    temp_name = unique_name('PD-MW-NEUAUFBAU-')
    p['_defer_registry'] = True
    p['_native_plain'] = native
    ok, meldung = zeichne_bauteil(
        h_uk, h_ok, h_pl, p, group_name=temp_name,
        pts_override=(uk_neu, ok_neu, pl_neu or None))
    if not ok:
        return False, ('Neuaufbau fehlgeschlagen; die vorhandene Mauer blieb '
                       'unveraendert.\n' + meldung)

    neu = dict(LAST_BUILD)
    neue_handles = list(neu.get('handles') or [])
    neue_daten = migrate_data(neu.get('data'))
    if not neue_handles or not neue_daten:
        delete_objects(neue_handles)
        for nm in neu.get('aux_names') or []:
            delete_objects([get_object(nm)])
        return False, ('Der Neuaufbau lieferte keine verwaltbaren Objekte; '
                       'die vorhandene Mauer blieb unveraendert.')

    if native:
        neue_daten['gruppe'] = zielname
        neue_daten['wall_id'] = p['wall_id']
        try:
            wall_object.replace_built(
                handles[0], neu['gruppe'], neue_daten,
                commit=lambda: registry_add(neue_daten))
        except Exception:
            delete_objects(neue_handles)
            for nm in neu.get('aux_names') or []:
                delete_objects([get_object(nm)])
            raise
        for nm in verwaltete_hilfsnamen(p):
            delete_objects([get_object(nm)])
        LAST_BUILD.update(gruppe=handles[0], handles=list(handles), data=neue_daten)
        return True, 'Mauer sicher aktualisiert.\n' + meldung

    # Erst jetzt ist der Ersatz vollstaendig vorhanden. Alte Haupt- und
    # Hilfsgruppen duerfen gefahrlos entfernt werden.
    delete_objects(handles)
    for nm in verwaltete_hilfsnamen(p):
        delete_objects([get_object(nm)])

    neue_gruppe = neu.get('gruppe')
    if neue_gruppe is not None:
        try:
            vs.SetName(neue_gruppe, zielname)
            zielname = vs.GetName(neue_gruppe) or zielname
        except Exception:
            try:
                zielname = vs.GetName(neue_gruppe) or temp_name
            except Exception:
                zielname = temp_name
    neue_daten['gruppe'] = zielname
    neue_daten['wall_id'] = p.get('wall_id') or neue_daten.get('wall_id')
    neue_daten['doc'] = doc_name()
    neue_daten['doc_key'] = doc_key()
    neue_daten['schema_version'] = DATA_VERSION
    for h in neue_handles:
        attach_data(h, neue_daten)
    registry_add(neue_daten)
    LAST_BUILD['data'] = neue_daten
    return True, 'Mauer sicher aktualisiert.\n' + meldung


def _name_of(h):
    try:
        return vs.GetName(h) or ''
    except Exception:
        return ''


def selected_any():
    """Alle ausgewaehlten Objekte - auch Gruppen und andere Typen."""
    out = []

    def cb(h):
        try:
            if vs.Selected(h):
                out.append(h)
        except Exception:
            pass

    try:
        vs.ForEachObjectInLayer(cb, 0, 0, 2)
    except Exception:
        pass
    return out


def walls_from_registry(sel_alle, sel_pts):
    """Mauern aus der Merkliste, die zur Auswahl passen:
    ueber den Gruppennamen oder ueber eine der Bezugslinien."""
    namen = set()
    for h in sel_alle:
        try:
            n = vs.GetName(h)
            if n:
                namen.add(n)
        except Exception:
            pass

    treffer = []
    for d in load_registry():
        if not daten_gehoeren_zum_dokument(d):
            continue                      # Eintrag gehoert zu einem anderen Dokument
        passt = d.get('gruppe') in namen
        if not passt:
            for schl in ('uk_name', 'ok_name', 'pl_name', 'bez_name'):
                if d.get(schl) and d[schl] in namen:
                    passt = True
                    break
        if not passt:
            for schl in ('uk_pts', 'ok_pts', 'pl_pts', 'bez_pts'):
                ziel = [(q[0], q[1]) for q in (d.get(schl) or [])]
                if ziel and any(pts_equal(sp, ziel) for sp in sel_pts):
                    passt = True
                    break
        if passt:
            treffer.append(d)
    return treffer


def handles_der_mauer(d, sel_alle=None):
    """Hauptgruppe einer Mauer ausschliesslich ueber ihren Namen."""
    name = d.get('gruppe', '')
    for h in (sel_alle or []):
        try:
            if name and vs.GetName(h) == name:
                return [h]
        except Exception:
            pass
    h = get_object(name)
    if h is not None:
        return [h]
    return []


def mauer_objektschluessel(handles, data):
    """Identitaet der tatsaechlich vorhandenen Hauptgruppe fuer Updates."""
    for h in handles or []:
        name = _gueltiger_objektname(_name_of(h))
        if name:
            return ('gruppe', name)
    name = _gueltiger_objektname(data.get('gruppe'))
    if name:
        return ('gruppe', name)
    return ('daten', data.get('wall_id'))


def action_update_selection(override):
    """Aktualisiert die Mauer(n), deren Gruppe ODER deren Referenzlinie
    (Unterkante, Oberkante, Aufsichtslinie) ausgewaehlt ist."""
    sel = selected_objects()
    sel_pts = [get_vertices(h) for h in sel]

    def ist_gewaehlt(name, pts):
        h = get_object(name)
        if h is not None:
            try:
                if vs.Selected(h):
                    return True
            except Exception:
                pass
        if pts:
            ziel = [(q[0], q[1]) for q in pts]
            for sp in sel_pts:
                if pts_equal(sp, ziel):
                    return True
        return False

    sel_alle = selected_any()
    walls = []
    gesehen = set()
    verwendete_objekte = set()

    def mauer_schluessel(d):
        return (d.get('wall_id'), d.get('gruppe'))
    for handles, d in collect_walls():
        treffer = False
        try:
            treffer = any(vs.Selected(h) for h in handles)
        except Exception:
            treffer = False
        if not treffer:
            treffer = (ist_gewaehlt(d.get('uk_name'), d.get('uk_pts'))
                       or ist_gewaehlt(d.get('ok_name'), d.get('ok_pts'))
                       or ist_gewaehlt(d.get('pl_name'), d.get('pl_pts'))
                       or ist_gewaehlt(d.get('bez_name'), d.get('bez_pts')))
        if treffer:
            walls.append((handles, d))
            gesehen.add(mauer_schluessel(d))
            verwendete_objekte.add(mauer_objektschluessel(handles, d))

    # Nur wenn keine ausgewaehlte Mauergruppe mit Datensatz gefunden wurde,
    # ueber ihre Bezugslinie in der Merkliste suchen. So kann eine ausgewaehlte
    # Gruppe niemals fuer mehrere historische Registry-Eintraege wiederverwendet
    # und dadurch mehrfach uebereinander neu aufgebaut werden.
    if not walls:
        for d in walls_from_registry(sel_alle, sel_pts):
            if mauer_schluessel(d) in gesehen:
                continue
            hs = handles_der_mauer(d)
            objekt_schluessel = mauer_objektschluessel(hs, d)
            if hs and objekt_schluessel not in verwendete_objekte:
                walls.append((hs, d))
                gesehen.add(mauer_schluessel(d))
                verwendete_objekte.add(objekt_schluessel)

    if not walls:
        merk = [d for d in load_registry()
                if daten_gehoeren_zum_dokument(d)]
        vs.AlrtDialog(
            'Es wurde keine Mauer zum Aktualisieren gefunden.\n\n'
            'Bitte die Mauergruppe ODER eine ihrer Bezugslinien '
            '(Unterkante, Oberkante, Aufsichtslinie) auswaehlen und den '
            'Befehl erneut aufrufen.\n\n'
            'Diagnose:\n'
            '  ausgewaehlte Objekte gesamt : %d\n'
            '  davon Linien                : %d\n'
            '  Linien im Dokument gesamt   : %s\n'
            '  Suchwege                    : %s\n'
            '  Mauern in der Merkliste     : %d\n'
            '  Namen der Auswahl           : %s'
            % (len(sel_alle), len(sel), SCAN_INFO.get('objekte', '?'),
               SCAN_INFO.get('quelle', '-'), len(merk),
               ', '.join(n for n in (_name_of(h) for h in sel_alle) if n) or '-'))
        return
    hinweis = ''
    if set(override or {}) == {'ref_aktiv', 'ref_hoehe'}:
        hinweis = ('Bezugshoehe auf %.3f m gesetzt.\n\n'
                   % override.get('ref_hoehe', 0.0))
    msgs = []
    for handles, d in walls:
        ok, m = rebuild(handles, d, override)
        msgs.append(('OK: ' if ok else 'FEHLER: ') + m.split('\n')[0])
    vs.AlrtDialog(hinweis + 'Aktualisierung abgeschlossen.\n\n' + '\n'.join(msgs))


def registry_cleanup():
    """Nur Doppeleintraege derselben Mauergruppe entfernen (den neuesten
    behalten). Eintraege werden NICHT geloescht, bloss weil sich die Gruppe
    gerade nicht ueber ihren Namen finden laesst - sonst waere die Mauer
    dauerhaft nicht mehr aktualisierbar."""
    liste = load_registry()
    gesehen, behalten = set(), []
    for d in reversed(liste):
        schl = (d.get('doc_key') or d.get('doc', ''), d.get('gruppe', ''))
        if schl[1] and schl in gesehen:
            continue
        gesehen.add(schl)
        behalten.append(d)
    behalten.reverse()
    if len(behalten) != len(liste):
        save_registry(behalten)
    return len(liste) - len(behalten)


def action_gab_schnitte(p, variante=0):
    """Systemschnitte durch eine bestehende Gabionenwand.
    variante 0 = eine Station, 1 = bei jedem Bauweisenwechsel.
    """
    sel_alle = selected_any()
    sel_pts = [get_vertices(h) for h in selected_objects()]
    treffer = [d for d in walls_from_registry(sel_alle, sel_pts)
               if d.get('bauart') == 'gabione']
    if not treffer:
        vs.AlrtDialog('Bitte zuerst eine Gabionenwand auswaehlen '
                      '(die Wand selbst oder eine ihrer Bezugslinien).')
        return

    d = dict(DEFAULTS)
    d.update(treffer[0])
    d['schnitt_station'] = p.get('schnitt_station', 5.0)
    d['gab_fund_tiefe'] = p.get(
        'gab_fund_tiefe', d.get('gab_fund_tiefe', GAB_FUND_TIEFE_CM))
    d['gab_fund_ueberstand'] = p.get(
        'gab_fund_ueberstand', d.get(
            'gab_fund_ueberstand', GAB_FUND_UEBERSTAND_CM))
    d['ref_aktiv'] = p.get('ref_aktiv', d.get('ref_aktiv'))
    derive_params(d)
    U.set(d.get('unit', 'm'))
    d['gab_prefix'] = d.get('gab_prefix') or DEFAULTS['gab_prefix']

    frame = PlanFrame(d.get('plan_angle_deg', 0.0))
    uk_pts = sort_by_x(frame.local_points(d.get('uk_pts') or []))
    ok_pts = sort_by_x(frame.local_points(d.get('ok_pts') or []))
    pl_pts = frame.local_points(d.get('pl_pts') or [])
    if len(uk_pts) < 2 or len(ok_pts) < 2:
        vs.AlrtDialog('Die Bezugslinien der Gabionenwand sind nicht lesbar.')
        return
    x0 = ok_pts[0][0]
    L_ok = ok_pts[-1][0] - x0
    L_uk = uk_pts[-1][0] - uk_pts[0][0]
    st_tab = station_table(pl_pts) if len(pl_pts) >= 2 else []
    laengen = [L_ok, L_uk] + ([st_tab[-1]] if st_tab else [])
    L_abw = min(laengen)
    corners = []
    if st_tab:
        cs = corner_list(pl_pts)
        if d.get('aufsicht_umkehren'):
            cs = [{'s': st_tab[-1] - c['s'], 'angle': c['angle']} for c in cs]
        corners = [c for c in cs if 1e-6 < c['s'] < L_abw - 1e-6]

    zellen, warn = gab_elemente(uk_pts, ok_pts, corners, x0, x0 + L_abw, d)
    if not zellen:
        vs.AlrtDialog('Aus der Gabionenwand liessen sich keine Schnitte '
                      'ableiten.')
        return
    erforderliche_tiefe = max(
        U.to_cm(y - z['ybot']) + 10.0
        for z in zellen for _x, y in (z.get('gel_uk_pts') or [
            (z['x0'], z.get('gel_uk', z['ybot']))]))
    if float(d.get('gab_fund_tiefe', 0.0)) + 1e-9 < erforderliche_tiefe:
        vs.AlrtDialog(
            'Die gewaehlte Fundamenttiefe ist fuer diese Gabionenwand zu '
            'gering.\n\nMindestens %.0f cm unter UK Gelaende sind '
            'erforderlich (10 cm Fundament unter der tiefsten Gabione).'
            % erforderliche_tiefe)
        return

    vorherige_ebene = ebene_vorbereiten(d)
    text_metrics(d)
    farben = gab_klassen(d['gab_prefix'], zellen,
                         int(d.get('farb_modus', 1)), False,
                         d.get('transparenz', 0.0),
                         d.get('gab_colors', {}),
                         d.get('fundament_farbe', DEFAULT_FUNDAMENT_FARBE))
    vs.PushAttrs()
    del NEW_OBJS[:]
    del TEXT_BOXES[:]
    anzahl = 0
    start_nr = naechste_gab_schnittnummer()
    sammlung = {'schnitte': [], 'markierungen': []}
    fehler = None
    try:
        y_unten = min(
            [z['ybot'] for z in zellen] +
            [q[1] - U.cm(float(d.get(
                'gab_fund_tiefe', GAB_FUND_TIEFE_CM)))
             for z in zellen for q in z.get('gel_uk_pts', [])] +
            [z['ybot'] - U.cm(10.0) for z in zellen])
        _th, line_h, _cw = text_metrics(d)
        y_tab = y_unten - line_h * (4.0 + len(gab_summen(zellen, d)) + 6.0)
        anzahl = gab_schnitte(zellen, d, x0, L_abw, pl_pts, st_tab,
                              bool(d.get('aufsicht_umkehren')), y_tab,
                              variante, farben, start_nr, sammlung)
        frame.rotate_created(vs, NEW_OBJS)
    except Exception:
        fehler = traceback.format_exc()
    finally:
        vs.PopAttrs()
    erzeugt = list(NEW_OBJS)
    del NEW_OBJS[:]
    if fehler:
        for h in erzeugt:
            try:
                vs.DelObject(h)
            except Exception:
                pass
        ebene_wiederherstellen(vorherige_ebene)
        vs.AlrtDialog('Fehler beim Zeichnen der Schnitte:\n\n' + fehler)
        return
    gruppen = []
    for name, objekte in sammlung['schnitte']:
        g = group_objects(objekte)
        if g is None:
            continue
        try:
            vs.SetName(g, unique_name('%sSCHNITT-%s-' %
                                      (d['gab_prefix'], name)))
        except Exception:
            pass
        gruppen.append(g)
    if sammlung['markierungen']:
        g_mark = group_objects(sammlung['markierungen'])
        if g_mark is not None:
            try:
                vs.SetName(g_mark, unique_name(
                    d['gab_prefix'] + 'SCHNITTMARKIERUNGEN-'))
            except Exception:
                pass
    if not gruppen and erzeugt:
        # Rueckfall fuer Installationen ohne verwertbare Einzelhandles.
        g = group_objects(erzeugt)
        if g is not None:
            try:
                vs.SetName(g, unique_name('PD-MA-GAB-SCHNITTE-'))
            except Exception:
                pass
    try:
        vs.ReDrawAll()
    except Exception:
        pass
    ebene_wiederherstellen(vorherige_ebene)
    if variante == 0:
        info = 'Einzelschnitt bei Station %.2f m' % float(
            d.get('schnitt_station', 0.0))
    else:
        info = 'Systemschnitte bei jedem Wechsel der Gabionenbauweise, '\
               'jeweils mittig'
    vs.AlrtDialog('%d Schnitt(e) gezeichnet - %s.\n\n'
                  'Die Schnitte stehen unterhalb der Tabellen und liegen '
                  'jeweils in einer eigenen, verschiebbaren Gruppe. Die '
                  'Schnittmarkierungen in Ansicht und Aufsicht bleiben '
                  'davon unabhaengig. Bezeichnung ab S%d.' %
                  (anzahl, info, start_nr))


def action_winkel_schnitte(p, variante=0):
    """Systemschnitte durch eine bestehende Winkelsteinwand."""
    sel_alle = selected_any()
    sel_pts = [get_vertices(h) for h in selected_objects()]
    treffer = [d for d in walls_from_registry(sel_alle, sel_pts)
               if d.get('bauart') != 'gabione' and
               int(d.get('stein_typ', 0)) != TYP_GABIONE]
    if not treffer:
        vs.AlrtDialog('Bitte zuerst eine Winkelsteinwand auswaehlen '
                      '(die Wand selbst oder eine ihrer Bezugslinien).')
        return

    d = dict(DEFAULTS)
    d.update(treffer[0])
    d['schnitt_station'] = p.get('schnitt_station', 5.0)
    d['winkel_fuss_staerke'] = p.get(
        'winkel_fuss_staerke', d.get('winkel_fuss_staerke', 15.0))
    d['ref_aktiv'] = p.get('ref_aktiv', d.get('ref_aktiv'))
    derive_params(d)
    U.set(d.get('unit', 'm'))
    d['prefix'] = d.get('prefix') or DEFAULTS['winkel_prefix']
    if not d.get('feet'):
        katalog = load_catalog(int(d.get('stein_typ', 0)), d)
        d['feet'] = dict((str(int(round(h))), float(f))
                         for h, f, _c, _b in katalog)
        d['colors'] = dict((str(int(round(h))), c)
                           for h, _f, c, _b in katalog)
        d['heights'] = [h for h, _f, _c, _b in katalog]

    frame = PlanFrame(d.get('plan_angle_deg', 0.0))
    uk_pts = sort_by_x(frame.local_points(d.get('uk_pts') or []))
    ok_pts = sort_by_x(frame.local_points(d.get('ok_pts') or []))
    pl_pts = frame.local_points(d.get('pl_pts') or [])
    if len(uk_pts) < 2 or len(ok_pts) < 2:
        vs.AlrtDialog('Die Bezugslinien der Winkelsteinwand sind nicht lesbar.')
        return
    x0 = ok_pts[0][0]
    st_tab = station_table(pl_pts) if len(pl_pts) >= 2 else []
    laengen = [ok_pts[-1][0] - x0, uk_pts[-1][0] - uk_pts[0][0]]
    if st_tab:
        laengen.append(st_tab[-1])
    L_abw = min(laengen)
    breaks = []
    if st_tab:
        cs = corner_list(pl_pts)
        if d.get('aufsicht_umkehren'):
            cs = [{'s': st_tab[-1] - c['s'], 'angle': c['angle']} for c in cs]
        breaks = [c for c in cs if 1e-6 < c['s'] < L_abw - 1e-6]
    elements, warn = compute_elements(
        uk_pts, ok_pts, breaks, x0, x0 + L_abw, d)
    if not elements:
        vs.AlrtDialog('Aus der Winkelsteinwand liessen sich keine Schnitte '
                      'ableiten.')
        return
    kleinste_hoehe = min(float(e.get('h_cm', 0.0)) for e in elements)
    fuss_staerke = float(d.get('winkel_fuss_staerke', 15.0))
    if fuss_staerke >= kleinste_hoehe - 1e-9:
        vs.AlrtDialog(
            'Die Staerke des Winkelsteinfusses (%.0f cm) muss kleiner als '
            'die kleinste im Schnitt vorkommende Steinhoehe (%.0f cm) sein.'
            % (fuss_staerke, kleinste_hoehe))
        return

    vorherige_ebene = ebene_vorbereiten(d)
    text_metrics(d)
    farben = prepare_classes(
        d['prefix'], d['heights'], d.get('colors', {}), False,
        d.get('transparenz', 0.0), int(d.get('farb_modus', 0)),
        d.get('fundament_farbe', DEFAULT_FUNDAMENT_FARBE))
    vs.PushAttrs()
    del NEW_OBJS[:]
    del TEXT_BOXES[:]
    start_nr = naechste_gab_schnittnummer()
    sammlung = {'schnitte': [], 'markierungen': []}
    anzahl, fehler = 0, None
    try:
        fundamente = winkel_fundamente(elements, d)
        y_unten = min(q[1] for f in fundamente for q in f['basis_pts'])
        _th, line_h, _cw = text_metrics(d)
        y_tab = y_unten - line_h * (4.0 + len(summarize(elements, d)) + 6.0)
        anzahl = winkel_schnitte(
            elements, d, x0, L_abw, pl_pts, st_tab,
            bool(d.get('aufsicht_umkehren')), y_tab, variante, farben,
            start_nr, sammlung)
        frame.rotate_created(vs, NEW_OBJS)
    except Exception:
        fehler = traceback.format_exc()
    finally:
        vs.PopAttrs()
    erzeugt = list(NEW_OBJS)
    del NEW_OBJS[:]
    if fehler:
        delete_objects(erzeugt)
        ebene_wiederherstellen(vorherige_ebene)
        vs.AlrtDialog('Fehler beim Zeichnen der Winkelsteinschnitte:\n\n' +
                      fehler)
        return

    gruppen = []
    for name, objekte in sammlung['schnitte']:
        g = group_objects(objekte)
        if g is None:
            continue
        try:
            vs.SetName(g, unique_name('%sSCHNITT-%s-' % (d['prefix'], name)))
        except Exception:
            pass
        gruppen.append(g)
    if sammlung['markierungen']:
        g_mark = group_objects(sammlung['markierungen'])
        if g_mark is not None:
            try:
                vs.SetName(g_mark, unique_name(
                    d['prefix'] + 'SCHNITTMARKIERUNGEN-'))
            except Exception:
                pass
    if not gruppen and erzeugt:
        g = group_objects(erzeugt)
        if g is not None:
            try:
                vs.SetName(g, unique_name(d['prefix'] + 'SCHNITTE-'))
            except Exception:
                pass
    try:
        vs.ReDrawAll()
    except Exception:
        pass
    ebene_wiederherstellen(vorherige_ebene)
    info = (('Einzelschnitt bei Station %.2f m' % float(
        d.get('schnitt_station', 0.0))) if variante == 0 else
        'Systemschnitte bei jedem Wechsel der Winkelsteinbauweise, jeweils mittig')
    meldung = ('%d Schnitt(e) gezeichnet - %s.\n\n'
               'Fussstaerke: %.0f cm. Jeder Schnitt liegt in einer eigenen '
               'verschiebbaren Gruppe; die Markierungen bleiben unabhaengig. '
               'Bezeichnung ab S%d.' % (
                   anzahl, info, float(d.get('winkel_fuss_staerke', 15.0)),
                   start_nr))
    if warn:
        meldung += '\n\nHinweise:\n' + '\n'.join(warn)
    vs.AlrtDialog(meldung)


def action_update_all(override):
    walls = collect_walls()
    bekannt = set(mauer_objektschluessel(hs, d) for hs, d in walls)
    for d in load_registry():
        if not daten_gehoeren_zum_dokument(d):
            continue
        hs = handles_der_mauer(d)
        schluessel = mauer_objektschluessel(hs, d)
        if hs and schluessel not in bekannt:
            walls.append((hs, d))
            bekannt.add(schluessel)
    if not walls:
        vs.AlrtDialog('Im Dokument wurde keine Mauer dieses Werkzeugs gefunden.')
        return
    n_ok, n_err, errs = 0, 0, []
    for handles, d in walls:
        ok, m = rebuild(handles, d, override)
        if ok:
            n_ok += 1
        else:
            n_err += 1
            errs.append(m.split('\n')[0])
    txt = 'Aktualisiert: %d\nFehler: %d' % (n_ok, n_err)
    if errs:
        txt += '\n\n' + '\n'.join(errs)
    vs.AlrtDialog(txt)


# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------


def derive_params(p):
    """Abgeleitete Masse ergaenzen, falls sie fehlen (alte Datensaetze)."""
    if 'breite_cm' not in p:
        p['breite_cm'] = {0: 50.0, 1: 100.0}.get(p.get('breite_mode', 0),
                                                 p.get('breite_frei', 75.0))
    if 'dicke_cm' not in p:
        p['dicke_cm'] = {0: 10.0, 1: 12.0, 2: 15.0, 3: 20.0}.get(
            p.get('dicke_mode', 2), p.get('dicke_frei', 18.0))
    p.setdefault('fund_ueberstand', WINKEL_FUND_UEBERSTAND_CM)
    p.setdefault('fund_tiefe', WINKEL_FUND_TIEFE_CM)
    p.setdefault('gab_fund_tiefe', GAB_FUND_TIEFE_CM)
    p.setdefault('gab_fund_ueberstand', GAB_FUND_UEBERSTAND_CM)
    p.setdefault('winkel_fuss_staerke', 15.0)
    return p


def validate_params(p):
    """Feldbezogene Plausibilitaetspruefung vor Zeichnen und Aktualisieren."""
    fehler = []

    def zahl(key, titel, groesser_null=False, nicht_negativ=False):
        try:
            wert = float(p.get(key, 0.0))
        except Exception:
            fehler.append('%s ist keine gueltige Zahl.' % titel)
            return 0.0
        if not math.isfinite(wert):
            fehler.append('%s ist keine endliche Zahl.' % titel)
        elif groesser_null and wert <= 0:
            fehler.append('%s muss groesser als 0 sein.' % titel)
        elif nicht_negativ and wert < 0:
            fehler.append('%s darf nicht negativ sein.' % titel)
        return wert

    zahl('ebene_massstab', 'Der Ebenenmassstab', groesser_null=True)
    zahl('dim_abstand', 'Der Bemassungsabstand', nicht_negativ=True)
    zahl('toleranz', 'Die Laengentoleranz', nicht_negativ=True)
    typ = int(p.get('stein_typ', 0))
    if typ == TYP_GABIONE:
        zahl('gab_laenge', 'Die Regellaenge der Gabione', groesser_null=True)
        lage = zahl('gab_lage', 'Die Hoehe der Gabionenlage', groesser_null=True)
        einbinde = zahl('gab_einbinde', 'Die Einbindetiefe',
                        nicht_negativ=True)
        zahl('gab_ueber', 'Der Gabionenueberstand', nicht_negativ=True)
        minimum = zahl('gab_lage_min', 'Die Mindesthoehe der untersten Lage',
                       nicht_negativ=True)
        gab_fund = zahl('gab_fund_tiefe',
                        'Die Fundamenttiefe der Gabionen',
                        groesser_null=True)
        zahl('gab_fund_ueberstand', 'Der Fundamentueberstand der Gabionen',
             nicht_negativ=True)
        if gab_fund + 1e-9 < einbinde * 100.0 + 10.0:
            fehler.append('Die Gabionen-Fundamenttiefe muss mindestens '
                          '10 cm tiefer als die Einbindetiefe liegen.')
        if lage > 0 and minimum > lage:
            fehler.append('Die Mindesthoehe der untersten Lage darf die '
                          'Lagenhoehe nicht uebersteigen.')
        if not gab_tabelle(p.get('gab_breiten', '')):
            fehler.append('Die Liste der Gabionenbreiten enthaelt keinen '
                          'gueltigen positiven Wert.')
    else:
        zahl('breite_cm', 'Die Elementlaenge', groesser_null=True)
        zahl('dicke_cm', 'Die Wanddicke', groesser_null=True)
        zahl('pass_min', 'Die Mindestbreite des Passstuecks', groesser_null=True)
        zahl('eck_schenkel', 'Die Eckschenkellaenge', groesser_null=True)
        unter = zahl('unter_uk', 'Die Tiefe unter UK', nicht_negativ=True)
        fund = zahl('fund_tiefe', 'Die Fundamenttiefe', groesser_null=True)
        zahl('winkel_fuss_staerke', 'Die Staerke des Winkelsteinfusses',
             groesser_null=True)
        if fund <= unter:
            fehler.append('Die Fundamenttiefe muss groesser als die Tiefe '
                          'des Winkelsteins unter UK Gelaende sein.')
        for h in p.get('heights', []):
            try:
                fuss = float(p.get('feet', {}).get(str(int(round(h))), 0.0))
            except Exception:
                fuss = 0.0
            if fuss <= 0:
                fehler.append('Fuer die Kataloghoehe %g cm fehlt eine positive '
                              'Fusslaenge.' % h)
                break
    return fehler


def markiere_eine(h, prefix='PD-MWL-'):
    """Hebt GENAU EINE Linie deutlich hervor: dicker Linienzug ueber die
    ganze Laenge plus grosse gefuellte Punkte. Kein Text (wird bei kleinem
    Zoom nur als Kasten gezeichnet) und keine Farbe (kommt nicht ueberall an).
    """
    register_prefix(prefix)
    cls = prefix + 'HILFE'
    ensure_class(cls, None, False)
    pts = get_vertices(h)
    if len(pts) < 2:
        return
    L = poly_length(pts)
    r = max(L * 0.02, 1e-9)

    vs.PushAttrs()
    try:
        apply_attrs(cls, None, False, 200)          # sehr dicker Stift
        try:
            vs.MoveTo(pts[0][0], pts[0][1])
            for q in pts[1:]:
                vs.LineTo(q[0], q[1])
            vs.LNewObj()
        except Exception:
            pass
        st = station_table(pts)
        for k in range(5):
            q, _r = point_at_station(pts, st, L * (k + 1.0) / 6.0)
            apply_attrs(cls, (0, 0, 0), True, 20)
            try:
                vs.Oval(q[0] - r, q[1] + r, q[0] + r, q[1] - r)
                vs.LNewObj()
            except Exception:
                pass
    finally:
        vs.PopAttrs()
    try:
        vs.ReDrawAll()
    except Exception:
        pass


def frage_rolle(kandidaten, rolle, p):
    """Zeigt die Kandidaten einzeln hervorgehoben und fragt, ob es die
    gesuchte Linie ist. Rueckgabe: Objekt oder None (Abbruch)."""
    for nr, h in enumerate(kandidaten, 1):
        markiere_eine(h, p['prefix'])
        text = ('Die im Plan DICK hervorgehobene Linie (mit grossen Punkten):\n\n'
                '   %s\n\n'
                'Ist das die %s?\n\n'
                '(Nein = naechste Linie hervorheben, %d von %d)'
                % (describe(h).strip(), rolle, nr, len(kandidaten)))
        antwort = vs.YNDialog(text)
        cleanup_helpers()
        if antwort:
            return h
    return None


def zuordnung_waehlen(vor, p, soll):
    """Fragt die Bezugslinien einzeln ab - je Rolle wird eine Linie im Plan
    hervorgehoben. Rueckgabe: Liste der Objekte oder None."""
    a, b, c = assign_from_selection(vor, bool(p['aufsicht']) and len(vor) >= 3)
    reihenfolge = {0: a, 1: b, 2: c}
    rollen = ['UNTERKANTE der Abwicklung',
              'OBERKANTE der Abwicklung',
              'AUFSICHTSLINIE (buendige Aussenkante)']

    rest = list(vor)
    gewaehlt = []
    n = 3 if (p['aufsicht'] and len(vor) >= 3) else 2
    for i in range(n):
        if not rest:
            break
        # Wahrscheinlichsten Kandidaten zuerst zeigen
        kand = list(rest)
        vorschlag = reihenfolge.get(i)
        if vorschlag in kand:
            kand.remove(vorschlag)
            kand.insert(0, vorschlag)
        h = frage_rolle(kand, rollen[i], p)
        if h is None:
            return None
        gewaehlt.append(h)
        rest.remove(h)
    return gewaehlt if len(gewaehlt) >= 2 else None


def main():
    if not lizenz_pruefen():
        return

    _dbg('0 - Merkliste aufraeumen')
    try:
        registry_cleanup()
    except Exception:
        pass

    _dbg('1 - Start, Einstellungen laden')
    settings = load_settings()
    for pre in (settings.get('winkel_prefix'), settings.get('gab_prefix'),
                settings.get('prefix')):
        register_prefix(pre)
    for eintrag in load_registry():
        register_prefix(eintrag.get('prefix'))
        register_prefix(eintrag.get('gab_prefix'))
    _dbg('2 - Kataloge laden')
    _kataloge.clear()
    for typ in (0, 1):
        _kataloge[typ] = load_catalog(typ, settings)
    catalog = _kataloge.get(int(settings.get('stein_typ', 0))) or []
    if catalog:
        settings['heights'] = [c[0] for c in catalog]
    U.set(settings.get('unit', 'm'))
    cleanup_helpers()

    # Die Referenzlinien der Neuanlage werden stabil vor dem Dialog ausgewaehlt.
    vorauswahl = selected_objects()

    _dbg('3 - Hauptdialog oeffnen')
    ok, p = show_dialog(settings)
    if not ok:
        return
    _dbg('4 - Hauptdialog beendet')

    # Katalog des gewaehlten Steintyps verwenden
    p.pop('_catalog_dirty', None)
    p.pop('_gab_dirty', None)
    typ = int(p.get('stein_typ', 0))
    catalog = [] if typ == TYP_GABIONE else (
        _kataloge.get(typ) or load_catalog(typ, p))
    p['feet'] = dict((str(int(round(h))), float(f)) for h, f, _c, _b in catalog)
    p['colors'] = dict((str(int(round(h))), c) for h, _f, c, _b in catalog)
    p['breite_cm'] = {0: 50.0, 1: 100.0}.get(p['breite_mode'], p['breite_frei'])
    p['dicke_cm'] = {0: 10.0, 1: 12.0, 2: 15.0, 3: 20.0}.get(p['dicke_mode'],
                                                             p['dicke_frei'])
    fehler = validate_params(p)
    if fehler:
        vs.AlrtDialog('Bitte Eingaben korrigieren:\n\n' + '\n'.join(fehler))
        return
    U.set(p['unit'])
    save_settings(p)
    if typ != TYP_GABIONE:
        _kataloge[typ] = list(catalog)

    if p['action'] == 1:
        action_update_selection(p)
        return
    if p['action'] == 2:
        action_update_all(p)
        return
    if p['action'] in (5, 6):
        variante = 1 if p['action'] == 6 else 0
        if typ == TYP_GABIONE:
            action_gab_schnitte(p, variante)
        else:
            action_winkel_schnitte(p, variante)
        return
    if p['action'] in (3, 4):
        # Nur die Bezugshoehe aendern - alle uebrigen Vorgaben der Mauer
        # bleiben unveraendert.
        nur = {'ref_aktiv': p['ref_aktiv'], 'ref_hoehe': p['ref_hoehe']}
        if p['action'] == 3:
            action_update_selection(nur)
        else:
            action_update_all(nur)
        return

    # Neue Mauer: stabiler Vorauswahlmodus. Die Linien muessen vor dem
    # Start des Menuebefehls markiert sein und werden danach je Rolle bestaetigt.
    soll = 3 if p.get('aufsicht') else 2
    if len(vorauswahl) < soll:
        vs.AlrtDialog('Keine ausreichende Linienauswahl gefunden.\n\n'
                      'Bitte vor dem Start des Befehls mindestens %d Linien '
                      'markieren:\nUnterkante, Oberkante%s.' % (
                          soll, ' und Aufsicht' if soll == 3 else ''))
        return
    _dbg('5 - Bezugslinien aus Vorauswahl zuordnen')
    vorschlag = zuordnung_waehlen(vorauswahl, p, soll)
    if vorschlag is None:
        vs.AlrtDialog('Linienzuordnung abgebrochen - es wurde nichts gezeichnet.')
        return
    linien = [[(q[0], q[1]) for q in get_vertices(h)] for h in vorschlag]
    _dbg('6 - zeichnen')
    _ok2, msg = zeichne_bauteil(
        vorschlag[0], vorschlag[1],
        vorschlag[2] if len(vorschlag) > 2 else None, p,
        pts_override=(linien[0], linien[1],
                      linien[2] if len(linien) > 2 else None))
    vs.AlrtDialog(msg)
    try:
        vs.ReDrawAll()
    except Exception:
        pass


if __name__ == '__main__':
    try:
        main()
    except Exception:
        vs.AlrtDialog('Fehler in %s:\n\n%s' % (TOOL_TITLE, traceback.format_exc()))
