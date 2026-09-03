"""Vectorworks 2026 point symbols and terrain-compatible primitives.

    Symbols are presentation only. Terrain gets native type 9 loci/type 25
    open polygons, never vertices of the marker artwork.
"""
import math
import vs

from .core import SlopeError
from . import point_output


def document_symbols():
    resource_list, count = vs.BuildResourceList(16, 0, "")
    names = []
    for index in range(1, count + 1):
        handle = vs.GetResourceFromList(resource_list, index)
        if handle and vs.GetTypeN(handle) == 16:
            names.append(str(vs.GetName(handle)))
    return tuple(sorted(set(names), key=str.casefold))


def _check_xyz(actual, expected):
    if (not isinstance(actual, (tuple, list)) or len(actual) != 3
            or not all(math.isfinite(float(v)) for v in actual)
            or max(abs(a-b) for a, b in zip(actual, expected)) > 1e-5):
        raise SlopeError("Vectorworks hat eine abweichende 3D-Position erzeugt; Ausgabe abgebrochen.")


def _symbol_xyz(handle):
    """Read a stable 3D symbol position after a native reset."""
    value = vs.GetSymLoc3D(handle)
    if (not isinstance(value, (tuple, list)) or len(value) < 3 or
            not all(math.isfinite(float(component)) for component in value[:3])):
        raise SlopeError(
            "Vectorworks hat die 3D-Position des Punktsymbols noch nicht bereitgestellt.")
    return tuple(float(component) for component in value[:3])


def _native_xyz(value, description):
    """Validate tuple-returning native geometry readers at the API boundary."""
    if (not isinstance(value, (tuple, list)) or len(value) < 3 or
            not all(math.isfinite(float(component)) for component in value[:3])):
        raise SlopeError("Vectorworks hat %s noch nicht bereitgestellt." % description)
    return tuple(float(component) for component in value[:3])


def _attributes(handle, class_name, color):
    vs.SetClass(handle, class_name)
    vs.SetPenFore(handle, tuple(color))
    vs.SetLSN(handle, 2)
    vs.SetOpacityN(handle, 100, 100)


def native_locus(point, factor, layer_z, class_name, color):
    local = (point[0]/factor, point[1]/factor, point[2]/factor-layer_z)
    vs.Locus3D(local)
    handle = vs.LNewObj()
    if not handle or vs.GetTypeN(handle) != 9:
        raise SlopeError("3D-Höhenpunkt konnte nicht erzeugt werden.")
    actual = _native_xyz(vs.GetLocus3D(handle), "die 3D-Lage des Höhenpunkts")
    _check_xyz(tuple(v*factor for v in actual), tuple(v*factor for v in local))
    _attributes(handle, class_name, color)
    return handle


def native_polygon(points, factor, layer_z, class_name, color):
    vs.BeginPoly3D()
    try:
        for x, y, z in points:
            vs.Add3DPt((x/factor, y/factor, z/factor-layer_z))
    finally:
        vs.EndPoly3D()
    handle = vs.LNewObj()
    if not handle or vs.GetTypeN(handle) != 25:
        raise SlopeError("3D-Verbindungslinie konnte nicht erzeugt werden.")
    vs.SetPolyClosed(handle, False)
    vs.SetFPat(handle, 0)
    if vs.GetVertNum(handle) != len(points) or vs.IsPolyClosed(handle):
        raise SlopeError("Die 3D-Verbindungslinie besitzt falsche Stützpunkte.")
    # GetPolyPt3D uses ZERO-based indices, unlike GetPolylineVertex.
    for index, expected in enumerate(points):
        x, y, z = _native_xyz(
            vs.GetPolyPt3D(handle, index), "den 3D-Stützpunkt %d" % (index + 1))
        # Unlike GetLocus3D, GetPolyPt3D already includes the layer elevation.
        _check_xyz((x*factor, y*factor, z*factor), expected)
    _attributes(handle, class_name, color)
    return handle


def ensure_symbol(options, factor, color):
    name = options["symbol"] or ("PD-GEF-Höhenpunkt-Kreuz-" + options["mode"].upper())
    if not options["symbol"] and options["mode"] == "3d":
        # New neutral artwork must not inherit the old definition's 2D class.
        name += "-V2"
    existing = vs.GetObject(name)
    if existing:
        if vs.GetTypeN(existing) != 16:
            raise SlopeError("Der Punktsymbolname ist anderweitig vergeben: " + name)
        return name
    if options["symbol"]:
        raise SlopeError("Punktsymbol fehlt in diesem Dokument: %s. Bitte importieren oder Standard-Kreuz wählen." % name)
    # Model-based cross, 10cm wide at factor 1. User can edit the symbol
    # resource later; existing definitions are NEVER rewritten.
    radius = .05
    vs.BeginSym(name)
    try:
        for a, b in (((-radius, 0), (radius, 0)), ((0, -radius), (0, radius))):
            if options["mode"] == "3d":
                native_polygon((a+(0.,), b+(0.,)), factor, 0, vs.ClassList(1), color)
            else:
                vs.MoveTo((a[0]/factor, a[1]/factor))
                vs.LineTo((b[0]/factor, b[1]/factor))
                _attributes(vs.LNewObj(), options["point_class"], color)
    except Exception:
        vs.EndSym()
        failed = vs.GetObject(name)
        if failed:
            vs.DelObject(failed)
        raise
    vs.EndSym()
    if not vs.GetObject(name):
        raise SlopeError("Das Standard-Punktsymbol konnte nicht angelegt werden.")
    return name


def marker(point, symbol_name, options, factor, layer_z):
    vs.Symbol(symbol_name, (point["x_m"]/factor, point["y_m"]/factor), 0.0)
    handle = vs.LNewObj()
    if not handle or vs.GetTypeN(handle) != 15:
        raise SlopeError("Bitte ein normales Punktsymbol verwenden, kein Symbol mit Objekt-/Gruppenumwandlung.")
    kind = vs.GetSymbolType(handle)
    if options["mode"] == "3d" and kind not in (1, 2):
        raise SlopeError("Für 3D bitte ein 3D-/Hybridsymbol oder das Standard-Kreuz wählen.")
    if options["mode"] == "2d" and kind != 0:
        raise SlopeError("Für reine 2D-Ausgabe bitte ein 2D-Symbol oder das Standard-Kreuz wählen.")
    # Symmetric scaling of the INSTANCE, never its shared definition.
    vs.SetObjectVariableInt(handle, 101, 2)
    # Scale type 2 is UNIFORM: only X is writable. VW applies it to all
    # axes; writing 103/104 in uniform mode reports native API errors.
    selectors = (102,)
    for selector in selectors:
        vs.SetObjectVariableReal(handle, selector, options["scale"])
    vs.ResetObject(handle)
    for selector in selectors:
        if abs(vs.GetObjectVariableReal(handle, selector) - options["scale"]) > 1e-8:
            raise SlopeError("Die Symbolskalierung wurde nicht übernommen.")
    if options["mode"] == "3d":
        target = (point["x_m"]/factor, point["y_m"]/factor, point["height_m"]/factor-layer_z)
        # VW 2026 may defer GetSymLoc3D during the first PIO reset. The symbol
        # was created at the known XY coordinate and Z=0, so that insertion
        # location is a deterministic, API-independent fallback.
        current = vs.GetSymLoc3D(handle)
        if (isinstance(current, (tuple, list)) and len(current) >= 3 and
                all(math.isfinite(float(value)) for value in current[:3])):
            x, y, z = (float(value) for value in current[:3])
        else:
            x, y, z = target[0], target[1], 0.0
        vs.Move3DObj(handle, target[0]-x, target[1]-y, target[2]-z)
        vs.ResetObject(handle)
        actual = vs.GetSymLoc3D(handle)
        if isinstance(actual, (tuple, list)) and len(actual) >= 3:
            _check_xyz(tuple(float(v)*factor for v in actual[:3]),
                       tuple(v*factor for v in target))
    vs.SetClass(handle, options["point_class"])
    vs.SetOpacityN(handle, 100, 100)
    return handle


def validate_symbols(symbol_names, output, factor, layer_z):
    """Probe real instances before changing live parameters (PIO resets defer).

    GetSymbolType is documented for instances, not symbol definitions. The
    temporary group owns all probe geometry and is removed on either outcome.
    """
    previous = vs.LNewObj()
    vs.BeginGroup()
    try:
        for mode, name in symbol_names.items():
            marker(dict(x_m=0., y_m=0., height_m=0.), name,
                   point_output.marker_options(output, mode), factor, layer_z)
    finally:
        vs.EndGroup()
        group = vs.LNewObj()
        if group and group != previous and vs.GetTypeN(group) == 11:
            vs.DelObject(group)


def create(chain, options, symbol_names, factor, layer_z, color, evaluate=None, line_color=None):
    """Called inside the managed group: caller owns rollback of ALL objects."""
    output_2d = point_output.marker_options(options, "2d")
    output_3d = point_output.marker_options(options, "3d")
    for point in chain["points"]:
        marker(point, symbol_names["2d"], output_2d, factor, layer_z)
        vs.Locus((point["x_m"]/factor, point["y_m"]/factor))
        handle = vs.LNewObj()
        if not handle or vs.GetTypeN(handle) != 17:
            raise SlopeError("2D-Höhenpunkt konnte nicht erzeugt werden.")
        vs.SetClass(handle, output_2d["point_class"])
        if options["mode"] == "3d":
            marker(point, symbol_names["3d"], output_3d, factor, layer_z)
            native_locus((point["x_m"], point["y_m"], point["height_m"]),
                         factor, layer_z, output_3d["point_class"], color)
    if options["mode"] == "3d":
        points = point_output.terrain_vertices(chain, evaluate, options["curve_tolerance_mm"])
        native_polygon(points, factor, layer_z, options["line_class"], color if line_color is None else line_color)
    if options["mode"] == "3d":
        vs.ResetOrientation3D()
