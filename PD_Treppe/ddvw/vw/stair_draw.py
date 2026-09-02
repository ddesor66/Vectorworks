"""Explicitly styled 2D geometry, native dimensions and annotations inside a PIO."""

import math

import vs
import pd_chamfer

from ..core.stair import StairError, german, leader, note_text, span_surface
from ..core.stair_path import add, height_label, mul, normal, offset, sub, unit

GEOMETRY_CLASS = "PD-WB-Treppe"
GEOMETRY_3D_CLASS = "PD-WB-Treppe_3D"
FOUNDATION_3D_CLASS = "PD-WB-Treppe-Fundament_3D"
TEXT_CLASS = "PD-TX-Treppe"
BLACK = (0, 0, 0)
FOUNDATION_GREY = (47104, 47104, 47104)
CHAMFER_M = .005


def units_per_metre():
    upi = float(vs.GetUnits()[3])
    if not math.isfinite(upi) or upi <= 0:
        raise StairError("Die Dokumenteinheit konnte nicht sicher ermittelt werden.")
    return upi / 0.0254


def layer_scale(handle):
    layer = vs.GetLayer(handle)
    if not layer:
        raise StairError("Der Treppe ist keine Konstruktionsebene zugeordnet.")
    scale = float(vs.GetLScale(layer))
    if not math.isfinite(scale) or scale <= 0:
        raise StairError("Der Ebenenmaßstab ist ungültig.")
    return scale


def layer_elevation_m(handle):
    layer = vs.GetLayer(handle)
    if not layer:
        raise StairError("Der Treppe ist keine Konstruktionsebene zugeordnet.")
    # Verified VW2026 contract: this API returns millimetres independently
    # from the document display unit.
    value = float(vs.GetLayerElevation(layer)[0]) / 1000.0
    if not math.isfinite(value):
        raise StairError("Die Ebenenhöhe der Treppe ist ungültig.")
    return value


def _new(expected, previous):
    handle = vs.LNewObj()
    if not handle or handle == previous or vs.GetTypeN(handle) != expected:
        raise StairError("Ein Treppenbestandteil konnte nicht erzeugt werden.")
    return handle


def attributes(handle, class_name, pen, fill=None, weight=10):
    object_type = vs.GetTypeN(handle)
    vs.SetClass(handle, class_name)
    vs.SetPenFore(handle, pen)
    vs.SetPenBack(handle, pen)
    # SetLSN/SetLW/SetFPat are 2D attribute calls. Applying them to a mesh
    # makes Vectorworks 2026 emit "Object passed ... is not the proper type"
    # once per stair body. Mesh graphics are set before creation and secured
    # afterwards only with the object attributes supported by type 40.
    if object_type != 40:
        vs.SetLSN(handle, 2)
        vs.SetLW(handle, weight)
    vs.SetOpacity(handle, 100)
    # Native VW2026 lines have no fill slot; SetFPat on a line logs two API errors.
    if object_type not in (2, 40):
        vs.SetFPat(handle, 1 if fill is not None else 0)
    if fill is not None:
        vs.SetFillFore(handle, fill)
        vs.SetFillBack(handle, fill)


def _profiled_faces(polygon, bottom_a, bottom_b, top_a, top_b, chamfer,
                    line_a, line_b):
    """Map a chamfered prism to one linear vertical profile."""
    nominal_bottom = min(bottom_a, bottom_b)
    nominal_top = max(top_a, top_b)
    faces = pd_chamfer.prism_faces(polygon, nominal_bottom, nominal_top, chamfer)
    dx, dy = line_b[0] - line_a[0], line_b[1] - line_a[1]
    length2 = dx * dx + dy * dy
    height = nominal_top - nominal_bottom
    if length2 <= 1e-12 or height <= 2.0001 * chamfer:
        raise pd_chamfer.ChamferError("Der profilierte Körper ist zu kurz oder zu niedrig.")
    transformed = []
    for face in faces:
        changed = []
        for x, y, z in face:
            station = max(0.0, min(1.0,
                ((x-line_a[0])*dx + (y-line_a[1])*dy) / length2))
            bottom = bottom_a + (bottom_b-bottom_a) * station
            top = top_a + (top_b-top_a) * station
            fraction = (z-nominal_bottom) / height
            changed.append((x, y, bottom + (top-bottom) * fraction))
        transformed.append(tuple(changed))
    return tuple(transformed)


def _create_profiled_mesh(result, factor, span_start, span_end,
                          bottom_a_m, bottom_b_m, top_a_m, top_b_m,
                          class_name, fill, layer_z, rotation):
    polygon = tuple((x * factor, y * factor)
                    for x, y in result.layout.band(span_start, span_end))
    line_a = tuple(value * factor for value in result.layout.at(span_start)[0])
    line_b = tuple(value * factor for value in result.layout.at(span_end)[0])
    values = tuple((value-layer_z) * factor for value in
                   (bottom_a_m, bottom_b_m, top_a_m, top_b_m))
    try:
        faces = _profiled_faces(
            polygon, *values, CHAMFER_M * factor, line_a, line_b)
        # Explicit active attributes are inherited safely by a new mesh.
        vs.NameClass(class_name)
        vs.FillPat(1)
        vs.FillFore(fill)
        vs.FillBack(fill)
        vs.PenFore(result.spec.outline_rgb)
        vs.PenBack(result.spec.outline_rgb)
        mesh = pd_chamfer.create_mesh(vs, faces)
    except pd_chamfer.ChamferError as exc:
        raise StairError(str(exc)) from exc
    attributes(mesh, class_name, result.spec.outline_rgb, fill, 18)
    if abs(rotation[0]) > 1e-10 or abs(rotation[1]) > 1e-10:
        pivot = (result.spec.lower_m-layer_z) * factor
        vs.Set3DRot(mesh, rotation[0], rotation[1], 0., 0., 0., pivot)
    return mesh


def draw_3d(result, handle, factor):
    """Create rise-thick treads/landings and three editable foundation types."""
    layer_z = layer_elevation_m(handle)
    rotation = result.spec.rotation_x_deg, result.spec.rotation_y_deg
    vs.NameClass(GEOMETRY_3D_CLASS)
    vs.NameClass(FOUNDATION_3D_CLASS)
    foundation_profiles = []
    preceding_under = result.spec.lower_m
    for number, span in enumerate(result.layout.spans, 1):
        try:
            top_a, top_b = span_surface(result, span)
            _create_profiled_mesh(
                result, factor, span.start, span.end,
                top_a-result.rise_m, top_b-result.rise_m, top_a, top_b,
                GEOMETRY_3D_CLASS, result.spec.fill_rgb, layer_z, rotation)
            rear_under = top_b - result.rise_m
            depth = result.spec.continuous_foundation_depth_m
            _create_profiled_mesh(
                result, factor, span.start, span.end,
                preceding_under-depth, rear_under-depth,
                preceding_under, rear_under,
                FOUNDATION_3D_CLASS, FOUNDATION_GREY, layer_z, rotation)
            foundation_profiles.append((span.start, span.end,
                                        preceding_under, rear_under))
            preceding_under = rear_under
        except StairError as exc:
            raise StairError("3D-Stufe %d: %s" % (number, exc)) from exc

    def foundation_top(station):
        for start, end, first, second in foundation_profiles:
            if station <= end + 1e-9:
                fraction = 0.0 if end <= start else (station-start)/(end-start)
                return first + (second-first) * max(0.0, min(1.0, fraction))
        return foundation_profiles[-1][3]

    end_width = min(result.spec.end_foundation_width_m, result.layout.length_m)
    for label, start, end in (
            ("Anfangsfundament", 0.0, end_width),
            ("Endfundament", max(0.0, result.layout.length_m-end_width),
             result.layout.length_m)):
        top_a, top_b = foundation_top(start), foundation_top(end)
        depth = result.spec.end_foundation_depth_m
        try:
            _create_profiled_mesh(
                result, factor, start, end, top_a-depth, top_b-depth,
                top_a, top_b, FOUNDATION_3D_CLASS, FOUNDATION_GREY,
                layer_z, rotation)
        except StairError as exc:
            raise StairError(label + ": " + str(exc)) from exc


def preview(result, origin):
    """Temporary dashed plan preview. The caller owns and deletes the group."""
    factor = units_per_metre()
    ox, oy = float(origin[0]), float(origin[1])

    def point(xy):
        return ox + xy[0] * factor, oy + xy[1] * factor

    previous = vs.LNewObj()
    vs.PushAttrs()
    try:
        vs.BeginGroup()
        vs.BeginPoly()
        for xy in result.layout.outline + result.layout.outline[:1]:
            vs.AddPoint(point(xy))
        vs.EndPoly()
        for span in result.layout.spans[1:]:
            a, b = result.layout.section(span.start)
            vs.MoveTo(point(a))
            vs.LineTo(point(b))
        vs.EndGroup()
        group = _new(11, previous)
        vs.SetClass(group, GEOMETRY_CLASS)
        child = vs.FInGroup(group)
        while child:
            attributes(child, GEOMETRY_CLASS, result.spec.outline_rgb, weight=12)
            vs.SetLSN(child, 4)  # Native dashed line pattern; preview only.
            vs.SetOpacity(child, 70)
            child = vs.NextObj(child)
        return group
    finally:
        vs.PopAttrs()


def draw(result, handle, note_xy_m):
    factor = units_per_metre()
    scale = layer_scale(handle)
    paper = scale / 1000.0  # One paper millimetre in model metres.
    spec = result.spec

    def point(xy):
        return tuple(value * factor for value in xy)

    def line(a, b, annotation=False, weight=10):
        previous = vs.LNewObj()
        vs.MoveTo(point(a))
        vs.LineTo(point(b))
        h = _new(2, previous)
        attributes(h, TEXT_CLASS if annotation else GEOMETRY_CLASS,
                   BLACK if annotation else spec.outline_rgb, weight=weight)
        # Markers are deliberately drawn as geometry; suppress inherited class markers.
        vs.SetObjBeginningMarker(h, 1280, 25, .25, .125, 34, 2, False)
        vs.SetObjEndMarker(h, 1280, 25, .25, .125, 34, 2, False)
        return h

    def text(value, xy, size, align=1, vertical=3, angle=0., max_width=None, max_height=None):
        if not value:
            return None
        value = value.replace("\n", "\r")
        vs.TextSize(size)
        vs.TextJust(align)
        vs.TextVerticalAlign(vertical)
        vs.TextOrigin(point(xy))
        previous = vs.LNewObj()
        vs.CreateText(value)
        h = _new(10, previous)
        attributes(h, TEXT_CLASS, BLACK)
        vs.SetTextStyleRef(h, 0)
        vs.SetTextSize(h, 0, len(value), size)
        vs.SetTextStyle(h, 0, len(value), 0)
        vs.SetTextJust(h, align)
        vs.SetTextVerticalAlign(h, vertical)
        vs.SetTextSpace(h, 2)
        if max_width is not None or max_height is not None:
            top_left, bottom_right = vs.GetBBox(h)
            width = abs(bottom_right[0] - top_left[0]) / factor
            height = abs(top_left[1] - bottom_right[1]) / factor
            ratio = min(1., max_width / width if max_width and width > 0 else 1.,
                        max_height / height if max_height and height > 0 else 1.)
            if ratio < 1:
                vs.SetTextSize(h, 0, len(value), size * ratio)
        if abs(angle) > 1e-8:
            vs.HRotate(h, point(xy), angle)
        return h

    def dimension(a, b, offset, direction):
        vs.TextSize(spec.dimension_font_pt)
        previous = vs.LNewObj()
        vs.LinearDim(point(a), point(b), offset * factor, direction, 771, 771, 0)
        h = _new(63, previous)
        attributes(h, TEXT_CLASS, BLACK)
        vs.SetTextStyleRef(h, 0)
        vs.SetObjectVariableLongInt(h, 1248, 0)  # Dimension text style, Appendix G.
        vs.SetObjectVariableReal(h, 40, spec.dimension_font_pt)  # Font size in points.
        vs.SetObjectVariableInt(h, 19, 0)  # Plain dimension font.
        vs.ResetObject(h)

    vs.PushAttrs()
    try:
        vs.NameClass(TEXT_CLASS)
        vs.NameClass(GEOMETRY_CLASS)
        vs.NameClass(GEOMETRY_3D_CLASS)
        vs.NameClass(FOUNDATION_3D_CLASS)
        attributes(handle, GEOMETRY_CLASS, spec.outline_rgb, spec.fill_rgb, 18)
        width, length, going = spec.width_m, result.length_m, result.going_m
        layout = result.layout
        previous = vs.LNewObj()
        if not spec.path_points:
            vs.Rect((0, length * factor), (width * factor, 0))
            outline = _new(3, previous)
        else:
            vs.BeginPoly()
            for xy in layout.outline + layout.outline[:1]:
                vs.AddPoint(point(xy))
            vs.EndPoly()
            outline = _new(5, previous)
        attributes(outline, GEOMETRY_CLASS, spec.outline_rgb, spec.fill_rgb, 18)
        if spec.draw_3d:
            draw_3d(result, handle, factor)
        for span in layout.spans[1:]:
            line(*layout.section(span.start))

        first = layout.spans[0]
        xy, size, angle, available = height_label(result, first, scale)
        tangent = layout.at(0)[1]
        text("UK " + german(spec.lower_m, 3) + " m", sub(xy, mul(tangent, going * .7)),
             size, vertical=5, angle=angle, max_width=available, max_height=going * .75)
        for span in layout.spans:
            xy, size, angle, available = height_label(result, span, scale)
            value = german(result.heights_m[span.step], 3) + " m"
            text(value, xy, size, vertical=5, angle=angle,
                 max_width=min(available, width * .43), max_height=going * .75)
        if result.steps > result.treads:
            left, right = layout.section(length)
            across = unit(sub(right, left))
            xy = add(left, mul(normal(across), going * .1))
            text(german(result.upper_m, 3) + " m", xy, size, vertical=5,
                 angle=math.degrees(math.atan2(across[1], across[0])),
                 max_width=width * .43, max_height=going * .75)

        # The ascent arrow follows the middle walking line, including landings.
        low, high = going * 0.15, length - going * 0.15
        arrow_size = min(3 * paper, width * 0.1, (high - low) * 0.2)
        arrow = layout.center_path(low, high)
        for a, b in zip(arrow, arrow[1:]):
            line(a, b, weight=18)
        tip, tangent = layout.at(high)
        base = sub(tip, mul(tangent, 2 * arrow_size))
        line(add(base, mul(normal(tangent), arrow_size)), tip, weight=18)
        line(sub(base, mul(normal(tangent), arrow_size)), tip, weight=18)

        dimension(*layout.section(0), -9 * paper, 4 if spec.path_points else 0)
        if not spec.path_points:
            dimension((width, 0), (width, length), 8 * paper, 1)
        else:
            # A straight chord dimension would be wrong for a curved stair.
            # Draw the offset measuring line and label its cumulative middle-line length.
            measure = offset(layout.center_path(0, length), -width / 2 - 8 * paper)
            for a, b in zip(measure, measure[1:]):
                line(a, b, annotation=True)
            line(layout.section(0)[1], measure[0], annotation=True)
            line(layout.section(length)[1], measure[-1], annotation=True)
            anchor = (layout.bounds[2] + 10 * paper, layout.bounds[3] + 4 * paper)
            text("Lauflänge " + german(length, 3) + " m", anchor, spec.dimension_font_pt)

        for span in layout.spans:
            if span.kind != "landing":
                continue
            if not spec.path_points:
                dimension((width, span.start), (width, span.end), 4 * paper, 1)
            else:
                route = layout.center_path(span.start, span.end)
                if len(route) == 2:
                    dimension(*route, width / 2 + 4 * paper, 4)
                else:
                    # A bent/curved landing is measured along its middle line, not its chord.
                    measure = offset(route, -width / 2 - 4 * paper)
                    for a, b in zip(measure, measure[1:]):
                        line(a, b, annotation=True)
                    line(layout.section(span.start)[1], measure[0], annotation=True)
                    line(layout.section(span.end)[1], measure[-1], annotation=True)
                    mid, tangent = layout.at((span.start + span.end) * .5)
                    label_xy = sub(mid, mul(normal(tangent), width / 2 + 6 * paper))
                    text(german(span.end - span.start, 3) + " m", label_xy,
                         spec.dimension_font_pt, vertical=1)
            if spec.landing_slope_enabled and spec.landing_slope_percent > 0:
                inset = min((span.end-span.start) * .2, going * .25)
                start = span.start + inset
                end = span.end - inset
                route = layout.center_path(start, end)
                for a, b in zip(route, route[1:]):
                    line(a, b, annotation=True, weight=12)
                tip, tangent = layout.at(end)
                arrow_size = min(2.5 * paper, width * .08, (end-start) * .15)
                base = sub(tip, mul(tangent, 2 * arrow_size))
                line(add(base, mul(normal(tangent), arrow_size)), tip,
                     annotation=True, weight=12)
                line(sub(base, mul(normal(tangent), arrow_size)), tip,
                     annotation=True, weight=12)
                middle, tangent = layout.at((start+end) * .5)
                text("Gefälle " + german(spec.landing_slope_percent, 2) + " %",
                     add(middle, mul(normal(tangent), 3 * paper)),
                     spec.dimension_font_pt, vertical=5,
                     angle=math.degrees(math.atan2(tangent[1], tangent[0])))

        if spec.show_note:
            connection = leader(result, note_xy_m, scale)
            if connection:
                line(connection[0], connection[1], annotation=True)
            text(note_text(result), note_xy_m, spec.note_font_pt, vertical=1)
    finally:
        vs.PopAttrs()
