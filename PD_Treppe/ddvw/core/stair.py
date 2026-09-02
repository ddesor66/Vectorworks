"""Parametric stair geometry and presentation settings, in metres and paper points."""
import json
import math
import re
from dataclasses import asdict, dataclass


class StairError(ValueError):
    pass


DEFAULT_NOTE = "{stufen} Stufen\nSteigung {steigung} cm / Auftritt {auftritt} cm"


def number(value, title):
    if isinstance(value, bool):
        raise StairError(title + ": eine Zahl eingeben.")
    try:
        result = float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError) as exc:
        raise StairError(title + ": eine gültige Zahl eingeben.") from exc
    if not math.isfinite(result):
        raise StairError(title + ": die Zahl muss endlich sein.")
    return result


@dataclass(frozen=True)
class StairSpec:
    mode: str = "levels"
    lower_m: float = 0.0
    upper_m: float = 1.5
    count: int = 10
    width_m: float = 1.2
    requested_rise_cm: float = 15.0
    automatic_going: bool = True
    going_cm: float = 33.0
    top_tread: bool = True
    height_font_pt: float = 9.0
    dimension_font_pt: float = 9.0
    note_font_pt: float = 10.0
    outline_rgb: tuple = (0, 0, 0)
    fill_rgb: tuple = (32768, 32768, 32768)
    show_note: bool = True
    note: str = DEFAULT_NOTE
    landings: tuple = ()  # (after tread number, additional horizontal depth in metres)
    step_length_cm: float = 66.0
    landing_steps: int = 2
    landing_slope_enabled: bool = False
    landing_slope_percent: float = 2.0  # Positive = fall in walking direction.
    path_points: tuple = ()  # Immutable local coordinates; original path is never modified.
    alignment: str = "center"
    reverse_path: bool = False
    draw_3d: bool = True
    end_foundation_width_m: float = 0.40
    end_foundation_depth_m: float = 0.80
    continuous_foundation_depth_m: float = 0.25
    rotation_x_deg: float = 0.0  # 3D body only; 2D Top/Plan stays readable.
    rotation_y_deg: float = 0.0

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class StairResult:
    spec: StairSpec
    steps: int
    treads: int
    rise_m: float
    going_m: float
    upper_m: float
    length_m: float
    heights_m: tuple
    layout: object = None


def spec_from_dict(values):
    allowed = set(StairSpec.__dataclass_fields__)
    if not isinstance(values, dict) or set(values) - allowed:
        raise StairError("Unbekanntes Treppendatenformat.")
    data = StairSpec().to_dict()
    data.update(values)
    for key in ("lower_m", "upper_m", "width_m", "requested_rise_cm", "going_cm",
                "height_font_pt", "dimension_font_pt", "note_font_pt", "step_length_cm",
                "landing_slope_percent", "end_foundation_width_m",
                "end_foundation_depth_m", "continuous_foundation_depth_m",
                "rotation_x_deg", "rotation_y_deg"):
        data[key] = number(data[key], key)
    count = number(data["count"], "Stufenzahl")
    if not count.is_integer() or not 1 <= count <= 1000:
        raise StairError("Die Stufenzahl muss eine ganze Zahl zwischen 1 und 1000 sein.")
    data["count"] = int(count)
    for key in ("automatic_going", "top_tread", "show_note", "reverse_path",
                "landing_slope_enabled", "draw_3d"):
        if type(data[key]) is not bool:
            raise StairError("Ungültiger Schalter: " + key)
    for key in ("outline_rgb", "fill_rgb"):
        color = data[key]
        if not isinstance(color, (list, tuple)) or len(color) != 3 or any(
                type(channel) is not int or not 0 <= channel <= 65535 for channel in color):
            raise StairError("Ungültige Farbe: " + key)
        data[key] = tuple(color)
    if not isinstance(data["note"], str) or len(data["note"]) > 4000:
        raise StairError("Der Beschreibungstext darf höchstens 4000 Zeichen enthalten.")
    data["note"] = data["note"].replace("\r\n", "\n").replace("\r", "\n")
    if data["mode"] not in ("levels", "count"):
        raise StairError("Eingabeart muss UK + OK oder UK + Stufenzahl sein.")
    if not 12.0 <= data["requested_rise_cm"] <= 17.0:
        raise StairError("Die gewünschte Steigung muss zwischen 12 und 17 cm liegen.")
    if not 0 < data["width_m"] <= 1000:
        raise StairError("Die Breite muss größer als 0 und höchstens 1000 m sein.")
    if not data["automatic_going"] and not 0 < data["going_cm"] <= 1000:
        raise StairError("Der Auftritt muss größer als 0 und höchstens 1000 cm sein.")
    for key in ("height_font_pt", "dimension_font_pt", "note_font_pt"):
        if not 1 <= data[key] <= 144:
            raise StairError("Schriftgrößen müssen zwischen 1 und 144 pt liegen.")
    if any(abs(data[key]) > 100000 for key in ("lower_m", "upper_m")):
        raise StairError("Höhen müssen innerhalb ±100000 m liegen.")
    if not 1 <= data["step_length_cm"] <= 200:
        raise StairError("Das Podest-Schrittmaß muss zwischen 1 und 200 cm liegen.")
    if not 0 <= data["landing_slope_percent"] <= 20:
        raise StairError("Das Podestgefälle muss zwischen 0 und 20 % liegen.")
    for key, title in (
            ("end_foundation_width_m", "Breite der Anfangs-/Endfundamente"),
            ("end_foundation_depth_m", "Tiefe der Anfangs-/Endfundamente"),
            ("continuous_foundation_depth_m", "Tiefe des durchgehenden Fundaments")):
        if not 0.01 <= data[key] <= 100:
            raise StairError(title + " muss zwischen 0,01 und 100 m liegen.")
    landing_steps = number(data["landing_steps"], "Podest-Schritte")
    if not landing_steps.is_integer() or not 1 <= landing_steps <= 100:
        raise StairError("Für Podeste bitte 1–100 ganze Schritte eingeben.")
    data["landing_steps"] = int(landing_steps)
    if data["alignment"] not in ("left", "center", "right"):
        raise StairError("Anordnung muss links, mittig oder rechts sein.")
    for key, limit in (("landings", 1000), ("path_points", 4000)):
        rows = data[key]
        if not isinstance(rows, (tuple, list)) or len(rows) > limit:
            raise StairError("Ungültige oder zu umfangreiche Daten: " + key)
        if any(not isinstance(row, (tuple, list)) or len(row) != 2 for row in rows):
            raise StairError("Ungültige Koordinaten / Podeste.")
        data[key] = tuple(tuple(number(v, key) for v in row) for row in rows)
    if data["path_points"] and len(data["path_points"]) < 2:
        raise StairError("Die Lauflinie benötigt mindestens zwei Punkte.")
    if any(abs(v) > 100000 for p in data["path_points"] for v in p):
        raise StairError("Die Lauflinie liegt außerhalb des zulässigen Bereichs.")
    if any(abs(data[key]) > 360 for key in ("rotation_x_deg", "rotation_y_deg")):
        raise StairError("Die 3D-Drehung muss zwischen −360° und +360° liegen.")
    used = set()
    for after, depth in data["landings"]:
        if not after.is_integer() or after < 1 or after in used or not 0.01 <= depth <= 100:
            raise StairError("Podeste: eindeutige ganze Stufennummer und Tiefe 0,01–100 m angeben.")
        used.add(after)
    data["landings"] = tuple(sorted((int(n), d) for n, d in data["landings"]))
    return StairSpec(**data)


def _solve_rise(spec, landing_length):
    """Solve constant risers after accounting for forward landing fall."""
    slope_drop = (landing_length * spec.landing_slope_percent / 100.0
                  if spec.landing_slope_enabled else 0.0)
    target = spec.requested_rise_cm / 100.0
    if spec.mode == "levels":
        delta = spec.upper_m - spec.lower_m
        if delta <= 0:
            raise StairError("Die Oberkante muss über der Unterkante liegen.")
        stair_delta = delta + slope_drop
        minimum = max(1, math.ceil((stair_delta - 1e-10) / 0.17))
        maximum = min(1000, math.floor((stair_delta + 1e-10) / 0.12))
        if minimum > maximum:
            raise StairError("Dieser Höhenunterschied einschließlich Podestgefälle ist mit "
                             "ganzen Stufen und 12–17 cm Steigung nicht lösbar.")
        steps = min(range(minimum, maximum + 1),
                    key=lambda n: (abs(stair_delta/n-target), n))
        return steps, stair_delta / steps, spec.upper_m
    steps, rise = spec.count, target
    return steps, rise, spec.lower_m + steps * rise - slope_drop


def calculate(value):
    spec = spec_from_dict(value.to_dict() if isinstance(value, StairSpec) else value)
    from .stair_path import build_layout

    # Automatic corner landings depend on the going, while the going depends
    # on the riser that includes their fall. A short bounded fixed-point pass
    # resolves this without changing the established layout architecture.
    landing_length = sum(depth for _after, depth in spec.landings)
    layout = None
    for _iteration in range(12):
        steps, rise, upper = _solve_rise(spec, landing_length)
        treads = steps if spec.top_tread else steps - 1
        if treads < 1:
            raise StairError("Bei nur einer Stufe bitte den oberen Auftritt mitzeichnen.")
        if any(after > treads for after, _depth in spec.landings):
            raise StairError("Ein Podest liegt hinter der letzten gezeichneten Stufe.")
        going = (0.63 - 2 * rise) if spec.automatic_going else spec.going_cm / 100.
        preliminary = StairResult(
            spec, steps, treads, rise, going, upper, treads * going,
            tuple(spec.lower_m + i * rise for i in range(steps)) + (upper,))
        layout = build_layout(preliminary)
        actual = sum(span.end - span.start for span in layout.spans
                     if span.kind == "landing")
        if abs(actual - landing_length) <= 1e-9:
            break
        landing_length = actual
    else:
        raise StairError("Podestgefälle und automatische Podeste konnten nicht stabil "
                         "berechnet werden. Bitte die Lauflinie oder Vorgaben ändern.")

    slope = spec.landing_slope_percent / 100.0 if spec.landing_slope_enabled else 0.0
    landing_before = [0.0] * (steps + 1)
    for index in range(steps + 1):
        landing_before[index] = sum(
            span.end - span.start for span in layout.spans
            if span.kind == "landing" and span.step < index)
    heights = tuple(spec.lower_m + index * rise - landing_before[index] * slope
                    for index in range(steps + 1))
    upper = spec.lower_m + steps * rise - landing_length * slope
    if spec.mode == "levels" and abs(upper - spec.upper_m) > 1e-7:
        raise StairError("Das Podestgefälle konnte nicht exakt in die Oberkante eingerechnet werden.")
    result = StairResult(spec, steps, treads, rise, going, upper,
                         layout.length_m, heights, layout)
    note_text(result)  # Validate the editable template before any document changes.
    return result


def span_surface(result, span):
    """Top elevations at the front and rear of one tread or landing."""
    start = result.heights_m[span.step]
    if span.kind != "landing" or not result.spec.landing_slope_enabled:
        return start, start
    drop = (span.end - span.start) * result.spec.landing_slope_percent / 100.0
    return start, start - drop


def german(value, decimals=2):
    text = f"{value:.{decimals}f}".replace(".", ",")
    return text[1:] if text.startswith("-0,") and float(text.replace(",", ".")) == 0 else text


def note_text(result):
    replacements = {
        "stufen": str(result.steps), "steigung": german(result.rise_m*100),
        "auftritt": german(result.going_m*100), "uk": german(result.spec.lower_m, 3),
        "ok": german(result.upper_m, 3), "breite": german(result.spec.width_m),
        "laenge": german(result.length_m),
    }
    unknown = set(re.findall(r"\{([^{}]*)\}", result.spec.note)) - set(replacements)
    if unknown:
        raise StairError("Unbekannte Textplatzhalter: " + ", ".join(sorted(unknown)))
    text = result.spec.note
    for key, value in replacements.items():
        text = text.replace("{" + key + "}", value)
    return text


def note_anchor(result, paper_scale):
    """Default note position right of the stair and outside the width dimension."""
    left, bottom, right, top = result.layout.bounds
    return right + 0.015 * paper_scale, (bottom + top) * 0.5


def leader(result, text_xy, paper_scale):
    default = note_anchor(result, paper_scale)
    if not result.spec.show_note or math.dist(default, text_xy) < 1e-7:
        return None
    from .stair_path import nearest_on_segment

    polygon = result.layout.outline
    candidates = [nearest_on_segment(text_xy, a, b) for a, b in
                  zip(polygon, polygon[1:] + polygon[:1])]
    start = min(candidates, key=lambda point: math.dist(point, text_xy))
    return start, tuple(text_xy)


def encode(spec, anchor_m=None):
    checked = calculate(spec).spec
    return json.dumps({"schema": 5, "spec": checked.to_dict(), "anchor_m": anchor_m},
                      ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def decode(raw):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise StairError("Die gespeicherten Treppendaten sind beschädigt.") from exc
    if not isinstance(value, dict) or value.get("schema") not in (1, 3, 4, 5) or "spec" not in value:
        raise StairError("Diese Treppendatenversion wird nicht unterstützt.")
    anchor = value.get("anchor_m")
    if anchor is not None:
        if not isinstance(anchor, list) or len(anchor) != 2:
            raise StairError("Die gespeicherte Textposition ist ungültig.")
        anchor = tuple(number(x, "Textposition") for x in anchor)
    return calculate(value["spec"]).spec, anchor


def adjusted_note_position(result, scale, point_m, previous_anchor_m):
    """Keep a dragged note's offset when stair dimensions or layer scale change."""
    anchor = note_anchor(result, scale)
    if previous_anchor_m is None or point_m is None:
        return anchor
    return tuple(anchor[i] + point_m[i] - previous_anchor_m[i] for i in range(2))
