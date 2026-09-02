# -*- coding: utf-8 -*-
"""
Berechnungslogik des Rigolen-Tools.

Diese Datei enthaelt BEWUSST KEIN "import vs".
Alles hier ist reine Mathematik und laesst sich ausserhalb von Vectorworks
mit den Tests in tests/test_core.py pruefen.

Einheit aller Laengen: METER.
Einheit aller Volumina: KUBIKMETER.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import math
import re

from rigole_config.constants import (
    LENGTH_EPS,
    ID_PREFIX,
    ID_DIGITS,
    ID_START,
    HEIGHT_MODE_OK,
    HEIGHT_MODE_UK,
    ROUND_UP,
    ROUND_DOWN,
    ROUND_NEAREST,
)


# ===========================================================================
# 1 - Gesamtmasse
# ===========================================================================

def calculate_total_dimensions(basket_length, basket_width, basket_height,
                               count_length, count_width, count_height):
    """
    Gesamtmasse der Rigole aus Korbmass und Anordnung.

        Gesamtlaenge  = Korblaenge  * Anzahl hintereinander (X)
        Gesamtbreite  = Korbbreite  * Anzahl nebeneinander  (Y)
        Gesamthoehe   = Korbhoehe   * Anzahl uebereinander  (Z)

    Rueckgabe: (total_length, total_width, total_height) in m
    """
    total_length = float(basket_length) * int(count_length)
    total_width = float(basket_width) * int(count_width)
    total_height = float(basket_height) * int(count_height)
    return (total_length, total_width, total_height)


def apply_orientation(basket_length, basket_width, swapped):
    """
    Ausrichtung der Koerbe: laengs oder quer.

    swapped = False  ->  (Laenge, Breite) unveraendert
    swapped = True   ->  Laenge und Breite werden getauscht

    Damit laesst sich derselbe Korbtyp einmal in Laengsrichtung und einmal
    um 90 Grad gedreht verbauen, ohne die Konfiguration zu aendern. Die
    Hoehe bleibt in beiden Faellen unberuehrt.
    """
    if swapped:
        return (float(basket_width), float(basket_length))
    return (float(basket_length), float(basket_width))


def total_basket_count(count_length, count_width, count_height):
    """Gesamtzahl der Koerbe = Anzahl der zu erzeugenden Symbolinstanzen."""
    return int(count_length) * int(count_width) * int(count_height)


# ===========================================================================
# 2 - Korbanzahl in Laengsrichtung
# ===========================================================================

class BasketCountAnalysis(object):
    """
    Ergebnis der Pruefung "passt die gewuenschte Gesamtlaenge auf ganze Koerbe?"

    Attribute:
        requested       gewuenschte Gesamtlaenge (m)
        basket_length   Korblaenge (m)
        raw             requested / basket_length (ungerundet)
        is_exact        True, wenn ein ganzzahliges Vielfaches vorliegt
        count_down      abgerundete Korbanzahl (mindestens 1)
        count_up        aufgerundete Korbanzahl
        length_down     tatsaechliche Laenge bei count_down (m)
        length_up       tatsaechliche Laenge bei count_up (m)
    """

    def __init__(self, requested, basket_length, raw, is_exact,
                 count_down, count_up, length_down, length_up):
        self.requested = requested
        self.basket_length = basket_length
        self.raw = raw
        self.is_exact = is_exact
        self.count_down = count_down
        self.count_up = count_up
        self.length_down = length_down
        self.length_up = length_up

    def __repr__(self):
        return ("BasketCountAnalysis(requested=%.6f, raw=%.6f, exact=%s, "
                "down=%d/%.6f, up=%d/%.6f)"
                % (self.requested, self.raw, self.is_exact,
                   self.count_down, self.length_down,
                   self.count_up, self.length_up))


def analyse_basket_count(target_length, basket_length, eps=LENGTH_EPS):
    """
    Prueft, ob sich die gewuenschte Gesamtlaenge exakt aus ganzen Koerben
    herstellen laesst, und liefert die Alternativen fuer den Warndialog.

    Es wird hier NICHT stillschweigend gerundet - die Entscheidung trifft
    der Anwender (siehe Punkt 5 der Spezifikation).
    """
    target_length = float(target_length)
    basket_length = float(basket_length)

    if basket_length <= 0.0:
        raise ValueError("Korblaenge muss groesser 0 sein.")
    if target_length <= 0.0:
        raise ValueError("Gesamtlaenge muss groesser 0 sein.")

    raw = target_length / basket_length
    nearest = int(round(raw))
    is_exact = (nearest >= 1) and (abs(nearest * basket_length - target_length) <= eps)

    if is_exact:
        count_down = nearest
        count_up = nearest
    else:
        count_down = int(raw)                 # Abschneiden = Abrunden (raw > 0)
        if count_down < 1:
            count_down = 1
        count_up = count_down + 1
        # Sonderfall raw < 1: abrunden ergaebe 0 -> beide auf 1 bzw. 1/2
        if raw < 1.0:
            count_down = 1
            count_up = 1

    return BasketCountAnalysis(
        requested=target_length,
        basket_length=basket_length,
        raw=raw,
        is_exact=is_exact,
        count_down=count_down,
        count_up=count_up,
        length_down=count_down * basket_length,
        length_up=count_up * basket_length,
    )


def calculate_basket_count(target_length, basket_length, rounding=ROUND_UP,
                           eps=LENGTH_EPS):
    """
    Modus B: aus gewuenschter Gesamtlaenge die Korbanzahl bestimmen.

    rounding: ROUND_UP | ROUND_DOWN | ROUND_NEAREST

    Rueckgabe: (count, actual_length, was_exact)
    """
    analysis = analyse_basket_count(target_length, basket_length, eps=eps)

    if analysis.is_exact:
        return (analysis.count_down, analysis.length_down, True)

    if rounding == ROUND_DOWN:
        count = analysis.count_down
    elif rounding == ROUND_NEAREST:
        d_down = abs(analysis.length_down - analysis.requested)
        d_up = abs(analysis.length_up - analysis.requested)
        count = analysis.count_down if d_down <= d_up else analysis.count_up
    elif rounding == ROUND_UP:
        count = analysis.count_up
    else:
        raise ValueError("Unbekannte Rundungsart: %r" % (rounding,))

    return (count, count * float(basket_length), False)


# ===========================================================================
# 3 - Volumen
# ===========================================================================

def calculate_storage_volume(total_length, total_width, total_height,
                             storage_coefficient):
    """
        V_brutto   = L * B * H
        V_Speicher = V_brutto * Speicherkoeffizient

    storage_coefficient ist ein FAKTOR (0 < k <= 1), nicht Prozent.
    Rueckgabe: (v_brutto, v_speicher) in m3, ungerundet.
    """
    v_brutto = float(total_length) * float(total_width) * float(total_height)
    v_speicher = v_brutto * float(storage_coefficient)
    return (v_brutto, v_speicher)


def percent_to_factor(percent):
    """95 -> 0.95"""
    return float(percent) / 100.0


def factor_to_percent(factor):
    """0.95 -> 95.0"""
    return float(factor) * 100.0


# ===========================================================================
# 4 - Hoehen
# ===========================================================================

def calculate_heights(height_mode, value, total_height):
    """
    height_mode = HEIGHT_MODE_OK  -> value ist die Oberkante,  UK = OK - H
    height_mode = HEIGHT_MODE_UK  -> value ist die Unterkante, OK = UK + H

    Alle Werte sind reale Planungshoehen in Metern.
    Rueckgabe: (ok, uk)
    """
    value = float(value)
    total_height = float(total_height)

    if height_mode == HEIGHT_MODE_OK:
        ok = value
        uk = value - total_height
    elif height_mode == HEIGHT_MODE_UK:
        uk = value
        ok = value + total_height
    else:
        raise ValueError("Unbekannter Hoehenbezug: %r" % (height_mode,))

    return (ok, uk)


# ===========================================================================
# 5 - Rasterpositionen der Koerbe
# ===========================================================================

def iter_basket_positions(count_length, count_width, count_height,
                          basket_length, basket_width, basket_height,
                          origin_x=0.0, origin_y=0.0, base_z=0.0):
    """
    Liefert die Einfuegepunkte aller Koerbe.

        x = Einfuegepunkt X + i * Korblaenge     (i = hintereinander,  X)
        y = Einfuegepunkt Y + j * Korbbreite     (j = nebeneinander,   Y)
        z = Rigolen-UK      + k * Korbhoehe      (k = uebereinander,   Z)

    Der zurueckgegebene Punkt ist die VORDERE LINKE UNTERE Ecke des Korbes.
    Ob das Symbol dort mit seinem Einfuegepunkt sitzt oder mittig, haengt vom
    Symbol ab -> siehe symbol_anchor_offset().

    Generator, damit auch 400+ Koerbe ohne grosse Listen im Speicher gehen.
    """
    for k in range(int(count_height)):
        z = float(base_z) + k * float(basket_height)
        for j in range(int(count_width)):
            y = float(origin_y) + j * float(basket_width)
            for i in range(int(count_length)):
                x = float(origin_x) + i * float(basket_length)
                yield (i, j, k, x, y, z)


def symbol_anchor_offset(basket_length, basket_width, anchor="corner"):
    """
    Zusatzversatz, falls der Einfuegepunkt der Symboldefinition NICHT in der
    vorderen linken Ecke, sondern in der Mitte des Korbes liegt.

    anchor = "corner" -> (0, 0)
    anchor = "center" -> (L/2, B/2)
    """
    if anchor == "center":
        return (float(basket_length) / 2.0, float(basket_width) / 2.0)
    return (0.0, 0.0)


# ===========================================================================
# 6 - Rigolen-ID
# ===========================================================================

def parse_rigole_id(text, prefix=ID_PREFIX):
    """
    'RIG-003' -> 3 ; alles andere -> None
    Toleriert Gross-/Kleinschreibung und fuehrende/abschliessende Leerzeichen.
    """
    if text is None:
        return None
    s = str(text).strip()
    if not s:
        return None
    pattern = r"^" + re.escape(prefix) + r"(\d+)$"
    m = re.match(pattern, s, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except ValueError:
        return None


def generate_next_rigole_id(existing_ids, prefix=ID_PREFIX, digits=ID_DIGITS,
                            start=ID_START):
    """
    Ermittelt die naechste freie Rigolen-ID.

    existing_ids: Liste der bereits im Dokument vorhandenen ID-Strings
                  (wird in der VW-Schicht per vs.ForEachObject ueber das
                  Kriterium (R IN ['DB_Rigole']) eingesammelt).

    Bestehende IDs werden NIE ueberschrieben: es wird immer max+1 vergeben,
    Luecken werden bewusst nicht aufgefuellt (stabile Nummerierung).
    """
    highest = start - 1
    for raw in (existing_ids or []):
        num = parse_rigole_id(raw, prefix=prefix)
        if num is not None and num > highest:
            highest = num
    next_num = highest + 1
    if next_num < start:
        next_num = start
    return "%s%0*d" % (prefix, int(digits), next_num)


# ===========================================================================
# 7 - Standardposition der Beschriftung
# ===========================================================================

def default_label_position(origin_x, origin_y, total_length, total_width,
                           offset_x, offset_y):
    """
    Standardposition der Beschriftung: rechts oberhalb der Rigole.

    Die Rigole wird vom Einfuegepunkt aus in positive X-/Y-Richtung
    aufgebaut, die rechte obere Ecke liegt also bei
    (origin_x + Gesamtlaenge, origin_y + Gesamtbreite).

    Rueckgabe: (x, y) in m - Ankerpunkt des Textobjekts (oben links,
    passend zu TextJust links / TextVerticalAlign oben).
    """
    x = float(origin_x) + float(total_length) + float(offset_x)
    y = float(origin_y) + float(total_width) + float(offset_y)
    return (x, y)


# ===========================================================================
# 8 - Komplettberechnung
# ===========================================================================

def alle_slots(klasse):
    """
    Alle __slots__ einer Klasse einschliesslich ihrer Basisklassen, in der
    Reihenfolge Basis zuerst.

    Ohne das griffe eine abgeleitete Ergebnisklasse (PolygonResult) beim
    Anlegen und bei as_dict() nur auf ihre EIGENEN Zusatzfelder zu - die
    geerbten blieben leer. Ein Fehler, der erst beim Datensatzschreiben
    auffiele.
    """
    namen = []
    for basis in reversed(klasse.__mro__):
        for name in getattr(basis, "__slots__", ()):
            if name not in namen:
                namen.append(name)
    return tuple(namen)


class RigoleResult(object):
    """
    Alle abgeleiteten Werte einer Rigole an einem Ort.
    Wird von der Dialog-, Record-, Geometrie- und Beschriftungsschicht
    gemeinsam genutzt, damit nirgends doppelt gerechnet wird.
    """

    __slots__ = (
        "basket_length", "basket_width", "basket_height",
        "count_length", "count_width", "count_height",
        "total_length", "total_width", "total_height",
        "basket_count",
        "storage_coefficient", "v_brutto", "v_speicher",
        "schacht_dn", "schacht_durchmesser", "schacht_positionen",
        "schacht_ok", "schacht_uk",
        "height_mode", "ok", "uk",
    )

    def __init__(self, **kwargs):
        for key in alle_slots(type(self)):
            setattr(self, key, kwargs.get(key))

    def as_dict(self):
        return dict((k, getattr(self, k)) for k in alle_slots(type(self)))

    @property
    def hat_schacht(self):
        return bool(self.schacht_positionen)

    @property
    def schacht_anzahl(self):
        return len(self.schacht_positionen or ())

    @property
    def schacht_hoehe(self):
        """Bauhoehe eines Schachtes in m (OK - UK)."""
        try:
            return float(self.schacht_ok) - float(self.schacht_uk)
        except (TypeError, ValueError):
            return 0.0

    def __repr__(self):
        return "RigoleResult(%r)" % (self.as_dict(),)


class KiesResult(object):
    """
    Alle abgeleiteten Werte einer KIESRIGOLE.

    Die Feldnamen total_length/-width/-height, v_brutto, v_speicher, ok und
    uk heissen bewusst genauso wie bei RigoleResult. Dadurch koennen
    Beschriftung, Datensatz und Ergebnisanzeige dieselben Bausteine
    verwenden, ohne auf die Bauart Ruecksicht nehmen zu muessen.
    """

    __slots__ = (
        "total_length", "total_width", "total_height",
        "material", "storage_coefficient", "v_brutto", "v_speicher",
        "rohr_dn", "rohr_durchmesser", "rohr_uk", "rohr_achse",
        "rohr_laenge_brutto", "rohr_laenge", "rohr_volumen", "rohr_segmente",
        "schacht_dn", "schacht_durchmesser", "schacht_positionen",
        "schacht_ok", "schacht_uk",
        "height_mode", "ok", "uk",
    )

    def __init__(self, **kwargs):
        for key in self.__slots__:
            setattr(self, key, kwargs.get(key))

    def as_dict(self):
        return dict((k, getattr(self, k)) for k in self.__slots__)

    @property
    def hat_rohr(self):
        try:
            return float(self.rohr_durchmesser or 0.0) > 0.0
        except (TypeError, ValueError):
            return False

    @property
    def hat_schacht(self):
        return bool(self.schacht_positionen)

    @property
    def schacht_anzahl(self):
        return len(self.schacht_positionen or ())

    @property
    def schacht_hoehe(self):
        """Bauhoehe eines Schachtes in m (OK - UK)."""
        try:
            return float(self.schacht_ok) - float(self.schacht_uk)
        except (TypeError, ValueError):
            return 0.0

    def __repr__(self):
        return "KiesResult(%r)" % (self.as_dict(),)


def pipe_volume(durchmesser, laenge):
    """
    Volumen des Draenrohres in m3 (Kreiszylinder ueber den Nenndurchmesser).

    Gerechnet wird mit dem NENNDURCHMESSER (lichte Weite) - so, wie ihn die
    DN-Bezeichnung angibt und wie das Rohr auch gezeichnet wird. Wandstaerke
    und Lochung bleiben ausser Betracht; der Wert ist eine Mengenangabe zur
    Einordnung, keine hydraulische Groesse.
    """
    try:
        d = float(durchmesser)
        l = float(laenge)
    except (TypeError, ValueError):
        return 0.0
    if d <= 0.0 or l <= 0.0:
        return 0.0
    return math.pi * (d / 2.0) ** 2 * l


def pipe_axis_height(durchmesser, uk_ueber_sohle):
    """
    Hoehe der Rohrachse ueber der Sohle, in Metern.

    Eingegeben wird der Abstand der ROHRUNTERKANTE zur Kiessohle - das ist
    das Mass, das auf der Baustelle abgesteckt und im Schnitt bemasst wird
    (Vorgabe des Anwenders vom 24.08.2026). Die Achse ergibt sich daraus:

        Achse = Abstand UK Rohr zur Sohle + halber Nenndurchmesser

    Der Wert 0 bedeutet damit "aufliegend": die Rohrunterkante sitzt genau
    auf der Sohle, die Achse liegt auf halber Rohrhoehe.
    """
    try:
        d = float(durchmesser)
    except (TypeError, ValueError):
        d = 0.0
    try:
        uk = float(uk_ueber_sohle)
    except (TypeError, ValueError):
        uk = 0.0
    if d <= 0.0:
        return 0.0
    if uk < 0.0:
        uk = 0.0
    return uk + d / 2.0


def schacht_positionen(rigolen_laenge, schacht_durchmesser,
                       rand=0.20, mitte_ab_laenge=20.0):
    """
    Lage der Kontrollschaechte, gemessen von der vorderen Stirnseite der
    Kiesrigole in Metern.

    Vorgabe des Anwenders (24.08.2026, praezisiert am selben Tag):
        * Die AUSSENKANTE des Schachtes liegt immer 'rand' (0,20 m) innerhalb
          der Aussenkante der Kiesfuellung. Die Schachtachse rueckt damit um
          rand + halber Schachtdurchmesser ein.
        * Je ein Schacht vorne und hinten.
        * Ist der Achsabstand der beiden groesser als 'mitte_ab_laenge'
          (20 m), kommt GENAU EINER zusaetzlich in die Mitte.

    Die Schaechte liegen damit vollstaendig INNERHALB der Schuettung; das
    Draenrohr laeuft nur noch zwischen ihnen.

    Rueckgabe: Liste der x-Positionen (aufsteigend). Leer, wenn die Rigole
    zu kurz ist, um zwei Schaechte mit dem geforderten Rand aufzunehmen.
    """
    try:
        laenge = float(rigolen_laenge)
        radius = float(schacht_durchmesser) / 2.0
        rand = float(rand)
    except (TypeError, ValueError):
        return []
    if laenge <= 0.0 or radius <= 0.0:
        return []

    erste = rand + radius
    letzte = laenge - rand - radius
    if letzte - erste <= LENGTH_EPS:
        # Zu kurz: die beiden Schaechte wuerden sich beruehren oder
        # durchdringen. Die Pruefung meldet das als Fehler.
        return []

    # Der Vergleich braucht die Toleranz: 20.8 - 2 * 0.4 ergibt in
    # Gleitkomma 20.000000000000004 und wuerde sonst einen Mittelschacht
    # ausloesen, obwohl der Achsabstand genau 20 m betraegt.
    if (letzte - erste) > float(mitte_ab_laenge) + LENGTH_EPS:
        return [erste, (erste + letzte) / 2.0, letzte]
    return [erste, letzte]


def pipe_segments(positionen, schacht_durchmesser, rohr_laenge=0.0,
                  eps=LENGTH_EPS):
    """
    Die Rohrstuecke zwischen den Schaechten.

    Das Draenrohr laeuft ausschliesslich ZWISCHEN den Schaechten: es beginnt
    an der Innenwand des ersten und endet an der Innenwand des naechsten.
    Ohne Schaechte bleibt es bei einem durchgehenden Rohr ueber
    'rohr_laenge'.

    Rueckgabe: Liste von (x_anfang, x_ende) in Metern, gemessen von der
    vorderen Stirnseite der Kiesrigole.
    """
    try:
        radius = float(schacht_durchmesser) / 2.0
    except (TypeError, ValueError):
        radius = 0.0

    if not positionen or radius <= 0.0:
        try:
            laenge = float(rohr_laenge)
        except (TypeError, ValueError):
            return []
        return [(0.0, laenge)] if laenge > eps else []

    grenzen = sorted(float(p) for p in positionen)
    segmente = []
    for a, b in zip(grenzen, grenzen[1:]):
        von, bis = a + radius, b - radius
        if bis - von > eps:
            segmente.append((von, bis))
    return segmente


def segments_length(segmente):
    """Summe der Rohrstuecke in Metern."""
    return sum(float(b) - float(a) for a, b in (segmente or ()))


def compute_kiesrigole(laenge, breite, hoehe, storage_coefficient,
                       height_mode, height_value,
                       material="", rohr_dn="", rohr_durchmesser=0.0,
                       rohr_uk_ueber_sohle=0.0,
                       mit_schacht=False, schacht_dn="",
                       schacht_durchmesser=0.0, schacht_ok=None,
                       schacht_tiefe_unter_rohr=0.20,
                       schacht_rand=0.20,
                       schacht_mitte_ab_laenge=20.0):
    """
    Berechnet eine Kiesrigole.

        V_brutto   = Laenge * Breite * Hoehe
        V_Speicher = V_brutto * Hohlraumanteil

    Das Draenrohr geht in das Speichervolumen NICHT ein - weder abziehend
    noch hinzufuegend. Sein Volumen wird getrennt ausgewiesen, damit die
    Zahl nachvollziehbar bleibt und spaeter bewusst entschieden werden kann,
    wie sie zu beruecksichtigen ist.

    SCHAECHTE
    ---------
    Sind Schaechte gewuenscht und liegt ein Draenrohr vor, ruecken sie mit
    ihrer Aussenkante 'schacht_rand' (0,20 m) von den Stirnseiten der
    Schuettung ein; ueber 20 m Achsabstand kommt zusaetzlich einer in die
    Mitte. Das Draenrohr laeuft dann nur noch ZWISCHEN den Schaechten.
    Ausgewiesen wird die tatsaechlich verlegte Rohrlaenge (rohr_laenge)
    neben dem Achsabstand erster bis letzter Schacht (rohr_laenge_brutto).
    """
    laenge = float(laenge)
    breite = float(breite)
    hoehe = float(hoehe)

    v_brutto = laenge * breite * hoehe
    v_speicher = v_brutto * float(storage_coefficient)
    ok, uk = calculate_heights(height_mode, height_value, hoehe)

    rohr_d = float(rohr_durchmesser or 0.0)
    rohr_uk = max(0.0, float(rohr_uk_ueber_sohle or 0.0))
    achse = pipe_axis_height(rohr_d, rohr_uk)
    laenge_brutto = laenge if rohr_d > 0.0 else 0.0

    # --- Schaechte ---------------------------------------------------------
    schacht_d = float(schacht_durchmesser or 0.0)
    positionen = []
    s_ok = None
    s_uk = None
    if mit_schacht and rohr_d > 0.0 and schacht_d > 0.0:
        positionen = schacht_positionen(laenge, schacht_d,
                                        schacht_rand, schacht_mitte_ab_laenge)
        # Unterkante Schacht = Rohrunterkante minus Sumpftiefe.
        # rohr_uk ist der Abstand ueber der Kiessohle, uk die absolute
        # Hoehenkote der Sohle.
        s_uk = uk + rohr_uk - float(schacht_tiefe_unter_rohr)
        s_ok = None if schacht_ok is None else float(schacht_ok)
    if not positionen:
        schacht_d = 0.0
        schacht_dn = ""

    # Mit Schaechten laeuft das Rohr nur noch ZWISCHEN ihnen; die Bruttolaenge
    # ist dann der Achsabstand vom ersten zum letzten Schacht.
    if positionen:
        laenge_brutto = positionen[-1] - positionen[0]

    segmente = pipe_segments(positionen, schacht_d, laenge_brutto)
    if rohr_d <= 0.0:
        segmente = []
    laenge_netto = segments_length(segmente)
    rohr_vol = pipe_volume(rohr_d, laenge_netto)

    return KiesResult(
        total_length=laenge,
        total_width=breite,
        total_height=hoehe,
        material=material,
        storage_coefficient=float(storage_coefficient),
        v_brutto=v_brutto,
        v_speicher=v_speicher,
        rohr_dn=rohr_dn,
        rohr_durchmesser=rohr_d,
        rohr_uk=rohr_uk,
        rohr_achse=achse,
        rohr_laenge_brutto=laenge_brutto,
        rohr_laenge=laenge_netto,
        rohr_volumen=rohr_vol,
        rohr_segmente=segmente,
        schacht_dn=schacht_dn,
        schacht_durchmesser=schacht_d,
        schacht_positionen=positionen,
        schacht_ok=s_ok,
        schacht_uk=s_uk,
        height_mode=height_mode,
        ok=ok,
        uk=uk,
    )


def korb_schacht_reihen(count_width):
    """
    Auf WELCHEN Reihen sitzen die Kontrollschaechte?

    Vorgabe des Anwenders vom 24.08.2026 (Reihe = Korbreihe quer, also
    count_width; Zaehlung hier 0-basiert):

        1 bis 2 Reihen   ->  Reihe 1                      (Index 0)
        3 bis 5 Reihen   ->  Reihe 2                      (Index 1)
        ab 6 Reihen      ->  Reihe 2 und vorletzte Reihe  (Index 1 und n-2)

    Rueckgabe: Liste der Reihenindizes, aufsteigend und ohne Dubletten.
    """
    try:
        n = int(count_width)
    except (TypeError, ValueError):
        return []
    if n < 1:
        return []
    if n <= 2:
        return [0]
    if n <= 5:
        return [1]
    reihen = sorted(set([1, n - 2]))
    return reihen


def korb_schacht_positionen(count_length, count_width,
                            basket_length, basket_width):
    """
    Mittelpunkte der Kontrollschaechte in der Draufsicht, gemessen vom
    vorderen linken Eck der Rigole in Metern.

    Jeder Schacht sitzt MITTIG auf der Oberkante eines Rigolenkorbes -
    auf dem ersten und dem letzten Korb der betroffenen Reihe.

    Rueckgabe: Liste von (x, y).
    """
    try:
        nl = int(count_length)
        bl = float(basket_length)
        bw = float(basket_width)
    except (TypeError, ValueError):
        return []
    if nl < 1 or bl <= 0.0 or bw <= 0.0:
        return []

    spalten = sorted(set([0, nl - 1]))
    positionen = []
    for reihe in korb_schacht_reihen(count_width):
        y = (reihe + 0.5) * bw
        for spalte in spalten:
            positionen.append(((spalte + 0.5) * bl, y))
    return positionen


def compute_rigole(basket_length, basket_width, basket_height,
                   count_length, count_width, count_height,
                   storage_coefficient, height_mode, height_value,
                   mit_schacht=False, schacht_dn="",
                   schacht_durchmesser=0.0, schacht_ok=None):
    """
    Fuehrt alle Berechnungen in einem Schritt aus.
    Erwartet bereits validierte und in Laengsrichtung aufgeloeste Werte
    (d. h. count_length steht fest - Modus B wurde vorher ueber
    calculate_basket_count() abgehandelt).

    SCHAECHTE
    ---------
    Sind Schaechte gewuenscht, sitzen sie mittig auf der Oberkante eines
    Rigolenkorbes; ihre Unterkante ist damit die Oberkante der Rigole.
    Welche Koerbe es trifft, entscheidet korb_schacht_positionen().
    """
    total_length, total_width, total_height = calculate_total_dimensions(
        basket_length, basket_width, basket_height,
        count_length, count_width, count_height)

    v_brutto, v_speicher = calculate_storage_volume(
        total_length, total_width, total_height, storage_coefficient)

    ok, uk = calculate_heights(height_mode, height_value, total_height)

    # --- Kontrollschaechte -------------------------------------------------
    # Die Unterkante ist die Oberkante der Rigole: der Schacht sitzt AUF
    # dem Korb, er steckt nicht in ihm.
    schacht_d = float(schacht_durchmesser or 0.0)
    positionen = []
    if mit_schacht and schacht_d > 0.0:
        positionen = korb_schacht_positionen(
            count_length, count_width, basket_length, basket_width)

    return RigoleResult(
        basket_length=float(basket_length),
        basket_width=float(basket_width),
        basket_height=float(basket_height),
        count_length=int(count_length),
        count_width=int(count_width),
        count_height=int(count_height),
        total_length=total_length,
        total_width=total_width,
        total_height=total_height,
        basket_count=total_basket_count(count_length, count_width, count_height),
        storage_coefficient=float(storage_coefficient),
        v_brutto=v_brutto,
        v_speicher=v_speicher,
        schacht_dn=(schacht_dn if positionen else ""),
        schacht_durchmesser=(schacht_d if positionen else 0.0),
        schacht_positionen=positionen,
        schacht_ok=(None if not positionen or schacht_ok is None
                    else float(schacht_ok)),
        # Der Schacht sitzt AUF dem Korb: seine Unterkante ist die
        # Oberkante der Rigole.
        schacht_uk=(ok if positionen else None),
        height_mode=height_mode,
        ok=ok,
        uk=uk,
    )


# ===========================================================================
# 12 - RIGOLE KOMPLEX: Rigole nach gezeichnetem Polygon (26.08.2026)
# ===========================================================================

class PolygonResult(RigoleResult):
    """
    Ergebnis einer Rigole, die einem gezeichneten Polygon folgt.

    Erbt bewusst von RigoleResult: Beschriftung, Hoehenlogik und
    Schachtdarstellung arbeiten damit unveraendert weiter. Die geerbten
    Felder haben hier folgende Bedeutung:

        total_length / total_width  Huellmass der BELEGTEN Koerbe, gemessen
                                    in Rasterrichtung (nicht des Polygons)
        count_length / count_width  Rasterspalten bzw. -reihen des belegten
                                    Bereichs - nur als Kennzahl, das Raster
                                    ist nicht vollstaendig gefuellt
        basket_count                tatsaechlich gesetzte Koerbe

    Zusaetzlich:
        polygon_punkte    Eckpunkte im ORIGINALSYSTEM der Zeichnung (m)
        polygon_lokal     dieselben Punkte im gedrehten Rastersystem (m)
        polygon_flaeche   m2
        raster_winkel     Grad, Drehung des Rasters gegen die x-Achse
        raster            polygon.Rasterergebnis
        zellen            [(spalte, reihe), ...] der belegten Korbplaetze
        zell_ursprung     (x, y) der Zelle (0,0) im gedrehten System
        lokaler_ursprung  (x, y) im gedrehten System, auf den sich die
                          Symboldefinition bezieht (linke untere Ecke der
                          belegten Huellbox)
        einfuegepunkt     (x, y) im ORIGINALSYSTEM - dort wird die Instanz
                          gesetzt, gedreht um raster_winkel
        belegte_flaeche   m2 einer Lage
        ausnutzung        Faktor 0..1 (belegt / Polygonflaeche)
        schacht_zellen    [(spalte, reihe), ...]
    """

    __slots__ = (
        "polygon_punkte", "polygon_lokal", "polygon_flaeche",
        "raster_winkel", "raster", "zellen", "zell_ursprung",
        "lokaler_ursprung", "einfuegepunkt",
        "belegte_flaeche", "ausnutzung", "schacht_zellen",
    )

    @property
    def koerbe_je_lage(self):
        return len(self.zellen or ())

    @property
    def eckenzahl(self):
        return len(self.polygon_punkte or ())

    def zellrechteck_lokal(self, zelle):
        """
        (x0, y0, x1, y1) einer Zelle, bezogen auf den lokalen Ursprung -
        also genau so, wie die Symboldefinition aufgebaut wird.
        """
        spalte, reihe = zelle
        x0 = (self.zell_ursprung[0] + spalte * self.basket_length
              - self.lokaler_ursprung[0])
        y0 = (self.zell_ursprung[1] + reihe * self.basket_width
              - self.lokaler_ursprung[1])
        return (x0, y0, x0 + self.basket_length, y0 + self.basket_width)

    def polygon_lokal_verschoben(self):
        """Polygonpunkte, bezogen auf den lokalen Ursprung."""
        ox, oy = self.lokaler_ursprung
        return [(x - ox, y - oy) for (x, y) in (self.polygon_lokal or ())]

    def __repr__(self):
        return "PolygonResult(%d Koerbe je Lage, %.2f m2)" % (
            self.koerbe_je_lage, self.polygon_flaeche or 0.0)


def compute_rigole_polygon(punkte, basket_length, basket_width, basket_height,
                           count_height, storage_coefficient,
                           height_mode, height_value,
                           raster_winkel=None, such_schritte=4,
                           mit_schacht=False, schacht_dn="",
                           schacht_durchmesser=0.0, schacht_ok=None,
                           schacht_mitte_ab_laenge=20.0):
    """
    Fuellt ein gezeichnetes Polygon mit Rigolenkoerben.

    punkte          Eckpunkte in METERN im Koordinatensystem der Zeichnung
    raster_winkel   None = an der laengsten Polygonkante ausrichten,
                    sonst der gewuenschte Winkel in Grad

    Gerechnet wird in einem GEDREHTEN System: Das Polygon wird um
    -raster_winkel gedreht, danach liegt die Rasterrichtung auf der x-Achse
    und die Zellen sind achsparallel. Die fertige Symboldefinition wird
    spaeter einfach mit +raster_winkel eingefuegt - vs.Symbol nimmt den
    Winkel entgegen, es muss also nichts von Hand zurueckgedreht werden.

    Rueckgabe: PolygonResult
    """
    from rigole_core import polygon as poly

    ecken = poly.bereinige(punkte)
    if len(ecken) < 3:
        raise poly.PolygonFehler(
            u"Das Umgrenzungspolygon hat weniger als drei Eckpunkte.")

    if raster_winkel is None:
        _index, _laenge, winkel = poly.laengste_kante(ecken)
    else:
        winkel = float(raster_winkel)

    # In das Rastersystem drehen: -winkel um den ersten Eckpunkt.
    drehpunkt = ecken[0]
    lokal = poly.drehe(ecken, -winkel, drehpunkt)

    raster = poly.belege_polygon(lokal, basket_length, basket_width,
                                 such_schritte=such_schritte)

    flaeche_polygon = poly.flaeche(ecken)
    je_lage = raster.anzahl
    belegt = je_lage * float(basket_length) * float(basket_width)
    ausnutzung = (belegt / flaeche_polygon) if flaeche_polygon > 0.0 else 0.0

    # Huellmass der tatsaechlich belegten Koerbe, im Rastersystem.
    x0, y0, x1, y1 = raster.belegte_bounding_box()
    total_length = x1 - x0
    total_width = y1 - y0
    total_height = float(basket_height) * int(count_height)

    spalten = sorted(set(z[0] for z in raster.zellen)) or [0]
    reihen = sorted(set(z[1] for z in raster.zellen)) or [0]

    # Speichervolumen: NICHT ueber das Huellmass - der Koerper ist nicht
    # rechteckig. Massgebend ist die Summe der wirklich gesetzten Koerbe.
    basket_count = je_lage * int(count_height)
    from rigole_config.constants import POLY_MAX_KOERBE
    if basket_count > POLY_MAX_KOERBE:
        raise poly.PolygonFehler(
            "Mehr als %d Körbe (%d) sind für eine komplexe Rigole nicht zulässig. "
            "Bitte die Rigole aufteilen." % (POLY_MAX_KOERBE, basket_count))
    v_brutto = (basket_count * float(basket_length) * float(basket_width)
                * float(basket_height))
    v_speicher = v_brutto * float(storage_coefficient)

    ok, uk = calculate_heights(height_mode, height_value, total_height)

    # --- Kontrollschaechte -------------------------------------------------
    schacht_d = float(schacht_durchmesser or 0.0)
    schacht_zellen_ = []
    positionen = []
    if mit_schacht and schacht_d > 0.0 and raster.zellen:
        schacht_zellen_ = poly.schacht_zellen(
            raster, mitte_ab_laenge=schacht_mitte_ab_laenge)
        # Positionen als Mittelpunkte im LOKALEN System, bezogen auf die
        # linke untere Ecke der belegten Huellbox - dieselbe Bezugsgroesse
        # wie fuer die Koerbe.
        for zelle in schacht_zellen_:
            mx, my = raster.zellmitte(zelle)
            positionen.append((mx - x0, my - y0))

    ergebnis = PolygonResult(
        basket_length=float(basket_length),
        basket_width=float(basket_width),
        basket_height=float(basket_height),
        count_length=(spalten[-1] - spalten[0] + 1),
        count_width=(reihen[-1] - reihen[0] + 1),
        count_height=int(count_height),
        total_length=total_length,
        total_width=total_width,
        total_height=total_height,
        basket_count=basket_count,
        storage_coefficient=float(storage_coefficient),
        v_brutto=v_brutto,
        v_speicher=v_speicher,
        schacht_dn=(schacht_dn if positionen else ""),
        schacht_durchmesser=(schacht_d if positionen else 0.0),
        schacht_positionen=positionen,
        schacht_ok=(None if not positionen or schacht_ok is None
                    else float(schacht_ok)),
        schacht_uk=(ok if positionen else None),
        height_mode=height_mode,
        ok=ok,
        uk=uk,
        # --- polygonspezifisch ---
        polygon_punkte=ecken,
        polygon_lokal=lokal,
        polygon_flaeche=flaeche_polygon,
        raster_winkel=winkel,
        raster=raster,
        zellen=list(raster.zellen),
        zell_ursprung=raster.ursprung,
        lokaler_ursprung=(x0, y0),
        einfuegepunkt=poly.drehe_punkt((x0, y0), winkel, drehpunkt),
        belegte_flaeche=belegt,
        ausnutzung=ausnutzung,
        schacht_zellen=schacht_zellen_,
    )
    return ergebnis
