"""Independent 2D annotation pairs, linked to their point or segment owner.

The label PIO's insertion vector is its user-controlled displacement from
the current owner anchor. Its two texts move together; owner geometry does
not move. Owner resets only request label resets, never the other way round.
"""
import math
import uuid

import vs
from pd_plan_frame import PlanFrame

from . import core, label_layout, live_model
from . import vw_adapter as adapter


PREFIX = "PD-GEF-T-"


def ensure(owner, data, created):
    from . import live_objects as live
    owner_name = vs.GetName(owner)
    if data["role"] == "point":
        targets = [("point", None)]
    else:
        targets = [("segment", (a["number"], b["number"]))
                   for a, b in zip(data["chain"]["points"], data["chain"]["points"][1:])]
    names = []
    for kind, pair in targets:
        identity = str(uuid.uuid5(uuid.NAMESPACE_URL, owner_name+":"+kind+":"+str(pair)))
        name = PREFIX+identity
        handle = vs.GetObject(name)
        if handle:
            old = live.data_of(handle)
            if not old or old.get("role") != "label" or old.get("owner") != owner_name:
                raise core.SlopeError("Der Name einer Beschriftung wird von einem anderen Objekt verwendet.")
        else:
            payload = dict(schema=1, role="label", id=identity, owner=owner_name, kind=kind, pair=pair)
            handle = live._new_object((0., 0.), payload, name, created)
            layer = vs.GetLayer(owner)
            if vs.GetParent(handle) != layer:
                if not vs.SetParent(handle, layer) or vs.GetParent(handle) != layer:
                    raise core.SlopeError("Die Beschriftung konnte nicht als eigenständiges Objekt angelegt werden.")
            if not vs.AddAssociation(owner, 4, handle):
                raise core.SlopeError("Bezug der Beschriftung konnte nicht gespeichert werden.")
        names.append(name)
    removed = [name for name in data.get("labels", ()) if name not in names]
    data.update(labels=names, separate_labels=True)
    live.write_data(owner, data)
    return removed


def reset_for(data):
    for name in data.get("labels", ()):
        handle = vs.GetObject(name)
        if handle:
            vs.ResetObject(handle)


def delete_obsolete(names):
    """Only labels no longer referenced by their successfully updated owner."""
    from . import live_objects as live
    for name in names:
        handle = vs.GetObject(name)
        if not handle:
            continue
        data = live.data_of(handle)
        if not data or data["role"] != "label" or name != PREFIX+data["id"]:
            raise core.SlopeError("Eine veraltete Beschriftung konnte nicht sicher zugeordnet werden.")
        owner = vs.GetObject(data["owner"])
        owner_data = live.data_of(owner)
        if owner_data and name not in owner_data.get("labels", ()):
            vs.DelObject(handle)


def draw(handle, data):
    from . import live_objects as live, live_render as render
    if vs.GetName(handle) != PREFIX+data["id"]:
        raise core.SlopeError("Eine Beschriftung wurde kopiert. Bitte die originale Beschriftung verschieben.")
    owner = vs.GetObject(data["owner"])
    owner_data = live.data_of(owner)
    if not owner_data or vs.GetName(handle) not in owner_data.get("labels", ()):
        return
    factor = adapter.units_to_meters()
    prefs = owner_data["preferences"]
    scale = max(1., float(vs.GetLScale(vs.GetLayer(handle)) or 1.))
    offset = prefs["offset_mm"] / 1000. * scale / factor
    angle = vs.GetSymRot(handle)
    frame = PlanFrame(float(owner_data.get("text_angle", 0.))-angle)
    if data["kind"] == "point" and owner_data["role"] == "point":
        point = live.read_point(owner, owner_data)
        anchor = live_model.local_xy((point["x_m"]/factor, point["y_m"]/factor), (0., 0.), angle)
        specs = render.point_label_specs(point, anchor, frame, offset, prefs)
        style = prefs["classes"]["height"]
    elif data["kind"] == "segment" and owner_data["role"] == "chain":
        chain = live.read_chain(owner, owner_data)
        index = next((i for i, (a, b) in enumerate(zip(chain["points"], chain["points"][1:]))
                      if [a["number"], b["number"]] == list(data["pair"])), None)
        if index is None:
            return
        local = live_model.local_chain(chain, (0., 0.), angle)
        anchor, specs = render.segment_label_specs(local, index, factor, frame, offset, prefs)
        style = prefs["classes"]["line"]
    else:
        raise core.SlopeError("Beschriftung und Bezugsobjekt passen nicht zusammen.")
    texts = [adapter._create_text(value, xy, rotation, cls, prefs) for value, xy, rotation, cls in specs]
    displacement = live_model.local_xy(vs.GetSymLoc(handle), (0., 0.), angle)
    if math.hypot(*displacement)*factor > 1e-6:
        start = anchor[0]-displacement[0], anchor[1]-displacement[1]
        end = label_layout.leader_end(start, [vs.GetBBox(text) for text in texts], .3/1000.*scale/factor)
        if math.hypot(end[0]-start[0], end[1]-start[1])*factor > 1e-6:
            adapter._create_line(start, end, style)
