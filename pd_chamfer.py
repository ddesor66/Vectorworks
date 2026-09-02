"""Watertight 3D mesh primitives with a true equal-distance edge chamfer.

The geometry module is deliberately independent from Vectorworks. Coordinates
stay in the caller's document units; the adapter only publishes verified mesh
faces through APIs present in the official Vectorworks 2026 ``vs.py``.
"""

import math


class ChamferError(ValueError):
    pass


def _cross(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _sub(a, b):
    return a[0] - b[0], a[1] - b[1]


def _add(a, b):
    return a[0] + b[0], a[1] + b[1]


def _mul(a, value):
    return a[0] * value, a[1] * value


def _unit(vector):
    length = math.hypot(*vector)
    if not math.isfinite(length) or length <= 1e-12:
        raise ChamferError("Der 3D-Körper enthält eine zu kurze Kante.")
    return vector[0] / length, vector[1] / length


def _area(points):
    return sum(_cross(a, b) for a, b in zip(points, points[1:] + points[:1])) * .5


def _clean(points, chamfer):
    result = []
    for value in points:
        if not isinstance(value, (tuple, list)) or len(value) < 2:
            raise ChamferError("Die Grundfläche des 3D-Körpers ist ungültig.")
        point = float(value[0]), float(value[1])
        if not all(math.isfinite(v) and abs(v) < 1e90 for v in point):
            raise ChamferError("Die Grundfläche enthält ungültige Koordinaten.")
        if not result or math.dist(point, result[-1]) > 1e-10:
            result.append(point)
    if len(result) > 1 and math.dist(result[0], result[-1]) <= 1e-10:
        result.pop()
    changed = True
    while changed and len(result) > 3:
        changed = False
        for index in range(len(result)):
            before = result[index - 1]
            point = result[index]
            after = result[(index + 1) % len(result)]
            incoming, outgoing = _sub(point, before), _sub(after, point)
            li, lo = math.hypot(*incoming), math.hypot(*outgoing)
            # Native curve tessellation can leave a sub-chamfer residual edge.
            # Removing that residual stays entirely inside the 5 mm bevel zone.
            if min(li, lo) <= chamfer * 2.0001:
                result.pop(index)
                changed = True
                break
            ui, uo = _unit(incoming), _unit(outgoing)
            if abs(_cross(ui, uo)) <= 1e-10 and ui[0] * uo[0] + ui[1] * uo[1] > 0:
                result.pop(index)
                changed = True
                break
    if len(result) < 3 or abs(_area(result)) <= 1e-12:
        raise ChamferError("Die Grundfläche des 3D-Körpers besitzt keine gültige Fläche.")
    if any(math.dist(a, b) <= chamfer * 2.0001
           for a, b in zip(result, result[1:] + result[:1])):
        raise ChamferError("Eine Körperkante ist für die 5×5-mm-Fase zu kurz.")
    return tuple(result)


def prism_faces(points, z_bottom, z_top, chamfer):
    """Return closed mesh faces for a polygonal prism, chamfering every edge.

    ``chamfer`` is the equal setback on both adjoining faces. The returned
    body includes the horizontal top/bottom bevels, vertical corner bevels,
    and triangular three-edge transitions at every prism corner.
    """
    values = tuple(float(v) for v in (z_bottom, z_top, chamfer))
    if not all(math.isfinite(v) and abs(v) < 1e90 for v in values):
        raise ChamferError("Die 3D-Höhen oder die Fase sind ungültig.")
    z_bottom, z_top, chamfer = values
    if chamfer <= 0:
        raise ChamferError("Die Fase muss größer als 0 sein.")
    if z_top - z_bottom <= 2.0001 * chamfer:
        raise ChamferError("Der 3D-Körper ist für die 5×5-mm-Fase zu niedrig.")
    polygon = _clean(points, chamfer)
    orientation = 1.0 if _area(polygon) > 0 else -1.0
    inset, q_in, q_out = [], [], []
    count = len(polygon)
    for index, point in enumerate(polygon):
        incoming = _unit(_sub(point, polygon[index - 1]))
        outgoing = _unit(_sub(polygon[(index + 1) % count], point))
        n_in = (-incoming[1] * orientation, incoming[0] * orientation)
        n_out = (-outgoing[1] * orientation, outgoing[0] * orientation)
        denominator = 1.0 + incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
        if denominator <= 1e-6:
            raise ChamferError("Ein zu spitzer Rücksprung verhindert die 5×5-mm-Fase.")
        miter = _mul(_add(n_in, n_out), chamfer / denominator)
        if math.hypot(*miter) > min(
                math.dist(point, polygon[index - 1]),
                math.dist(point, polygon[(index + 1) % count])) * .49:
            raise ChamferError("Die 5×5-mm-Fase überschneidet sich an einer schmalen Ecke.")
        inset.append(_add(point, miter))
        q_in.append(_add(point, _mul(incoming, -chamfer)))
        q_out.append(_add(point, _mul(outgoing, chamfer)))

    low, high = z_bottom + chamfer, z_top - chamfer

    def p3(point, z):
        return point[0], point[1], z

    faces = [tuple(p3(point, z_bottom) for point in reversed(inset)),
             tuple(p3(point, z_top) for point in inset)]
    for index in range(count):
        following = (index + 1) % count
        faces.extend((
            (p3(inset[index], z_bottom), p3(inset[following], z_bottom),
             p3(q_in[following], low), p3(q_out[index], low)),
            (p3(inset[index], z_bottom), p3(q_out[index], low),
             p3(q_in[index], low)),
            (p3(q_out[index], low), p3(q_in[following], low),
             p3(q_in[following], high), p3(q_out[index], high)),
            (p3(q_in[index], low), p3(q_out[index], low),
             p3(q_out[index], high), p3(q_in[index], high)),
            (p3(q_out[index], high), p3(q_in[following], high),
             p3(inset[following], z_top), p3(inset[index], z_top)),
            (p3(q_in[index], high), p3(inset[index], z_top),
             p3(q_out[index], high)),
        ))
    return tuple(faces)


def create_mesh(api, faces):
    """Publish closed faces as one native Vectorworks mesh (object type 40)."""
    previous = api.LNewObj()
    api.BeginMesh()
    for face in faces:
        if len(face) < 3:
            raise ChamferError("Eine 3D-Meshfläche besitzt zu wenige Punkte.")
        api.BeginPoly3D()
        for point in face:
            api.Add3DPt(tuple(float(value) for value in point))
        api.EndPoly3D()
    api.EndMesh()
    handle = api.LNewObj()
    if not handle or handle == previous or int(api.GetTypeN(handle)) != 40:
        raise ChamferError("Vectorworks konnte den gefasten 3D-Körper nicht erzeugen.")
    api.ResetOrientation3D()
    return handle
