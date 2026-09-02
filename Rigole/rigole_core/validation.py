# -*- coding: utf-8 -*-
"""
Eingabepruefung des Rigolen-Tools.

Kein "import vs" -> ausserhalb von Vectorworks testbar.
Alle Meldungen sind deutschsprachig und direkt anzeigefertig
(vs.AlrtDialog erwartet einen fertigen String).

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

from rigole_config.constants import (
    MIN_DIMENSION, MAX_DIMENSION,
    MAX_BASKETS_TOTAL, WARN_BASKETS_TOTAL,
    MIN_ELEVATION, MAX_ELEVATION,
    HEIGHT_MODE_OK, HEIGHT_MODE_UK,
    LENGTH_MODE_COUNT, LENGTH_MODE_TOTAL,
    LENGTH_EPS,
)
from rigole_core.calculations import (
    total_basket_count, schacht_positionen, pipe_segments,
)


class ValidationIssue(object):
    """severity: 'error' blockiert, 'warning' erlaubt Fortfahren."""

    def __init__(self, field, message, severity="error"):
        self.field = field
        self.message = message
        self.severity = severity

    @property
    def is_error(self):
        return self.severity == "error"

    def __repr__(self):
        return "ValidationIssue(%r, %r, %r)" % (self.field, self.message, self.severity)

    def __str__(self):
        return self.message


class ValidationResult(object):

    def __init__(self, issues=None):
        self.issues = list(issues or [])

    def add(self, field, message, severity="error"):
        self.issues.append(ValidationIssue(field, message, severity))

    @property
    def errors(self):
        return [i for i in self.issues if i.is_error]

    @property
    def warnings(self):
        return [i for i in self.issues if not i.is_error]

    @property
    def ok(self):
        return len(self.errors) == 0

    def message_text(self, include_warnings=True):
        """Fertiger Text fuer vs.AlrtDialog."""
        lines = []
        if self.errors:
            lines.append("Bitte korrigieren Sie folgende Eingaben:")
            lines.append("")
            for i in self.errors:
                lines.append(u"• " + i.message)
        if include_warnings and self.warnings:
            if lines:
                lines.append("")
            lines.append("Hinweise:")
            lines.append("")
            for i in self.warnings:
                lines.append(u"• " + i.message)
        return "\n".join(lines)

    def __repr__(self):
        return "ValidationResult(errors=%d, warnings=%d)" % (
            len(self.errors), len(self.warnings))


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _check_dimension(result, field, label, value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        result.add(field, u"%s: kein gueltiger Zahlenwert." % label)
        return None
    if v <= 0.0:
        result.add(field, u"%s muss groesser als 0 sein (eingegeben: %s)." % (label, value))
        return None
    if v < MIN_DIMENSION:
        result.add(field, u"%s ist unrealistisch klein (< %.4f m)." % (label, MIN_DIMENSION))
        return None
    if v > MAX_DIMENSION:
        result.add(field, u"%s ist unrealistisch gross (> %.0f m)." % (label, MAX_DIMENSION))
        return None
    return v


def _check_count(result, field, label, value):
    try:
        n = int(value)
    except (TypeError, ValueError):
        result.add(field, u"%s: kein gueltiger ganzzahliger Wert." % label)
        return None
    if n < 1:
        result.add(field, u"%s muss mindestens 1 betragen (eingegeben: %s)." % (label, value))
        return None
    return n


# ---------------------------------------------------------------------------
# Hauptpruefung
# ---------------------------------------------------------------------------

def _catalog_warning(result, parameters):
    from rigole_config.basket_types import get_basket_type, note_for, CUSTOM_BASKET_KEY
    key = parameters.get("basket_key") or parameters.get("rigole_type")
    data = get_basket_type(key)
    if data is not None:
        text = note_for(key)
        if key == CUSTOM_BASKET_KEY:
            text += " Speicherkoeffizient und Maße müssen eigenständig geprüft werden."
        result.add(
            "basket_key", "%s\nEingestellter Speicheranteil: %s %%. "
            "Keine hydraulische oder statische Bemessung. "
            "Nur nach Prüfung anhand der aktuellen Herstellerunterlagen fortfahren."
            % (text, parameters.get("storage_percent", "?")), "warning")


def validate_parameters(p):
    """
    p ist ein dict mit den Dialogwerten (Laengen in Metern):

        rigole_type          str
        system_name          str
        basket_length        float (m)
        basket_width         float (m)
        basket_height        float (m)
        length_mode          'count' | 'total'
        count_length         int   (nur bei length_mode == 'count')
        target_length        float (nur bei length_mode == 'total', m)
        count_width          int
        count_height         int
        storage_percent      float (Prozent, 0 < x <= 100)
        height_mode          'OK' | 'UK'
        height_value         float (m)
        symbol_name          str
        symbol_exists        bool   (von der VW-Schicht gesetzt)
        load_class           str
        welded               bool

    Rueckgabe: ValidationResult
    """
    r = ValidationResult()

    _catalog_warning(r, p)
    # --- Bezeichnung -------------------------------------------------------
    if not str(p.get("system_name", "")).strip():
        r.add("system_name", u"Die Systembezeichnung darf nicht leer sein.")

    if not str(p.get("rigole_type", "")).strip():
        r.add("rigole_type",
              u"Es wurde kein Hersteller / System gewaehlt.")

    # --- Korbabmessungen ---------------------------------------------------
    bl = _check_dimension(r, "basket_length", u"Korblaenge", p.get("basket_length"))
    bw = _check_dimension(r, "basket_width", u"Korbbreite", p.get("basket_width"))
    bh = _check_dimension(r, "basket_height", u"Korbhoehe", p.get("basket_height"))

    # --- Anordnung ---------------------------------------------------------
    cw = _check_count(r, "count_width", u"Anzahl Koerbe nebeneinander", p.get("count_width"))
    ch = _check_count(r, "count_height", u"Anzahl Koerbe uebereinander", p.get("count_height"))

    length_mode = p.get("length_mode", LENGTH_MODE_COUNT)
    cl = None
    if length_mode == LENGTH_MODE_COUNT:
        cl = _check_count(r, "count_length", u"Anzahl Koerbe hintereinander", p.get("count_length"))
    elif length_mode == LENGTH_MODE_TOTAL:
        tl = p.get("target_length")
        try:
            tlf = float(tl)
        except (TypeError, ValueError):
            r.add("target_length", u"Gesamtlaenge: kein gueltiger Zahlenwert.")
            tlf = None
        if tlf is not None:
            if tlf <= 0.0:
                r.add("target_length", u"Die gewuenschte Gesamtlaenge muss groesser als 0 sein.")
            elif bl is not None and tlf < bl - 1e-9:
                r.add("target_length",
                      u"Die gewuenschte Gesamtlaenge (%.3f m) ist kleiner als ein "
                      u"einzelner Korb (%.3f m)." % (tlf, bl))
        # count_length wird erst nach der Rundungsentscheidung gesetzt
        cl = p.get("count_length")
        if cl is not None:
            cl = _check_count(r, "count_length", u"Anzahl Koerbe hintereinander", cl)
    else:
        r.add("length_mode", u"Unbekannter Berechnungsmodus fuer die Laengsrichtung.")

    # --- Anzahl gesamt -----------------------------------------------------
    if cl and cw and ch:
        n = total_basket_count(cl, cw, ch)
        if n > MAX_BASKETS_TOTAL:
            r.add("count_total",
                  u"Die Rigole haette %d Koerbe. Das Maximum liegt bei %d. "
                  u"Bitte teilen Sie die Anlage auf mehrere Rigolen auf."
                  % (n, MAX_BASKETS_TOTAL))
        elif n > WARN_BASKETS_TOTAL:
            r.add("count_total",
                  u"Die Rigole besteht aus %d Koerben. Der Aufbau kann einen "
                  u"Moment dauern." % n, severity="warning")

    # --- Speicherkoeffizient ----------------------------------------------
    sp = p.get("storage_percent")
    try:
        spf = float(sp)
    except (TypeError, ValueError):
        r.add("storage_percent", u"Speicherkoeffizient: kein gueltiger Zahlenwert.")
        spf = None
    if spf is not None:
        if spf <= 0.0:
            r.add("storage_percent", u"Der Speicherkoeffizient muss groesser als 0 % sein.")
        elif spf > 100.0:
            r.add("storage_percent",
                  u"Der Speicherkoeffizient darf hoechstens 100 %% betragen "
                  u"(eingegeben: %s %%)." % (sp,))

    # --- Hoehen ------------------------------------------------------------
    height_mode = p.get("height_mode")
    if height_mode not in (HEIGHT_MODE_OK, HEIGHT_MODE_UK):
        r.add("height_mode", u"Es wurde kein gueltiger Hoehenbezug gewaehlt.")
    hv = p.get("height_value")
    try:
        hvf = float(hv)
    except (TypeError, ValueError):
        r.add("height_value", u"Hoehenwert: kein gueltiger Zahlenwert.")
        hvf = None
    if hvf is not None and not (MIN_ELEVATION <= hvf <= MAX_ELEVATION):
        r.add("height_value",
              u"Der Hoehenwert %.3f m liegt ausserhalb des plausiblen Bereichs "
              u"(%.0f m bis %.0f m)." % (hvf, MIN_ELEVATION, MAX_ELEVATION))

    # --- Symbol ------------------------------------------------------------
    # Das Symbol gehoert zum Korbtyp und wird nicht mehr im Dialog gewaehlt.
    # Geprueft wird deshalb nur noch, wenn ueberhaupt 3D erzeugt werden soll.
    korbtyp = str(p.get("basket_key", "")).strip()
    sym = str(p.get("symbol_name", "")).strip()

    if p.get("draw_3d"):
        if not sym:
            r.add("symbol_name",
                  u"Fuer den Korbtyp „%s“ konnte kein Symbolname gebildet "
                  u"werden. Bitte die Korbabmessungen pruefen." % (korbtyp,))
        elif p.get("symbol_exists") is False:
            # Kommt nur noch vor, wenn die Symbolerzeugung fehlgeschlagen ist.
            r.add("symbol_name",
                  u"Das Symbol „%s“ (Korbtyp „%s“) steht nicht zur "
                  u"Verfuegung." % (sym, korbtyp))

    # --- Kontrollschaechte -------------------------------------------------
    _pruefe_korb_schaechte(r, p, bl, bw, hvf)

    if not p.get("draw_2d") and not p.get("draw_3d"):
        r.add("darstellung",
              u"Es ist weder eine 2D- noch eine 3D-Darstellung ausgewaehlt. "
              u"Es gaebe nichts zu zeichnen.")

    return r


def _pruefe_korb_schaechte(r, p, basket_length, basket_width, hoehenwert):
    """
    Kontrollschaechte der KOERBE-Rigole.

    Sie sitzen mittig auf der Oberkante eines Rigolenkorbes; ihre Unterkante
    ist damit die Oberkante der Rigole. Zu pruefen sind deshalb nur der
    Durchmesser (passt er auf einen Korb?) und die Oberkante.
    """
    if not p.get("mit_schacht"):
        return

    try:
        schacht_d = float(p.get("schacht_durchmesser") or 0.0)
    except (TypeError, ValueError):
        schacht_d = 0.0
    if schacht_d <= 0.0:
        r.add("schacht_dn", u"Es wurde kein Schachtdurchmesser gewaehlt.")
        return

    # Der Schacht sitzt MITTIG auf einem Korb. Ist er groesser als der Korb,
    # kragt er ueber dessen Rand aus - moeglich, aber erwaehnenswert.
    korb = None
    if basket_length is not None and basket_width is not None:
        korb = min(basket_length, basket_width)
    if korb is not None and schacht_d > korb + LENGTH_EPS:
        r.add("schacht_dn",
              u"Der Schacht (%.3f m) ist groesser als ein Rigolenkorb "
              u"(%.3f m) und kragt ueber dessen Rand aus."
              % (schacht_d, korb), "warning")

    schacht_ok = p.get("schacht_ok")
    try:
        schacht_ok = float(schacht_ok)
    except (TypeError, ValueError):
        r.add("schacht_ok", u"Oberkante Schacht: kein gueltiger Zahlenwert.")
        return

    if not (MIN_ELEVATION <= schacht_ok <= MAX_ELEVATION):
        r.add("schacht_ok",
              u"Die Oberkante Schacht %.3f m liegt ausserhalb des plausiblen "
              u"Bereichs (%.0f m bis %.0f m)."
              % (schacht_ok, MIN_ELEVATION, MAX_ELEVATION))
        return

    if hoehenwert is None:
        return

    # Unterkante Schacht = Oberkante Rigole.
    if p.get("height_mode") == HEIGHT_MODE_OK:
        ok_rigole = hoehenwert
    else:
        try:
            ok_rigole = hoehenwert + float(p.get("basket_height") or 0.0) \
                * int(p.get("count_height") or 0)
        except (TypeError, ValueError):
            return

    if schacht_ok <= ok_rigole + LENGTH_EPS:
        r.add("schacht_ok",
              u"Die Oberkante Schacht (%.3f m) liegt nicht ueber der "
              u"Oberkante der Rigole (%.3f m) - der Schacht haette keine "
              u"Bauhoehe." % (schacht_ok, ok_rigole))


def _pruefe_schaechte(r, p, laenge, breite, hoehe, rohr_d, hoehenwert):
    """
    Prueft die Angaben zu den Kontrollschaechten.

    Ohne Draenrohr gibt es keine Schaechte - die Pruefung entfaellt dann
    vollstaendig, damit niemand wegen eines Feldes aufgehalten wird, das in
    seinem Fall gar keine Rolle spielt.
    """
    if not p.get("kies_mit_schacht"):
        return
    if rohr_d <= 0.0:
        # Kein Rohr, also auch keine Schaechte. Das ist kein Fehler, sondern
        # nur ein Hinweis - das Werkzeug zeichnet dann eben keine.
        r.add("kies_schacht", u"Ohne Draenrohr werden keine Kontrollschaechte gesetzt.", "warning")
        return

    try:
        schacht_d = float(p.get("kies_schacht_durchmesser") or 0.0)
    except (TypeError, ValueError):
        schacht_d = 0.0
    if schacht_d <= 0.0:
        r.add("kies_schacht_dn", u"Es wurde kein Schachtdurchmesser gewaehlt.")
        return

    try:
        rand = float(p.get("kies_schacht_rand", 0.20))
    except (TypeError, ValueError):
        rand = 0.20

    # --- Passt der Schacht seitlich in die Rigole? ------------------------
    # Die Schachtachse liegt auf der Draenrohrachse, also in der Mitte der
    # Breite. Seitlich verschieben laesst er sich deshalb nicht - der
    # geforderte Rand wird hier zur Anforderung an die BREITE.
    if breite is not None:
        seitlich = (breite - schacht_d) / 2.0
        if seitlich < -LENGTH_EPS:
            r.add("kies_schacht_dn",
                  u"Der Schacht (%.3f m) ist breiter als die Kiesrigole "
                  u"(%.3f m) und ragt seitlich heraus." % (schacht_d, breite),
                  "warning")
        elif seitlich < rand - LENGTH_EPS:
            r.add("kies_schacht_dn",
                  u"Seitlich bleiben nur %.3f m zwischen Schacht und Rand der "
                  u"Schuettung statt der geforderten %.3f m. Fuer diesen "
                  u"Schacht waeren mindestens %.3f m Breite noetig."
                  % (seitlich, rand, schacht_d + 2.0 * rand), "warning")

    # --- Passen zwei Schaechte ueberhaupt in die Laenge? ------------------
    if laenge is not None:
        positionen = schacht_positionen(laenge, schacht_d, rand)
        if not positionen:
            r.add("kies_schacht_dn",
                  u"Die Kiesrigole ist mit %.3f m zu kurz fuer zwei Schaechte "
                  u"mit %.3f m Durchmesser und %.3f m Randabstand. Noetig "
                  u"waeren mehr als %.3f m."
                  % (laenge, schacht_d, rand, schacht_d + 2.0 * rand))
        else:
            segmente = pipe_segments(positionen, schacht_d)
            if not segmente:
                r.add("kies_schacht_dn",
                      u"Zwischen den Schaechten bleibt kein Platz fuer das "
                      u"Draenrohr. Bitte die Rigole verlaengern oder einen "
                      u"kleineren Schacht waehlen.")

    # --- Hoehenlage --------------------------------------------------------
    try:
        rohr_uk = float(p.get("kies_rohr_uk") or 0.0)
    except (TypeError, ValueError):
        rohr_uk = 0.0
    try:
        tiefe = float(p.get("kies_schacht_tiefe", 0.20))
    except (TypeError, ValueError):
        tiefe = 0.20

    schacht_ok = p.get("kies_schacht_ok")
    try:
        schacht_ok = float(schacht_ok)
    except (TypeError, ValueError):
        r.add("kies_schacht_ok", u"Oberkante Schacht: kein gueltiger Zahlenwert.")
        return

    if not (MIN_ELEVATION <= schacht_ok <= MAX_ELEVATION):
        r.add("kies_schacht_ok",
              u"Die Oberkante Schacht %.3f m liegt ausserhalb des plausiblen "
              u"Bereichs (%.0f m bis %.0f m)."
              % (schacht_ok, MIN_ELEVATION, MAX_ELEVATION))
        return

    if hoehenwert is None or hoehe is None:
        return

    if p.get("height_mode") == HEIGHT_MODE_OK:
        ok_rigole = hoehenwert
        uk_rigole = hoehenwert - hoehe
    else:
        uk_rigole = hoehenwert
        ok_rigole = hoehenwert + hoehe

    schacht_uk = uk_rigole + rohr_uk - tiefe
    if schacht_ok <= schacht_uk + LENGTH_EPS:
        r.add("kies_schacht_ok",
              u"Die Oberkante Schacht (%.3f m) liegt nicht ueber seiner "
              u"Unterkante (%.3f m = UK Rigole %.3f m + %.3f m UK Rohr "
              u"- %.3f m Sumpf)."
              % (schacht_ok, schacht_uk, uk_rigole, rohr_uk, tiefe))
    elif schacht_ok < ok_rigole - LENGTH_EPS:
        r.add("kies_schacht_ok",
              u"Die Oberkante Schacht (%.3f m) liegt unter der Oberkante der "
              u"Kiesrigole (%.3f m) - der Schacht endet damit im Kies."
              % (schacht_ok, ok_rigole), "warning")


def validate_kies_parameters(p):
    """
    Eingabepruefung fuer die KIESRIGOLE.

    p ist ein dict mit (Laengen in Metern):
        rigole_type, system_name
        kies_laenge, kies_breite, kies_hoehe
        kies_material
        storage_percent
        kies_rohr_dn, kies_rohr_durchmesser, kies_rohr_uk
        height_mode, height_value
        draw_2d, draw_3d
    """
    r = ValidationResult()
    from rigole_config.kies_types import note_for_material, note_for_rohr
    notes = [note_for_material(p.get("kies_material")),
             note_for_rohr(p.get("kies_rohr_dn"))]
    r.add("storage_percent", "\n".join(note for note in notes if note) +
          "\nSpeicheranteil und Rohrmaße anhand der Herstellerunterlagen prüfen. "
          "Die Volumenberechnung ersetzt keine hydraulische Bemessung.", "warning")

    if not str(p.get("system_name", "")).strip():
        r.add("system_name", u"Die Systembezeichnung darf nicht leer sein.")

    laenge = _check_dimension(r, "kies_laenge", u"Laenge", p.get("kies_laenge"))
    breite = _check_dimension(r, "kies_breite", u"Breite", p.get("kies_breite"))
    hoehe = _check_dimension(r, "kies_hoehe", u"Hoehe", p.get("kies_hoehe"))

    if not str(p.get("kies_material", "")).strip():
        r.add("kies_material", u"Es wurde kein Fuellmaterial gewaehlt.")

    # --- Speicherkoeffizient ----------------------------------------------
    sp = p.get("storage_percent")
    try:
        spf = float(sp)
    except (TypeError, ValueError):
        r.add("storage_percent", u"Speicherkoeffizient: kein gueltiger Zahlenwert.")
        spf = None
    if spf is not None:
        if spf <= 0.0:
            r.add("storage_percent",
                  u"Der Speicherkoeffizient muss groesser als 0 %% sein.")
        elif spf > 100.0:
            r.add("storage_percent",
                  u"Der Speicherkoeffizient darf hoechstens 100 %% betragen "
                  u"(eingegeben: %s %%)." % (sp,))

    # --- Draenrohr ---------------------------------------------------------
    try:
        rohr_d = float(p.get("kies_rohr_durchmesser") or 0.0)
    except (TypeError, ValueError):
        rohr_d = 0.0
        r.add("kies_rohr_dn", u"Draenrohr: kein gueltiger Durchmesser.")

    if rohr_d > 0.0:
        if breite is not None and rohr_d >= breite:
            r.add("kies_rohr_dn",
                  u"Das Draenrohr (%.3f m) ist so breit wie die Rigole selbst "
                  u"(%.3f m) oder breiter." % (rohr_d, breite))
        if hoehe is not None and rohr_d >= hoehe:
            r.add("kies_rohr_dn",
                  u"Das Draenrohr (%.3f m) ist so hoch wie die Rigole selbst "
                  u"(%.3f m) oder hoeher." % (rohr_d, hoehe))

        # Eingegeben wird der Abstand der ROHRUNTERKANTE zur Sohle.
        # Nach unten kann das Rohr damit gar nicht mehr herausragen; zu
        # pruefen bleibt nur, ob es oben noch in die Rigole passt.
        try:
            rohr_uk = float(p.get("kies_rohr_uk") or 0.0)
        except (TypeError, ValueError):
            rohr_uk = 0.0
            r.add("kies_rohr_uk",
                  u"Abstand der Rohrunterkante zur Sohle: kein gueltiger Wert.")
        if rohr_uk < 0.0:
            r.add("kies_rohr_uk",
                  u"Der Abstand der Rohrunterkante zur Sohle darf nicht "
                  u"negativ sein. 0 bedeutet aufliegend.")
        elif hoehe is not None and rohr_uk + rohr_d > hoehe + 1e-9:
            r.add("kies_rohr_uk",
                  u"Bei einem Abstand von %.3f m ragt das Rohr oben aus der "
                  u"Rigole heraus: %.3f m + %.3f m Rohr = %.3f m, die Rigole "
                  u"ist aber nur %.3f m hoch."
                  % (rohr_uk, rohr_uk, rohr_d, rohr_uk + rohr_d, hoehe))

    # --- Hoehen ------------------------------------------------------------
    height_mode = p.get("height_mode")
    if height_mode not in (HEIGHT_MODE_OK, HEIGHT_MODE_UK):
        r.add("height_mode", u"Es wurde kein gueltiger Hoehenbezug gewaehlt.")
    hv = p.get("height_value")
    try:
        hvf = float(hv)
    except (TypeError, ValueError):
        r.add("height_value", u"Hoehenwert: kein gueltiger Zahlenwert.")
        hvf = None
    if hvf is not None and not (MIN_ELEVATION <= hvf <= MAX_ELEVATION):
        r.add("height_value",
              u"Der Hoehenwert %.3f m liegt ausserhalb des plausiblen Bereichs "
              u"(%.0f m bis %.0f m)." % (hvf, MIN_ELEVATION, MAX_ELEVATION))

    # --- Kontrollschaechte -------------------------------------------------
    _pruefe_schaechte(r, p, laenge, breite, hoehe, rohr_d, hvf)

    if not p.get("draw_2d") and not p.get("draw_3d"):
        r.add("darstellung",
              u"Es ist weder eine 2D- noch eine 3D-Darstellung ausgewaehlt. "
              u"Es gaebe nichts zu zeichnen.")

    return r


def validate_kies_computed(result_obj):
    """Plausibilitaetspruefung nach der Berechnung einer Kiesrigole."""
    r = ValidationResult()
    if result_obj is None:
        r.add("result", u"Die Berechnung hat kein Ergebnis geliefert.")
        return r

    if (result_obj.total_length <= 0 or result_obj.total_width <= 0
            or result_obj.total_height <= 0):
        r.add("total", u"Die Abmessungen der Kiesrigole sind nicht plausibel.")

    if result_obj.v_brutto <= 0:
        r.add("volume", u"Das berechnete Bruttovolumen ist 0 oder negativ.")

    if result_obj.v_speicher > result_obj.v_brutto + 1e-9:
        r.add("volume", u"Das Speichervolumen ist groesser als das "
                        u"Bruttovolumen. Bitte den Hohlraumanteil pruefen.")

    if abs((result_obj.ok - result_obj.uk) - result_obj.total_height) > 1e-6:
        r.add("heights", u"Ober- und Unterkante passen nicht zur Hoehe.")

    return r


def validate_computed(result_obj):
    """
    Plausibilitaetspruefung NACH der Berechnung (letzte Sicherung vor der
    Geometrieerzeugung).
    """
    r = ValidationResult()
    if result_obj is None:
        r.add("result", u"Die Berechnung hat kein Ergebnis geliefert.")
        return r

    if result_obj.total_length <= 0 or result_obj.total_width <= 0 \
            or result_obj.total_height <= 0:
        r.add("total", u"Die berechneten Gesamtmasse sind nicht plausibel "
                       u"(ein Mass ist 0 oder negativ).")

    if result_obj.v_brutto <= 0:
        r.add("volume", u"Das berechnete Bruttovolumen ist 0 oder negativ.")

    if result_obj.v_speicher > result_obj.v_brutto + 1e-9:
        r.add("volume", u"Das Speichervolumen ist groesser als das Bruttovolumen. "
                        u"Bitte pruefen Sie den Speicherkoeffizienten.")

    if abs((result_obj.ok - result_obj.uk) - result_obj.total_height) > 1e-6:
        r.add("heights", u"Ober- und Unterkante passen nicht zur Gesamthoehe.")

    return r


# ===========================================================================
# RIGOLE KOMPLEX (26.08.2026)
# ===========================================================================

def validate_polygon_parameters(p):
    """
    Pruefung der Dialogwerte des Werkzeugs "Rigole komplex".

    Gegenueber der rechteckigen Rigole entfaellt alles, was mit Anzahl in
    Laengs- und Querrichtung zu tun hat; dafuer kommt die Umgrenzung dazu.

    Rueckgabe: ValidationResult
    """
    from rigole_config.constants import POLY_MAX_KOERBE

    r = ValidationResult()
    _catalog_warning(r, p)

    if not str(p.get("system_name", "")).strip():
        r.add("system_name", u"Die Systembezeichnung darf nicht leer sein.")
    if not str(p.get("rigole_type", "")).strip():
        r.add("rigole_type",
              u"Es wurde kein Hersteller / System gewaehlt.")

    _check_dimension(r, "basket_length", u"Korblaenge", p.get("basket_length"))
    _check_dimension(r, "basket_width", u"Korbbreite", p.get("basket_width"))
    _check_dimension(r, "basket_height", u"Korbhoehe", p.get("basket_height"))
    _check_count(r, "count_height", u"Anzahl Koerbe uebereinander",
                 p.get("count_height"))

    # --- Umgrenzung --------------------------------------------------------
    punkte = p.get("polygon") or []
    if len(punkte) < 3:
        r.add("polygon", u"Es liegt keine brauchbare Umgrenzung vor - das "
                         u"Polygon braucht mindestens drei Eckpunkte.")
    else:
        from rigole_core import polygon as poly
        if poly.flaeche(punkte) <= 0.0:
            r.add("polygon", u"Die Umgrenzung hat keine Flaeche.")

    # --- Rasterwinkel ------------------------------------------------------
    try:
        winkel = float(p.get("raster_winkel") or 0.0)
    except (TypeError, ValueError):
        r.add("raster_winkel", u"Rasterwinkel: kein gueltiger Zahlenwert.")
        winkel = 0.0
    if abs(winkel) > 360.0:
        r.add("raster_winkel",
              u"Der Rasterwinkel muss zwischen -360 und 360 Grad liegen.")

    # --- Speicherkoeffizient ----------------------------------------------
    try:
        prozent = float(p.get("storage_percent"))
    except (TypeError, ValueError):
        r.add("storage_percent",
              u"Speicherkoeffizient: kein gueltiger Zahlenwert.")
        prozent = None
    if prozent is not None and not (0.0 < prozent <= 100.0):
        r.add("storage_percent",
              u"Der Speicherkoeffizient muss groesser als 0 % und hoechstens "
              u"100 % sein.")

    # --- Hoehenlage --------------------------------------------------------
    if p.get("height_mode") not in (HEIGHT_MODE_OK, HEIGHT_MODE_UK):
        r.add("height_mode", u"Unbekannter Hoehenbezug.")
    try:
        float(p.get("height_value"))
    except (TypeError, ValueError):
        r.add("height_value", u"Hoehe: kein gueltiger Zahlenwert.")

    # --- Darstellung -------------------------------------------------------
    if not p.get("draw_2d") and not p.get("draw_3d"):
        r.add("draw", u"Es ist weder eine 2D- noch eine 3D-Darstellung "
                      u"ausgewaehlt. Es gaebe nichts zu zeichnen.")

    if not str(p.get("symbol_name", "")).strip():
        r.add("symbol_name",
              u"Aus den Korbmassen liess sich kein Symbolname bilden.")

    # --- Schaechte ---------------------------------------------------------
    if p.get("mit_schacht"):
        try:
            d = float(p.get("schacht_durchmesser") or 0.0)
        except (TypeError, ValueError):
            d = 0.0
        if d <= 0.0:
            r.add("schacht_dn", u"Es wurde kein Schachtdurchmesser gewaehlt.")
        try:
            ok_schacht = float(p.get("schacht_ok"))
        except (TypeError, ValueError):
            r.add("schacht_ok", u"OK Schacht: kein gueltiger Zahlenwert.")
            ok_schacht = None
        if ok_schacht is not None and p.get("height_mode") == HEIGHT_MODE_OK:
            try:
                if ok_schacht <= float(p.get("height_value")):
                    r.add("schacht_ok",
                          u"Die Schachtoberkante liegt nicht ueber der "
                          u"Rigolenoberkante - der Schacht haette keine "
                          u"Hoehe.", "warning")
            except (TypeError, ValueError):
                pass

    # --- Groessenordnung ---------------------------------------------------
    # Nur eine Warnung: Wie viele Koerbe es wirklich werden, weiss erst die
    # Belegung. Der Dialog zeigt die Zahl vorher an.
    if len(punkte) >= 3:
        from rigole_core import polygon as poly
        try:
            grobe_zahl = int(poly.flaeche(punkte)
                             / (float(p.get("basket_length"))
                                * float(p.get("basket_width")))
                             * int(p.get("count_height")))
        except (TypeError, ValueError, ZeroDivisionError):
            grobe_zahl = 0
        if grobe_zahl > POLY_MAX_KOERBE:
            r.add("count_total",
                  u"Die Umgrenzung fasst ueberschlaegig %d Koerbe. Ab etwa "
                  u"%d dauert das Erzeugen spuerbar und die Datei wird gross."
                  % (grobe_zahl, POLY_MAX_KOERBE), "warning")

    return r


def validate_polygon_computed(result_obj):
    """Plausibilitaetspruefung nach der Belegung."""
    r = ValidationResult()
    if result_obj is None:
        r.add("result", u"Die Berechnung hat kein Ergebnis geliefert.")
        return r

    if not getattr(result_obj, "zellen", None):
        r.add("zellen",
              u"In die Umgrenzung passt kein einziger vollstaendiger Korb.\n\n"
              u"Moeglichkeiten: kleinere Rigolenkoerper waehlen, die Koerbe "
              u"quer stellen, eine andere Rasterausrichtung waehlen oder das "
              u"Polygon vergroessern.")
        return r

    if result_obj.v_brutto <= 0:
        r.add("volume", u"Das berechnete Bruttovolumen ist 0 oder negativ.")

    if result_obj.v_speicher > result_obj.v_brutto + 1e-9:
        r.add("volume", u"Das Speichervolumen ist groesser als das "
                        u"Bruttovolumen. Bitte den Speicherkoeffizienten "
                        u"pruefen.")

    if abs((result_obj.ok - result_obj.uk) - result_obj.total_height) > 1e-6:
        r.add("heights", u"Ober- und Unterkante passen nicht zur Gesamthoehe.")

    if result_obj.belegte_flaeche > result_obj.polygon_flaeche + 1e-6:
        r.add("flaeche", u"Die belegte Flaeche ist groesser als die "
                         u"Polygonflaeche - das kann nicht sein.")

    return r
