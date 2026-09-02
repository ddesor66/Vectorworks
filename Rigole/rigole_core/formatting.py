# -*- coding: utf-8 -*-
"""
Zahlen- und Textformatierung sowie Aufbau des Beschriftungstextes.

Kein "import vs" -> ausserhalb von Vectorworks testbar.
Anzeige-Einheiten: m / m2 / m3, unabhaengig von den Dokumenteinheiten.
Dezimaltrennzeichen: Komma (deutsche Planungspraxis).

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

from rigole_config.constants import LABEL_FIELDS


DEC_LENGTH = 2      # Nachkommastellen fuer Laengen in m
DEC_HEIGHT = 2      # Nachkommastellen fuer Hoehenkoten in m
DEC_VOLUME = 2      # Nachkommastellen fuer Volumen in m3
DEC_PERCENT = 0     # Nachkommastellen fuer Prozentwerte


def _dec(value, places, decimal_sep=","):
    """Rundet kaufmaennisch-neutral ueber format() und setzt das Trennzeichen."""
    s = ("%." + str(int(places)) + "f") % (float(value),)
    if s == "-" + ("0." + "0" * places if places else "0"):
        s = s[1:]                      # "-0,00" vermeiden
    return s.replace(".", decimal_sep)


def fmt_length(value_m, places=DEC_LENGTH, unit=True, decimal_sep=","):
    s = _dec(value_m, places, decimal_sep)
    return s + (" m" if unit else "")


def fmt_height(value_m, places=DEC_HEIGHT, unit=True, decimal_sep=","):
    s = _dec(value_m, places, decimal_sep)
    return s + (" m" if unit else "")


def fmt_volume(value_m3, places=DEC_VOLUME, unit=True, decimal_sep=","):
    s = _dec(value_m3, places, decimal_sep)
    return s + (u" m³" if unit else "")


def fmt_area(value_m2, places=DEC_VOLUME, unit=True, decimal_sep=","):
    s = _dec(value_m2, places, decimal_sep)
    return s + (u" m²" if unit else "")


def fmt_percent(factor, places=DEC_PERCENT, decimal_sep=","):
    """0.95 -> '95 %'"""
    s = _dec(float(factor) * 100.0, places, decimal_sep)
    return s + " %"


def fmt_triple(a, b, c, places=DEC_LENGTH, decimal_sep=","):
    """8.0, 2.4, 0.66 -> '8,00 x 2,40 x 0,66 m'"""
    return u"%s × %s × %s m" % (
        _dec(a, places, decimal_sep),
        _dec(b, places, decimal_sep),
        _dec(c, places, decimal_sep),
    )


def fmt_arrangement(count_length, count_width, count_height):
    """10, 3, 2 -> '10 x 3 x 2'"""
    return u"%d × %d × %d" % (int(count_length), int(count_width),
                                        int(count_height))


def fmt_bool(value):
    return "Ja" if value else "Nein"


# ---------------------------------------------------------------------------
# Beschriftungstext
# ---------------------------------------------------------------------------

def build_label_lines(data, enabled_fields, decimal_sep=","):
    """
    Baut die Zeilen der Beschriftung.

    data: dict mit
        rigole_id, rigole_type, system_name,
        total_length, total_width, total_height,
        basket_length, basket_width, basket_height,
        count_length, count_width, count_height,
        welded, storage_coefficient, v_speicher, ok, uk, load_class

    enabled_fields: dict {schluessel: bool} - siehe LABEL_FIELDS

    Rueckgabe: Liste von Zeilen (Leerstrings = Absatztrenner)
    """
    def on(key):
        return bool(enabled_fields.get(key, False))

    lines = []

    # --- Block 1: Kopfzeile ------------------------------------------------
    head = []
    if on("id"):
        head.append(str(data.get("rigole_id", "")))
    if on("art"):
        head.append(str(data.get("rigole_type", "")))
    if head:
        lines.append(u" – ".join([h for h in head if h]))
    if on("system"):
        lines.append(u"System: %s" % (data.get("system_name", ""),))

    # --- Block 2: Geometrie ------------------------------------------------
    block = []
    if on("gesamt"):
        block.append(u"Gesamt: " + fmt_triple(
            data.get("total_length", 0.0),
            data.get("total_width", 0.0),
            data.get("total_height", 0.0),
            decimal_sep=decimal_sep))
    if on("korb"):
        block.append(u"Korb: " + fmt_triple(
            data.get("basket_length", 0.0),
            data.get("basket_width", 0.0),
            data.get("basket_height", 0.0),
            decimal_sep=decimal_sep))
    if on("anordnung"):
        # "Rigole komplex" liefert einen fertigen Text mit - dort gibt es
        # keine Anzahl in Laengs- und Querrichtung, sondern eine Anzahl
        # belegter Korbplaetze je Lage.
        fertig = str(data.get("anordnung_text", "") or "").strip()
        block.append(u"Anordnung: " + (fertig if fertig else fmt_arrangement(
            data.get("count_length", 0),
            data.get("count_width", 0),
            data.get("count_height", 0))))
    if on("flaeche") and data.get("polygon_flaeche"):
        block.append(u"Flaeche: %s Polygon, davon %s belegt (%s)" % (
            fmt_area(data.get("polygon_flaeche", 0.0),
                     decimal_sep=decimal_sep),
            fmt_area(data.get("belegte_flaeche", 0.0),
                     decimal_sep=decimal_sep),
            fmt_percent(data.get("ausnutzung", 0.0),
                        decimal_sep=decimal_sep)))
    if on("verschweisst"):
        block.append(u"Verschweisst: " + fmt_bool(data.get("welded", False)))
    if block:
        if lines:
            lines.append("")
        lines.extend(block)

    # --- Block 3: Speicher -------------------------------------------------
    block = []
    if on("koeffizient"):
        block.append(u"Speicherkoeffizient: " + fmt_percent(
            data.get("storage_coefficient", 0.0), decimal_sep=decimal_sep))
    if on("speichervolumen"):
        block.append(u"Speichervolumen: " + fmt_volume(
            data.get("v_speicher", 0.0), decimal_sep=decimal_sep))
    if block:
        if lines:
            lines.append("")
        lines.extend(block)

    # --- Block 4: Hoehen ---------------------------------------------------
    block = []
    if on("ok"):
        block.append(u"OK Rigole: " + fmt_height(
            data.get("ok", 0.0), decimal_sep=decimal_sep))
    if on("uk"):
        block.append(u"UK Rigole: " + fmt_height(
            data.get("uk", 0.0), decimal_sep=decimal_sep))
    if block:
        if lines:
            lines.append("")
        lines.extend(block)

    # --- Block 5: Belastungsklasse ----------------------------------------
    if on("belastung"):
        if lines:
            lines.append("")
        lines.append(u"Belastungsklasse: %s" % (data.get("load_class", ""),))

    # --- Block 6: nur Kiesrigole ------------------------------------------
    # Diese Zeilen erscheinen nur, wenn auch Inhalt da ist. Bei der
    # Koerbe-Rigole bleiben die Werte leer und der Block entfaellt still.
    block = []
    if on("material") and str(data.get("material", "")).strip():
        block.append(u"Material: %s" % (data.get("material"),))
    if on("draenrohr") and str(data.get("draenrohr", "")).strip():
        block.append(u"Draenrohr: %s" % (data.get("draenrohr"),))
    if on("schacht") and str(data.get("schacht", "")).strip():
        block.append(u"Schaechte: %s" % (data.get("schacht"),))
    if block:
        if lines:
            lines.append("")
        lines.extend(block)

    return lines


def build_kies_label_data(ergebnis, rigole_id, rigole_type, system_name,
                          load_class="", decimal_sep=","):
    """
    Stellt die Werte fuer die Beschriftung einer KIESRIGOLE zusammen.

    Die Schluessel heissen genauso wie bei der Koerbe-Rigole, damit
    build_label_lines unveraendert benutzt werden kann. 'Gesamt' ist hier
    schlicht Laenge x Breite x Hoehe des Schuettkoerpers.
    """
    if ergebnis.hat_rohr:
        rohr = u"%s (Durchmesser %s, UK %s ueber Sohle, verlegt %s)" % (
            ergebnis.rohr_dn,
            fmt_length(ergebnis.rohr_durchmesser, places=3,
                       decimal_sep=decimal_sep),
            fmt_length(ergebnis.rohr_uk or 0.0, places=3,
                       decimal_sep=decimal_sep),
            fmt_length(ergebnis.rohr_laenge or 0.0, decimal_sep=decimal_sep))
    else:
        rohr = u"ohne"

    if ergebnis.hat_schacht:
        schacht = u"%d x %s, OK %s / UK %s" % (
            ergebnis.schacht_anzahl,
            ergebnis.schacht_dn,
            fmt_height(ergebnis.schacht_ok, decimal_sep=decimal_sep),
            fmt_height(ergebnis.schacht_uk, decimal_sep=decimal_sep))
    else:
        schacht = u""

    return {
        "rigole_id": rigole_id,
        "rigole_type": rigole_type,
        "system_name": system_name,
        "total_length": ergebnis.total_length,
        "total_width": ergebnis.total_width,
        "total_height": ergebnis.total_height,
        "storage_coefficient": ergebnis.storage_coefficient,
        "v_speicher": ergebnis.v_speicher,
        "ok": ergebnis.ok,
        "uk": ergebnis.uk,
        "load_class": load_class,
        "material": ergebnis.material or "",
        "draenrohr": rohr,
        "schacht": schacht,
        # Korbfelder bleiben leer - sie werden von der aufrufenden Schicht
        # ohnehin abgeschaltet.
        "basket_length": 0.0, "basket_width": 0.0, "basket_height": 0.0,
        "count_length": 0, "count_width": 0, "count_height": 0,
        "welded": False,
    }


def kies_label_fields(enabled_fields):
    """
    Passt die Beschriftungsauswahl an die Kiesrigole an: Korbabmessungen und
    Anordnung gibt es dort nicht, Material und Draenrohr dagegen schon.
    Die Entscheidung des Anwenders zu den uebrigen Feldern bleibt erhalten.
    """
    felder = dict(enabled_fields or {})
    felder["korb"] = False
    felder["anordnung"] = False
    felder["verschweisst"] = False
    felder["flaeche"] = False
    return felder


def rigole_label_fields(enabled_fields):
    """Umgekehrt: Material und Draenrohr gibt es bei den Koerben nicht."""
    felder = dict(enabled_fields or {})
    felder["material"] = False
    felder["draenrohr"] = False
    felder["flaeche"] = False
    # "schacht" bleibt: Kontrollschaechte gibt es seit dem 24.08.2026 auch
    # bei der Koerbe-Rigole. Die Zeile entfaellt von selbst, wenn keine da
    # sind - build_label_lines gibt leere Werte nicht aus.
    return felder


def polygon_label_fields(enabled_fields):
    """
    Beschriftungsauswahl fuer "Rigole komplex".

    Wie bei der Koerbe-Rigole - Material und Draenrohr gibt es nicht -,
    aber die Flaechenzeile bleibt erlaubt.
    """
    felder = dict(enabled_fields or {})
    felder["material"] = False
    felder["draenrohr"] = False
    return felder


def build_label_text(data, enabled_fields, decimal_sep=",", newline="\n"):
    """
    Fertiger Beschriftungstext.

    HINWEIS fuer die VW-Schicht: vs.CreateText erwartet einen String;
    fuer den Zeilenumbruch innerhalb eines VW-Textobjekts wird ueblicherweise
    vs.Chr(13) verwendet. Deshalb ist newline hier parametrierbar
    -> in geometry/labeling wird build_label_text(..., newline=vs.Chr(13))
    aufgerufen. ZU PRUEFEN in VW 2026 (siehe Architekturdokument, Punkt U6).
    """
    return newline.join(build_label_lines(data, enabled_fields,
                                          decimal_sep=decimal_sep))


def label_field_defaults():
    return dict((k, d) for (k, _t, d) in LABEL_FIELDS)
