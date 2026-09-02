"""Native, staged inputs: geometry, path, appearance and 3D orientation."""

from dataclasses import replace

import vs

from PD_Treppe import VERSION
from ..core.stair import DEFAULT_NOTE, StairError, calculate, german, number

INIT = 12255
NUMERIC = {
    14: "lower_m", 16: "upper_m", 18: "count", 20: "width_m",
    22: "requested_rise_cm", 25: "going_cm",
}


def _title(value):
    return "%s | v%s | manufactured by Dirk D." % (value, VERSION)


def _run(dialog, handler):
    if not vs.VerifyLayout(dialog):
        raise StairError("Der Treppendialog konnte nicht sicher aufgebaut werden.")
    return vs.RunLayoutDialog(dialog, handler)


def _row(dialog, previous, label_id, field_id, label, value):
    vs.CreateStaticText(dialog, label_id, label, 36)
    vs.CreateEditText(dialog, field_id, str(value).replace(".", ","), 16)
    vs.SetBelowItem(dialog, previous, label_id, 0, 3)
    vs.SetRightItem(dialog, label_id, field_id, 0, 0)


def _preview(result):
    import math

    angle = math.degrees(math.atan2(result.rise_m, result.going_m))
    step_length = 2 * result.rise_m + result.going_m
    return (
        f"{result.steps} Stufen · Steigung {german(result.rise_m * 100, 3)} cm · "
        f"Auftritt {german(result.going_m * 100, 3)} cm\r"
        f"{result.treads} Auftritte · Länge {german(result.length_m, 3)} m · "
        f"Oberkante {german(result.upper_m, 3)} m\r"
        f"Treppenwinkel {german(angle, 2)}° · Schrittmaß 2S+A "
        f"{german(step_length * 100, 2)} cm"
    )


def source_mode():
    """Choose between an explicit source-path pick and straight insertion."""
    answer = vs.AlertQuestion(
        "Soll die Treppe an einer vorhandenen Lauflinie entwickelt werden?",
        "Linie, Polylinie oder Polygon können direkt gewählt werden. Die Quelle bleibt "
        "unverändert. Alternativ wird eine gerade Treppe frei eingesetzt.",
        1, "Lauflinie auswählen", "Abbrechen", "Gerade Treppe", "")
    return {1: "path", 2: "straight"}.get(int(answer))


def confirm_preview(result):
    """Confirm the visible dashed preview or return to all edit stages."""
    answer = vs.AlertQuestion(
        "Ist der gestrichelt dargestellte Treppenlauf korrekt?",
        _preview(result).replace("\r", "\n") + "\n"
        "Die Vorschau ist nur vorübergehend. Mit Korrigieren können alle Eingaben "
        "erneut geändert werden.",
        1, "Treppe anlegen", "Abbrechen", "Korrigieren", "")
    return {1: "accept", 2: "edit"}.get(int(answer), "cancel")


def geometry(initial):
    state = {"result": None}
    dialog = vs.CreateResizableLayout(_title("PD Treppe – 1/4 Abmessungen"), True,
                                      "Weiter", "Abbrechen", True, False)
    vs.CreateStaticText(dialog, 10, "Höhen in m · Steigung und Auftritt in cm", 64)
    vs.CreatePullDownMenu(dialog, 11, 48)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.SetBelowItem(dialog, 10, 11, 0, 4)
    previous = 11
    labels = ("Unterkante [m]", "Oberkante [m]", "Gewünschte Stufenzahl",
              "Breite [m]", "Gewünschte Steigung [12–17 cm]")
    for field, label in zip((14, 16, 18, 20, 22), labels):
        _row(dialog, previous, field - 1, field, label, initial.to_dict()[NUMERIC[field]])
        previous = field - 1
    vs.CreateCheckBox(dialog, 23, "Auftritt automatisch: 63 cm − 2 × tatsächliche Steigung")
    vs.SetBelowItem(dialog, previous, 23, 0, 5)
    _row(dialog, 23, 24, 25, "Auftritt [cm] – Vorschlag ist änderbar", initial.going_cm)
    vs.CreateCheckBox(dialog, 26, "Oberen Auftritt mitzeichnen (sonst Anschluss an Podest)")
    vs.SetBelowItem(dialog, 24, 26, 0, 4)
    vs.CreatePushButton(dialog, 27, "Berechnung aktualisieren")
    vs.SetBelowItem(dialog, 26, 27, 0, 6)
    vs.CreateStaticText(dialog, 28, "Berechnung\rVorschau", 70)
    vs.SetBelowItem(dialog, 27, 28, 0, 5)
    vs.CreateStaticText(dialog, 29,
                        "Bei UK + OK: ganzzahlige Stufen, tatsächliche Steigung 12–17 cm.\r"
                        "Podeste und Lauflinie folgen im nächsten Dialog. Keine Normprüfung.", 70)
    vs.SetBelowItem(dialog, 28, 29, 0, 7)

    def read():
        data = initial.to_dict()
        data["mode"] = "levels" if vs.GetSelectedChoiceIndex(dialog, 11, 0) == 0 else "count"
        data["automatic_going"] = bool(vs.GetBooleanItem(dialog, 23))
        for item, key in NUMERIC.items():
            # Disabled fields keep valid stored values and never block another input mode.
            if (key == "count" and data["mode"] == "levels") or (
                    key == "upper_m" and data["mode"] == "count"):
                continue
            if key == "going_cm" and data["automatic_going"]:
                continue
            data[key] = number(vs.GetItemText(dialog, item), key)
        data["top_tread"] = bool(vs.GetBooleanItem(dialog, 26))
        # First choose dimensions; landings/path constraints are handled in stage two.
        result = calculate(dict(data, landings=(), path_points=()))
        return replace(result, spec=replace(result.spec, landings=initial.landings,
                                           path_points=initial.path_points))

    def refresh(show_error=False):
        vs.EnableItem(dialog, 16, vs.GetSelectedChoiceIndex(dialog, 11, 0) == 0)
        vs.EnableItem(dialog, 18, vs.GetSelectedChoiceIndex(dialog, 11, 0) == 1)
        vs.EnableItem(dialog, 25, not vs.GetBooleanItem(dialog, 23))
        try:
            result = read()
            if result.spec.automatic_going:
                vs.SetItemText(dialog, 25, german(result.going_m * 100, 3))
            vs.SetItemText(dialog, 28, _preview(result))
            return result.spec
        except StairError as exc:
            vs.SetItemText(dialog, 28, str(exc))
            if show_error:
                vs.AlrtDialog(str(exc))
            return None

    def handler(item, _data):
        if item == INIT:
            vs.AddChoice(dialog, 11, "Unterkante + Oberkante", 0)
            vs.AddChoice(dialog, 11, "Unterkante + Stufenzahl", 1)
            vs.SelectChoice(dialog, 11, 0 if initial.mode == "levels" else 1, True)
            vs.SetBooleanItem(dialog, 23, initial.automatic_going)
            vs.SetBooleanItem(dialog, 26, initial.top_tread)
            refresh()
        elif item == 1:
            state["result"] = refresh(True)
            if state["result"] is None:
                return -1
        elif item in (11, 14, 16, 18, 20, 22, 23, 25, 26, 27):
            refresh(item == 27)
        return item

    return state["result"] if _run(dialog, handler) == 1 else None


def _parse_landings(value):
    rows = []
    if value.strip():
        for entry in value.split(";"):
            parts = entry.strip().split(":")
            if len(parts) != 2:
                raise StairError("Podeste bitte als Stufe:Tiefe eingeben, z. B. 5:1,32; 10:1,98")
            rows.append((number(parts[0], "Stufe vor Podest"), number(parts[1], "Podesttiefe")))
    return tuple(rows)


def landings(initial):
    state = {"result": None}
    dialog = vs.CreateResizableLayout(_title("PD Treppe – 2/4 Podeste und Lauflinie"), True,
                                      "Weiter", "Abbrechen", True, False)
    vs.CreateStaticText(dialog, 10,
                        "Sollen Podeste vorgesehen werden? Tiefe zusätzlich zum Auftritt.\r"
                        "Schrittzahl × Schrittmaß ergibt den veränderbaren Tiefenvorschlag.", 76)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.CreateCheckBox(dialog, 11, "Zusätzliche Podeste vorsehen")
    vs.SetBelowItem(dialog, 10, 11, 0, 5)
    _row(dialog, 11, 12, 13, "Schrittmaß auf dem Podest [cm]", initial.step_length_cm)
    _row(dialog, 12, 14, 15, "Schritte auf dem Podest", initial.landing_steps)
    _row(dialog, 14, 16, 17, "Nach wie vielen Stufen?", 5)
    _row(dialog, 16, 18, 19, "Podesttiefe [m] – frei änderbar",
         initial.landing_steps * initial.step_length_cm / 100)
    vs.CreatePushButton(dialog, 20, "Tiefe aus Schritten berechnen")
    vs.CreatePushButton(dialog, 21, "Podest hinzufügen / ersetzen")
    vs.SetBelowItem(dialog, 18, 20, 0, 4)
    vs.SetRightItem(dialog, 20, 21, 0, 0)
    vs.CreateStaticText(dialog, 22,
                        "Alle Podeste (Stufe:Tiefe in m); Eintrag löschen entfernt ein Podest", 76)
    vs.SetBelowItem(dialog, 20, 22, 0, 4)
    values = "; ".join(f"{int(n)}:{german(d, 3)}" for n, d in initial.landings)
    vs.CreateEditText(dialog, 23, values, 76)
    vs.SetBelowItem(dialog, 22, 23, 0, 2)
    vs.CreateCheckBox(dialog, 30, "Podestgefälle in Laufrichtung einrechnen")
    vs.SetBelowItem(dialog, 23, 30, 0, 5)
    _row(dialog, 30, 31, 32, "Podestgefälle [%] – positiv = abfallend",
         initial.landing_slope_percent)
    vs.CreateStaticText(dialog, 24, "Anordnung bezogen auf die gewählte Linie, in Laufrichtung", 76)
    vs.SetBelowItem(dialog, 31, 24, 0, 7)
    vs.CreatePullDownMenu(dialog, 25, 48)
    vs.SetBelowItem(dialog, 24, 25, 0, 3)
    vs.CreateCheckBox(dialog, 26, "Laufrichtung der Ausgangslinie umkehren")
    vs.SetBelowItem(dialog, 25, 26, 0, 4)
    vs.CreatePushButton(dialog, 27, "Treppenlauf und Podeste prüfen")
    vs.SetBelowItem(dialog, 26, 27, 0, 5)
    vs.CreateStaticText(dialog, 28, "Prüfung\rPodeste\rLauflinie", 76)
    vs.SetBelowItem(dialog, 27, 28, 0, 4)
    vs.CreateStaticText(dialog, 29,
                        "An Knicken über 5° entstehen automatisch Podeste, bei Bedarf tiefer.\r"
                        "Alle Auftritte werden auf der mittigen Lauflinie gemessen.\r"
                        "Die Ausgangslinie bleibt erhalten. Start = erster Punkt (umkehrbar).", 76)
    vs.SetBelowItem(dialog, 28, 29, 0, 6)

    def read():
        values = initial.to_dict()
        values["step_length_cm"] = number(vs.GetItemText(dialog, 13), "Schrittmaß")
        values["landing_steps"] = number(vs.GetItemText(dialog, 15), "Podest-Schritte")
        values["landings"] = (_parse_landings(vs.GetItemText(dialog, 23))
                              if vs.GetBooleanItem(dialog, 11) else ())
        values["landing_slope_enabled"] = bool(vs.GetBooleanItem(dialog, 30))
        values["landing_slope_percent"] = number(
            vs.GetItemText(dialog, 32), "Podestgefälle")
        values["alignment"] = ("left", "center", "right")[vs.GetSelectedChoiceIndex(dialog, 25, 0)]
        values["reverse_path"] = bool(vs.GetBooleanItem(dialog, 26))
        return calculate(values)

    def refresh(show_error=False):
        for item in (17, 19, 20, 21, 23):
            vs.EnableItem(dialog, item, vs.GetBooleanItem(dialog, 11))
        vs.EnableItem(dialog, 30, vs.GetBooleanItem(dialog, 11))
        vs.EnableItem(dialog, 31, (vs.GetBooleanItem(dialog, 11) and
                                   vs.GetBooleanItem(dialog, 30)))
        vs.EnableItem(dialog, 32, (vs.GetBooleanItem(dialog, 11) and
                                   vs.GetBooleanItem(dialog, 30)))
        try:
            result = read()
            platforms = [s for s in result.layout.spans if s.kind == "landing"]
            detail = "; ".join(f"nach {s.step}: {german(s.end - s.start, 2)} m"
                               + (" automatisch" if s.automatic else "") for s in platforms[:3])
            if len(platforms) > 3:
                detail += f"; … ({len(platforms)} Podeste)"
            vs.SetItemText(dialog, 28, _preview(result) + "\r" + (detail or "Keine Podeste"))
            return result.spec
        except StairError as exc:
            vs.SetItemText(dialog, 28, str(exc))
            if show_error:
                vs.AlrtDialog(str(exc))
            return None

    def handler(item, _data):
        if item == INIT:
            labels = ("Links von der Linie", "Mittig auf der Linie", "Rechts von der Linie")
            for i, label in enumerate(labels):
                vs.AddChoice(dialog, 25, label, i)
            vs.SelectChoice(dialog, 25, ("left", "center", "right").index(initial.alignment), True)
            vs.SetBooleanItem(dialog, 26, initial.reverse_path)
            vs.SetBooleanItem(dialog, 11, bool(initial.landings))
            vs.SetBooleanItem(dialog, 30, initial.landing_slope_enabled)
            vs.EnableItem(dialog, 25, bool(initial.path_points))
            vs.EnableItem(dialog, 26, bool(initial.path_points))
            refresh()
        elif item in (20, 21):
            try:
                if item == 20:
                    depth = number(vs.GetItemText(dialog, 13), "Schrittmaß") * number(
                        vs.GetItemText(dialog, 15), "Podest-Schritte") / 100
                    vs.SetItemText(dialog, 19, german(depth, 3))
                else:
                    after = number(vs.GetItemText(dialog, 17), "Stufennummer")
                    if not after.is_integer() or after < 1:
                        raise StairError("Bitte eine positive ganze Stufennummer angeben.")
                    rows = dict(_parse_landings(vs.GetItemText(dialog, 23)))
                    rows[int(after)] = number(vs.GetItemText(dialog, 19), "Podesttiefe")
                    vs.SetItemText(dialog, 23, "; ".join(f"{int(n)}:{german(d, 3)}"
                                                       for n, d in sorted(rows.items())))
                refresh(True)
            except StairError as exc:
                vs.AlrtDialog(str(exc))
        elif item == 1:
            state["result"] = refresh(True)
            if state["result"] is None:
                return -1
        elif item in (11, 13, 15, 23, 25, 26, 27, 30, 32):
            refresh(item == 27)
        return item

    return state["result"] if _run(dialog, handler) == 1 else None


def appearance(initial):
    state = {"result": None}
    dialog = vs.CreateResizableLayout(_title("PD Treppe – 3/4 Darstellung"), True,
                                      "Übernehmen", "Abbrechen", True, False)
    vs.CreateStaticText(dialog, 10, _preview(calculate(initial)), 70)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.CreateStaticText(dialog, 11, "Umrahmung · PD-WB-Treppe", 36)
    vs.CreateColorPopup(dialog, 12, 16)
    vs.SetBelowItem(dialog, 10, 11, 0, 6)
    vs.SetRightItem(dialog, 11, 12, 0, 0)
    vs.CreateStaticText(dialog, 13, "Füllung · PD-WB-Treppe", 36)
    vs.CreateColorPopup(dialog, 14, 16)
    vs.SetBelowItem(dialog, 11, 13, 0, 3)
    vs.SetRightItem(dialog, 13, 14, 0, 0)
    _row(dialog, 13, 15, 16, "Höhenbeschriftung [pt]", initial.height_font_pt)
    _row(dialog, 15, 17, 18, "Maßzahlen Breite / Länge [pt]", initial.dimension_font_pt)
    _row(dialog, 17, 19, 20, "Seitlicher Beschreibungstext [pt]", initial.note_font_pt)
    vs.CreateCheckBox(dialog, 21, "Seitlichen Beschreibungstext anzeigen")
    vs.SetBelowItem(dialog, 19, 21, 0, 6)
    vs.CreateStaticText(dialog, 22,
                        "Text frei bearbeiten; Enter = Zeilenumbruch. Automatische Werte:\r"
                        "{stufen}, {steigung}, {auftritt}, {uk}, {ok}, {breite}, {laenge}", 70)
    vs.SetBelowItem(dialog, 21, 22, 0, 4)
    vs.CreateEditTextBox(dialog, 23, initial.note.replace("\n", "\r\n"), 70, 5)
    vs.SetBelowItem(dialog, 22, 23, 0, 3)
    vs.CreatePushButton(dialog, 24, "Standardtext einsetzen")
    vs.SetBelowItem(dialog, 23, 24, 0, 4)
    vs.CreateStaticText(dialog, 25,
                        "Höhen links unten, max. ¾ Auftrittstiefe, parallel zur Stufe.\r"
                        "Text am Kontrollpunkt verschieben → automatische Bezugslinie.\r"
                        "Treppe per Doppelklick bearbeiten; Duplikate bleiben unabhängig.", 70)
    vs.SetBelowItem(dialog, 24, 25, 0, 6)

    def handler(item, _data):
        if item == INIT:
            r, g, b = initial.outline_rgb
            vs.SetColorChoice(dialog, 12, vs.RGBToColorIndex(r, g, b))
            r, g, b = initial.fill_rgb
            vs.SetColorChoice(dialog, 14, vs.RGBToColorIndex(r, g, b))
            vs.SetBooleanItem(dialog, 21, initial.show_note)
        elif item == 24:
            vs.SetItemText(dialog, 23, DEFAULT_NOTE.replace("\n", "\r\n"))
        elif item == 1:
            try:
                data = initial.to_dict()
                for field, key in ((16, "height_font_pt"), (18, "dimension_font_pt"),
                                   (20, "note_font_pt")):
                    data[key] = number(vs.GetItemText(dialog, field), key)
                data["outline_rgb"] = vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 12))
                data["fill_rgb"] = vs.ColorIndexToRGB(vs.GetColorChoice(dialog, 14))
                data["show_note"] = bool(vs.GetBooleanItem(dialog, 21))
                data["note"] = vs.GetItemText(dialog, 23)
                state["result"] = calculate(data).spec
            except StairError as exc:
                vs.AlrtDialog(str(exc))
                return -1
        return item

    return state["result"] if _run(dialog, handler) == 1 else None


def orientation(initial):
    """Rotation of the 3D component around the stair start; 2D stays planar."""
    state = {"result": None}
    dialog = vs.CreateResizableLayout(_title("PD Treppe – 4/4 3D"), True,
                                      "Weiter", "Abbrechen", True, False)
    vs.CreateStaticText(dialog, 10,
                        "Die 2D-Darstellung wird immer erzeugt. Die 3D-Konstruktion ist wählbar.\r"
                        "Jede Stufe ist nur eine Steigung hoch; alle 3D-Kanten erhalten "
                        "eine 5×5-mm-Fase.", 76)
    vs.SetFirstLayoutItem(dialog, 10)
    vs.CreateCheckBox(dialog, 16, "3D-Konstruktion mit Fundamenten erzeugen")
    vs.SetBelowItem(dialog, 10, 16, 0, 5)
    _row(dialog, 16, 17, 18, "Breite Anfangs-/Endfundament [m]",
         initial.end_foundation_width_m)
    _row(dialog, 17, 19, 20, "Tiefe Anfangs-/Endfundament [m]",
         initial.end_foundation_depth_m)
    _row(dialog, 19, 21, 22, "Tiefe durchgehendes Fundament [m]",
         initial.continuous_foundation_depth_m)
    _row(dialog, 21, 11, 12, "3D-Drehung um X am Treppenanfang [°]",
         initial.rotation_x_deg)
    _row(dialog, 11, 13, 14, "3D-Drehung um Y am Treppenanfang [°]",
         initial.rotation_y_deg)
    vs.CreateStaticText(dialog, 23,
                        "Die Drehung betrifft nur den 3D-Körper. Grundriss, Maße und Texte "
                        "bleiben lesbar in 2D. Die Drehung in der Grundrissebene erfolgt "
                        "weiterhin mit dem normalen Vectorworks-Drehen. Fundamentvorgaben "
                        "bleiben editierbar.", 76)
    vs.SetBelowItem(dialog, 13, 23, 0, 6)

    def enabled():
        active = bool(vs.GetBooleanItem(dialog, 16))
        for item in (17, 18, 19, 20, 21, 22, 11, 12, 13, 14):
            vs.EnableItem(dialog, item, active)

    def handler(item, _data):
        if item == INIT:
            vs.SetBooleanItem(dialog, 16, initial.draw_3d)
            enabled()
        elif item == 16:
            enabled()
        elif item == 1:
            try:
                data = initial.to_dict()
                data["draw_3d"] = bool(vs.GetBooleanItem(dialog, 16))
                data["end_foundation_width_m"] = number(
                    vs.GetItemText(dialog, 18), "Breite Anfangs-/Endfundament")
                data["end_foundation_depth_m"] = number(
                    vs.GetItemText(dialog, 20), "Tiefe Anfangs-/Endfundament")
                data["continuous_foundation_depth_m"] = number(
                    vs.GetItemText(dialog, 22), "Tiefe durchgehendes Fundament")
                data["rotation_x_deg"] = number(vs.GetItemText(dialog, 12), "3D-Drehung X")
                data["rotation_y_deg"] = number(vs.GetItemText(dialog, 14), "3D-Drehung Y")
                state["result"] = calculate(data).spec
            except StairError as exc:
                vs.AlrtDialog(str(exc))
                return -1
        return item

    return state["result"] if _run(dialog, handler) == 1 else None


def edit(initial):
    spec = geometry(initial)
    if spec is not None:
        spec = landings(spec)
    if spec is not None:
        spec = appearance(spec)
    return orientation(spec) if spec is not None else None
