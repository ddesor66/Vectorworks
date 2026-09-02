"""Native Vectorworks Stake bridges for the built-in Grade tool.

Vectorworks 2026 resolves an initial Grade elevation from another Grade,
a Stake Object, or a site model.  A generic PIO or a 3D locus is not part of
that contract.  Every PD height point therefore owns one derived, top-level
Stake Object at the same insertion point and elevation.  The PD point remains
the only source of truth; the bridge has no label and does not modify terrain.
"""
import math

import vs

from . import core, point_output
from . import vw_adapter as adapter


PLUGIN = "Stake Object"
PREFIX = "PD-GEF-VW-FANG-"
DELETE_WITH_OWNER = 4
def _available():
    """Allow the pure-Python test doubles to omit native PIO introspection."""
    return (hasattr(vs, "AddAssociation")
            and hasattr(vs, "CreateCustomObjectN")
            and hasattr(vs, "GetFldName")
            and hasattr(vs, "GetObject")
            and hasattr(vs, "GetParametricRecord")
            and hasattr(vs, "GetParent")
            and hasattr(vs, "GetSymLoc")
            and hasattr(vs, "GetSymLoc3D")
            and hasattr(vs, "GetTypeN")
            and hasattr(vs, "HMove")
            and hasattr(vs, "Move3DObj")
            and hasattr(vs, "NumFields")
            and hasattr(vs, "ResetObject")
            and hasattr(vs, "SetClass")
            and hasattr(vs, "SetName")
            and hasattr(vs, "SetParent")
            and hasattr(vs, "SetRField"))


def _field_names(handle):
    record = vs.GetParametricRecord(handle)
    if not record:
        return set()
    return {str(vs.GetFldName(record, index))
            for index in range(1, int(vs.NumFields(record) or 0) + 1)}


def _set_if_present(handle, fields, name, value):
    if name in fields:
        vs.SetRField(handle, PLUGIN, name, str(value))


def _configure(handle, local_z):
    fields = _field_names(handle)
    if "Z Value" not in fields:
        raise core.SlopeError(
            "Der Vectorworks-Vermessungspunkt besitzt kein Feld 'Z Value'. "
            "Bitte die Vectorworks-2026-Installation prüfen.")

    # The legacy universal parameter name is still "Include as site model
    # data", but in VW 2026 it is the popup that also contains the safe
    # graphic-only mode.  Do not use a boolean here: the user's last Stake
    # preference could otherwise leave this derived point as a modifier.
    _set_if_present(handle, fields, "Include as site model data",
                    "Use as 2D graphic only")
    _set_if_present(handle, fields, "Style", "Point")
    _set_if_present(handle, fields, "Label Reference", "No Label")
    _set_if_present(handle, fields, "Label ReferenceN", "No Label")
    _set_if_present(handle, fields, "UseAnnotation", "Built-in Tag")
    _set_if_present(handle, fields, "Display Leader Line", "False")
    vs.SetRField(handle, PLUGIN, "Z Value", "%.12g" % local_z)


def _sync_position(handle, xy, local_z):
    x, y = vs.GetSymLoc(handle)
    if math.hypot(float(x)-xy[0], float(y)-xy[1]) > 1e-8:
        vs.HMove(handle, xy[0]-float(x), xy[1]-float(y))
    _configure(handle, local_z)
    vs.ResetObject(handle)

    # Z Value is the normal Stake contract.  Move3DObj is a verified fallback
    # for installations where the compiled PIO applies the field on a deferred
    # reset; it also keeps the insertion matrix correct for 3D snapping.
    location = adapter.symbol_location_3d(handle)
    if location is None:
        # The Z Value field is the authoritative Stake contract. A freshly
        # created native PIO may not expose its 3D matrix until Vectorworks has
        # completed the requested reset; verify it on a later synchronization.
        return
    z = location[2]
    if abs(z-local_z) > 1e-7:
        vs.Move3DObj(handle, 0., 0., local_z-z)
        vs.ResetObject(handle)
        location = adapter.symbol_location_3d(handle)
        if location is None:
            return
        z = location[2]
    if abs(z-local_z) > 1e-5:
        raise core.SlopeError(
            "Der Vectorworks-Höhenfangpunkt konnte nicht auf die PD-Höhe gesetzt werden.")


def ensure(owner, data, point, created=None):
    """Create or synchronize the native Stake owned by a PD height point."""
    if data.get("role") != "point" or not _available():
        return None
    name = PREFIX + str(data["id"])
    handle = vs.GetObject(name)
    is_new = not handle
    if is_new:
        factor = adapter.units_to_meters()
        handle = vs.CreateCustomObjectN(
            PLUGIN, (point["x_m"]/factor, point["y_m"]/factor), 0., False)
        if not handle or vs.GetTypeN(handle) != 86:
            raise core.SlopeError(
                "Der native Vectorworks-Vermessungspunkt für den Höhenfang "
                "konnte nicht erzeugt werden.")
        if created is not None:
            created.append(handle)
        vs.SetName(handle, name)
        if vs.GetName(handle) != name:
            raise core.SlopeError("Der Vectorworks-Höhenfangpunkt konnte nicht benannt werden.")
        layer = vs.GetLayer(owner)
        if vs.GetParent(handle) != layer:
            if not vs.SetParent(handle, layer) or vs.GetParent(handle) != layer:
                raise core.SlopeError(
                    "Der Vectorworks-Höhenfangpunkt konnte nicht auf der Punktebene angelegt werden.")
        if not vs.AddAssociation(owner, DELETE_WITH_OWNER, handle):
            raise core.SlopeError(
                "Der Vectorworks-Höhenfangpunkt konnte nicht mit dem PD-Punkt verknüpft werden.")
    elif vs.GetTypeN(handle) != 86 or not vs.GetParametricRecord(handle):
        raise core.SlopeError(
            "Der reservierte Name des Vectorworks-Höhenfangpunkts ist anderweitig belegt.")

    factor = adapter.units_to_meters()
    layer_z = adapter.layer_elevation_units(vs.GetLayer(owner), factor)
    xy = point["x_m"]/factor, point["y_m"]/factor
    local_z = point["height_m"]/factor-layer_z
    marker_class = point_output.marker_options(data["output"], "2d")["point_class"]
    vs.SetClass(handle, marker_class)
    _sync_position(handle, xy, local_z)
    return handle
