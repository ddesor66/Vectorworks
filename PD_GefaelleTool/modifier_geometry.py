"""PIO-owned point/breakline modifiers; no exports or site-model resets."""
import vs

from .core import SlopeError
from . import point_geometry


def point(xyz, factor, layer_z, class_name, color, modifier=False):
    """One native locus, owned by the live point; symbol artwork stays neutral."""
    if not modifier:
        return point_geometry.native_locus(xyz, factor, layer_z, class_name, color)
    previous, active_class = vs.LNewObj(), vs.ActiveClass()
    group = None
    try:
        vs.BeginGroup()
        try:
            locus = point_geometry.native_locus(xyz, factor, layer_z, class_name, color)
            before = vs.GetLocus3D(locus)
            vs.SetPadAttrs(locus)
            if not vs.GetClass(locus) or vs.GetClass(locus) == class_name:
                raise SlopeError("Vectorworks hat die Punkt-Modifikator-Zuordnung nicht übernommen.")
            vs.SetPenFore(locus, tuple(color))
            vs.SetLSN(locus, 2)
            if vs.GetLocus3D(locus) != before:
                raise SlopeError("Geländemodifikator hat die Punktlage verändert; Ausgabe abgebrochen.")
        finally:
            vs.EndGroup()
            candidate = vs.LNewObj()
            if candidate and candidate != previous and vs.GetTypeN(candidate) == 11:
                group = candidate
        if group is None:
            raise SlopeError("Die 3D-Punktmodifikator-Komponente konnte nicht erzeugt werden.")
        vs.SetClass(group, class_name)
        return group
    except Exception:
        if group is not None:
            vs.DelObject(group)
        raise
    finally:
        if vs.ActiveClass() != active_class:
            vs.NameClass(active_class)


def connection(points, factor, layer_z, class_name, color, modifier=False):
    if not modifier:
        return point_geometry.native_polygon(points, factor, layer_z, class_name, color)

    # Only this generated 3D component is wrapped, never the independent PIOs.
    # The outer _3D class controls display; SetPadAttrs supplies the native,
    # localized technical class on the ONE actual open 3D polygon inside.
    previous, active_class = vs.LNewObj(), vs.ActiveClass()
    group = None
    try:
        vs.BeginGroup()
        try:
            polygon = point_geometry.native_polygon(points, factor, layer_z, class_name, color)
            before = tuple(vs.GetPolyPt3D(polygon, i) for i in range(vs.GetVertNum(polygon)))
            line_weight = vs.GetLW(polygon)
            vs.SetPadAttrs(polygon)
            if not vs.GetClass(polygon) or vs.GetClass(polygon) == class_name:
                raise SlopeError("Vectorworks hat die native Modifikator-Zuordnung nicht übernommen.")
            # Native modifier attributes may change the pen; preserve our style.
            vs.SetPenFore(polygon, tuple(color))
            vs.SetLSN(polygon, 2)
            vs.SetLW(polygon, line_weight)
            vs.SetFPat(polygon, 0)
            after = tuple(vs.GetPolyPt3D(polygon, i) for i in range(vs.GetVertNum(polygon)))
            if vs.IsPolyClosed(polygon) or before != after:
                raise SlopeError("Geländemodifikator hat die 3D-Stützpunkte verändert; Ausgabe abgebrochen.")
        finally:
            vs.EndGroup()
            candidate = vs.LNewObj()
            if candidate and candidate != previous and vs.GetTypeN(candidate) == 11:
                group = candidate
        if group is None:
            raise SlopeError("Die 3D-Modifikator-Komponente konnte nicht erzeugt werden.")
        vs.SetClass(group, class_name)
        return group
    except Exception:
        if group is not None:
            # Delete only the just-created component, never existing geometry.
            vs.DelObject(group)
        raise
    finally:
        if vs.ActiveClass() != active_class:
            vs.NameClass(active_class)
