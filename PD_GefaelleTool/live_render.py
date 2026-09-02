"""PIO-owned geometry: one independent height point or one chain drawing."""
import math

import vs
from pd_plan_frame import PlanFrame

from . import core, label_format, live_model, modifier_geometry, point_geometry, point_output
from . import vw_adapter as adapter


def context(handle, data):
    factor = adapter.units_to_meters()
    preferences = data["preferences"]
    scale = float(vs.GetLScale(vs.GetLayer(handle)) or 1.)
    offset = preferences["offset_mm"] / 1000. * max(1., scale) / factor
    angle = vs.GetSymRot(handle)
    frame = PlanFrame(float(data.get("text_angle", 0.))-angle)
    origin = vs.GetSymLoc(handle)
    # CreateCustomObjectN can trigger this reset before Vectorworks exposes a
    # 3D insertion tuple. PD point/chain PIOs are deliberately created at Z=0.
    location_3d = adapter.symbol_location_3d(handle)
    z = location_3d[2] if location_3d is not None else 0.0
    layer_z = adapter.layer_elevation_units(vs.GetLayer(handle), factor) + z
    return factor, offset, angle, frame, origin, layer_z


def draw_point(handle, data, point):
    factor, offset, angle, frame, origin, layer_z = context(handle, data)
    preferences, output = data["preferences"], data["output"]
    classes = preferences["classes"]
    local = dict(point, x_m=0., y_m=0.)
    opts2d = point_output.marker_options(output, "2d")
    point_geometry.marker(local, data["symbols"]["2d"], opts2d, factor, layer_z)
    vs.Locus((0., 0.))
    locus = vs.LNewObj()
    if not locus or vs.GetTypeN(locus) != 17:
        raise core.SlopeError("2D-Punkt konnte nicht erzeugt werden.")
    vs.SetClass(locus, opts2d["point_class"])
    if output["mode"] == "3d":
        opts3d = point_output.marker_options(output, "3d")
        point_geometry.marker(local, data["symbols"]["3d"], opts3d, factor, layer_z)
        modifier_geometry.point((0., 0., point["height_m"]), factor, layer_z,
                                 opts3d["point_class"], classes["height"]["color"],
                                 output.get("point_terrain_modifier", False))
    if not data.get("separate_labels"):
        for value, xy, rotation, cls in point_label_specs(point, (0., 0.), frame, offset, preferences):
            adapter._create_text(value, xy, rotation, cls, preferences)
    if output["mode"] == "3d":
        vs.ResetOrientation3D()


def draw_chain(handle, data, chain):
    factor, offset, angle, frame, origin, layer_z = context(handle, data)
    preferences, output = data["preferences"], data["output"]
    classes = preferences["classes"]
    local = live_model.local_chain(chain, (origin[0]*factor, origin[1]*factor), angle)
    coordinates = adapter._drawing_coordinates(local)
    evaluate = None
    if local.get("curve"):
        curve_handle = adapter._create_curve(local, classes["line"])
        evaluate = adapter._curve_evaluator(curve_handle, factor, local["curve"]["length_m"])
    else:
        for first, second in zip(coordinates, coordinates[1:]):
            adapter._create_line(first, second, classes["line"])
    if output["mode"] == "3d":
        vertices = point_output.terrain_vertices(local, evaluate, output["curve_tolerance_mm"])
        modifier_geometry.connection(vertices, factor, layer_z, output["line_class"], classes["line"]["color"],
                                     output.get("terrain_modifier", False))
    if not data.get("separate_labels"):
        for index in range(len(local["points"])-1):
            _, specs = segment_label_specs(local, index, factor, frame, offset, preferences)
            for value, xy, rotation, cls in specs:
                adapter._create_text(value, xy, rotation, cls, preferences)
    if output["mode"] == "3d":
        vs.ResetOrientation3D()


def point_label_specs(point, anchor, frame, offset, preferences):
    classes = preferences["classes"]
    return [("P:%d" % point["number"], frame.offset(anchor, 0., offset), frame.angle, classes["number"]),
            (label_format.annotation("height", point["height_m"], preferences),
             frame.offset(anchor, 0., -offset), frame.angle, classes["height"])]


def segment_label_specs(chain, index, factor, frame, offset, preferences):
    segment = core.segment_rows(chain)[index]
    a, b = chain["points"][index:index+2]
    first, second = (a["x_m"]/factor, a["y_m"]/factor), (b["x_m"]/factor, b["y_m"]/factor)
    dx, dy = second[0]-first[0], second[1]-first[1]
    middle = ((first[0]+second[0])*.5, (first[1]+second[1])*.5)
    if chain.get("curve"):
        label = chain["curve"]["labels"][index]
        middle = label["x_m"]/factor, label["y_m"]/factor
        dx, dy = label["tx"], label["ty"]
    norm = math.hypot(dx, dy)
    nx, ny = -dy/norm, dx/norm
    rotation = adapter._readable_angle((0., 0.), (dx, dy), frame.angle)
    specs = []
    for kind, value, sign in (("slope", segment["slope_percent"], 1.), ("length", segment["length_m"], -1.)):
        specs.append((label_format.annotation(kind, value, preferences),
                      (middle[0]+sign*nx*offset, middle[1]+sign*ny*offset), rotation, preferences["classes"][kind]))
    return middle, specs
