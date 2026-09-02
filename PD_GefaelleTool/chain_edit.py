"""Regrade a selected connected part of one slope chain; no Vectorworks IO."""
import copy

from . import core


def edit_heights(chain, heights):
    """Edit only named elevations; preserve all other data without rounding."""
    core.validate_chain(chain)
    if not isinstance(heights, dict) or not heights:
        raise core.SlopeError("Bitte mindestens eine Punkthöhe ändern.")
    numbers = {p["number"] for p in chain["points"]}
    if any(isinstance(n, bool) or not isinstance(n, int) or n not in numbers for n in heights):
        raise core.SlopeError("Eine Punktnummer gehört nicht zu dieser Kette.")
    values = {n: core._number(h, "Höhe P:%d" % n) for n, h in heights.items()}
    changed = copy.deepcopy(chain)
    details = []
    for point in changed["points"]:
        number, old = point["number"], point["height_m"]
        if number in values and values[number] != old:
            point["height_m"] = values[number]
            details.append(dict(number=number, old_height_m=old, new_height_m=values[number],
                                delta_m=values[number]-old, fixed=False))
    if not details:
        raise core.SlopeError("Es wurden noch keine Punkthöhen geändert.")
    changed["mode"], changed["value"] = "manual", 0.
    core.validate_chain(changed)
    before, after = core.segment_rows(chain), core.segment_rows(changed)
    boundary = [dict(from_number=a["from"], to_number=a["to"],
                     old_slope=a["slope_percent"], new_slope=b["slope_percent"])
                for a, b in zip(before, after) if abs(a["slope_percent"]-b["slope_percent"]) > 1e-9]
    return changed, dict(operation="heights", points=details, boundary=boundary)


def preview(chain, mode, rows, slope_percent, fixed="first", height_overrides=None):
    if height_overrides:
        return edit_heights(chain, height_overrides)
    return regrade(chain, mode, rows, slope_percent, fixed)


def selection_span(chain, mode, rows):
    core.validate_chain(chain)
    if mode not in ("points", "segments"):
        raise core.SlopeError("Bitte Höhenpunkte oder Verbindungen als Auswahlart wählen.")
    values = tuple(rows)
    if any(isinstance(i, bool) or not isinstance(i, int) for i in values):
        raise core.SlopeError("Ungültige Zeilenauswahl.")
    indexes = sorted(set(values))
    limit = len(chain["points"]) - (1 if mode == "segments" else 0)
    if any(i < 0 or i >= limit for i in indexes):
        raise core.SlopeError("Die Auswahl gehört nicht vollständig zu diesem Gefälle.")
    if mode == "points":
        if len(indexes) < 2:
            raise core.SlopeError("Mindestens zwei Höhenpunkte markieren. Alle Zwischenpunkte werden einbezogen.")
        return indexes[0], indexes[-1]
    if not indexes:
        raise core.SlopeError("Mindestens eine Verbindung markieren.")
    if indexes != list(range(indexes[0], indexes[-1] + 1)):
        raise core.SlopeError("Die markierten Verbindungen bilden keine zusammenhängende Kette. Bitte die Lücken mit auswählen.")
    return indexes[0], indexes[-1] + 1


def regrade(chain, mode, rows, slope_percent, fixed="first"):
    first, last = selection_span(chain, mode, rows)
    slope = core._number(slope_percent, "Gefälle")
    points = chain["points"]
    if fixed == "first":
        anchor = first
    elif fixed == "last":
        anchor = last
    else:
        if isinstance(fixed, bool) or not isinstance(fixed, int):
            raise core.SlopeError("Bitte eine gültige feste Punktnummer angeben.")
        anchor = next((i for i in range(first, last+1) if points[i]["number"] == fixed), None)
        if anchor is None:
            raise core.SlopeError("Der feste Höhenpunkt muss innerhalb der gewählten Kette liegen.")
    segments = core.segment_rows(chain)  # native arc lengths where present
    distances = [0.]
    for segment in segments:
        distances.append(distances[-1] + segment["length_m"])
    changed = copy.deepcopy(chain)
    height = points[anchor]["height_m"]
    for i in range(first, last+1):
        changed["points"][i]["height_m"] = height - (distances[i]-distances[anchor]) * slope / 100.
    changed["mode"], changed["value"] = "manual", 0.
    core.validate_chain(changed)
    after = core.segment_rows(changed)
    boundary = [dict(from_number=segments[i]["from"], to_number=segments[i]["to"],
                     old_slope=segments[i]["slope_percent"], new_slope=after[i]["slope_percent"])
                for i in (first-1, last) if 0 <= i < len(segments)
                and abs(after[i]["slope_percent"]-segments[i]["slope_percent"]) > 1e-9]
    details = [dict(number=points[i]["number"], old_height_m=points[i]["height_m"],
                    new_height_m=changed["points"][i]["height_m"],
                    delta_m=changed["points"][i]["height_m"]-points[i]["height_m"],
                    fixed=i == anchor) for i in range(first, last+1)]
    return changed, dict(from_number=points[first]["number"], to_number=points[last]["number"],
                         fixed_number=points[anchor]["number"], fixed_height_m=height,
                         slope_percent=slope, length_m=distances[last]-distances[first],
                         points=details, boundary=boundary)


def check_shared_points(original, changed, other_chains):
    """Do not leave two different heights on a shared branch junction."""
    heights = {p["number"]: p["height_m"] for p in original["points"]}
    moved = {p["number"] for p in changed["points"]
             if abs(p["height_m"]-heights[p["number"]]) > 1e-9}
    for other in other_chains:
        for point in other["points"]:
            if point["number"] in moved:
                raise core.SlopeError(
                    "P:%d gehört auch zu einer anderen Gefällegruppe. Diesen Anschlusspunkt als feste "
                    "Punktnummer wählen oder die Teilkette eingrenzen. Andere Gruppen werden nicht verändert."
                    % point["number"])
