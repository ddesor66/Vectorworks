# -*- coding: utf-8 -*-
"""Narrow Vectorworks 2026 adapter for PD Gefälle-Tool."""

from __future__ import absolute_import

import json
import math
import copy

import vs
from pd_plan_frame import PlanFrame

from . import core
from . import curve_path
from . import point_output
from . import point_geometry
from . import insert_point
from . import settings
from . import label_format


TYPE_LINE = 2
TYPE_POLYGON = 5
TYPE_GROUP = 11
TYPE_POLYLINE = 21
RECORD_NAME = "PD_GefaelleDaten"
RECORD_FIELD = "KetteJSON"
GROUP_PREFIX = "PD-GEF-"
_point_input_token = None
_point_input_callback = None


def _mouse_click_sample():
    """Return the real Windows left-button edge hidden by RunTempTool."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        raw = int(user32.GetAsyncKeyState(1))
        return (bool(raw & 0x8000), bool(raw & 1),
                int(kernel32.GetTickCount64()), int(user32.GetDoubleClickTime()))
    except (AttributeError, OSError, TypeError, ValueError):
        return False, False, 0, 500


def _backspace_pressed():
    """Return True once for the physical Backspace key press."""
    try:
        import ctypes
        return bool(int(ctypes.windll.user32.GetAsyncKeyState(8)) & 1)
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _backspace_down():
    """Return whether Backspace is physically held right now."""
    try:
        import ctypes
        return bool(int(ctypes.windll.user32.GetAsyncKeyState(8)) & 0x8000)
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _enter_pressed():
    """Return True while Enter is held or once for its physical edge."""
    try:
        import ctypes
        return bool(int(ctypes.windll.user32.GetAsyncKeyState(13)) & 0x8001)
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def _start_backspace_watch(token, state):
    """Remember Backspace while VW is between Python tool callbacks."""
    if getattr(vs, "__name__", "") != "vs":
        return
    try:
        import ctypes
        import threading
        import time
        user32 = ctypes.windll.user32
    except (AttributeError, ImportError, OSError):
        return

    def watch():
        held = False
        while _point_input_token is token:
            try:
                down = bool(int(user32.GetAsyncKeyState(8)) & 0x8000)
                if down and not held:
                    state["backspace_pending"] = True
                held = down
                time.sleep(0.01)
            except (OSError, TypeError, ValueError):
                return

    threading.Thread(target=watch, name="PD-Gefaelle-Backspace", daemon=True).start()


def object_type(handle):
    return int(vs.GetTypeN(handle)) if handle else 0


def layer_elevation_units(layer, factor):
    """GetLayerElevation is ALWAYS mm; drawing coordinates use document units."""
    value = float(vs.GetLayerElevation(layer)[0]) / 1000.0 / factor
    if not math.isfinite(value):
        raise core.SlopeError("Ebenenhöhe konnte nicht gelesen werden.")
    return value


def alert(message):
    try:
        vs.AlertInform(str(message), "", False)
    except Exception:
        vs.AlrtDialog(str(message))


def units_to_meters():
    values = vs.GetUnits()
    try:
        units_per_inch = float(values[3])
    except (TypeError, ValueError, IndexError) as error:
        raise core.SlopeError("Dokumenteinheiten konnten nicht gelesen werden.") from error
    if not math.isfinite(units_per_inch) or units_per_inch <= 0.0:
        raise core.SlopeError("Die Dokumenteinheiten sind ungültig.")
    return 0.0254 / units_per_inch


def _point(value):
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            pass
    return None


def selected_handles():
    result = []
    try:
        # SEL also matches descendants of selected containers in VW 2026.
        # Do not treat an unselected nested slope as an additional selection.
        def collect(handle):
            if vs.Selected(handle):
                result.append(handle)
        vs.ForEachObject(collect, "(SEL=TRUE)")
    except Exception as error:
        raise core.SlopeError("Die Zeichnungsauswahl konnte nicht gelesen werden.") from error
    return tuple(result)


def extract_path(handle):
    object_type = int(vs.GetTypeN(handle) or 0)
    points = []
    if object_type == TYPE_LINE:
        points = [_point(vs.GetSegPt1(handle)),
                  _point(vs.GetSegPt2(handle))]
    elif object_type in (TYPE_POLYGON, TYPE_POLYLINE):
        count = int(vs.GetVertNum(handle) or 0)
        for index in range(1, count + 1):
            if object_type == TYPE_POLYLINE:
                raw = vs.GetPolylineVertex(handle, index)
                if not isinstance(raw, (tuple, list)) or len(raw) < 2:
                    raise core.SlopeError("Polylinienpunkt %d konnte nicht gelesen werden." % index)
                if int(raw[1] or 0) != 0:
                    return _extract_curve(handle)
                candidate = _point(raw[0])
            else:
                candidate = _point(vs.GetPolyPt(handle, index))
            points.append(candidate)
    else:
        raise core.SlopeError(
            "Bitte genau eine Linie, Polylinie oder ein Polygon markieren.")
    if any(point is None for point in points):
        raise core.SlopeError("Die Stützpunkte konnten nicht vollständig gelesen werden.")
    factor = units_to_meters()
    return {"points": tuple((point[0] * factor, point[1] * factor) for point in points),
            "curve": None}


def _curve_vertices(handle, factor):
    vertices = []
    count = int(vs.GetVertNum(handle))
    for index in range(1, count + 1):
        point, kind, radius = vs.GetPolylineVertex(handle, index)
        vertices.append(dict(x_m=float(point[0]) * factor, y_m=float(point[1]) * factor,
                             type=int(kind), radius_m=float(radius) * factor))
    return vertices


def _curve_evaluator(handle, factor, length_m):
    # VW2026 stationing uses a slightly shorter native tessellation domain
    # than HPerimN's arc length. Calibrate that domain against the independent
    # last control vertex; preserve the original curve and true arc length.
    native_length = length_m
    end = vs.PointAlongPolyN(handle, length_m / factor, 1e-7 / factor)
    if not end[0]:
        if not vs.PointAlongPolyN(handle, 0., 1e-7 / factor)[0]:
            raise core.SlopeError("Der Kurvenanfang konnte nicht bestimmt werden.")
        low, high = 0., length_m
        for _ in range(48):
            middle = (low + high) * .5
            result = vs.PointAlongPolyN(handle, middle / factor, 1e-7 / factor)
            if result[0]:
                low, end = middle, result
            else:
                high = middle
        endpoint = _point(vs.GetPolylineVertex(handle, vs.GetVertNum(handle))[0])
        actual = _point(end[1])
        if (endpoint is None or actual is None
                or math.hypot(actual[0]-endpoint[0], actual[1]-endpoint[1])*factor > 1e-5
                or length_m-low > max(1e-5, length_m*1e-4)):
            raise core.SlopeError("Native Kurvenstationierung weicht vom Original ab; keine Ersatzgerade erzeugt.")
        native_length = low

    def at(station):
        return vs.PointAlongPolyN(handle, station / length_m * native_length / factor, 1e-7 / factor)

    def evaluate(station_m):
        if not math.isfinite(station_m) or not 0 <= station_m <= length_m:
            raise core.SlopeError("Kurvenstation liegt außerhalb des Linienverlaufs.")
        ok, point, tangent = at(station_m)
        if not ok:
            raise core.SlopeError("Ein Punkt auf der Gefällekurve konnte nicht berechnet werden.")
        point, tangent = _point(point), _point(tangent)
        if (point is None or tangent is None
                or not all(math.isfinite(v) for v in point + tangent)):
            raise core.SlopeError("Vectorworks liefert ungültige Kurvenkoordinaten.")
        norm = math.hypot(*tangent)
        if norm <= 1e-12:
            # At a corner, derive the direction from neighbouring on-curve
            # points. Distances still come from HPerimN, never these chords.
            delta = min(length_m * 1e-4, 1e-5)
            before = at(max(0, station_m - delta))
            after = at(min(length_m, station_m + delta))
            if not before[0] or not after[0]:
                raise core.SlopeError("Kurventangente konnte nicht bestimmt werden.")
            tangent = (after[1][0] - before[1][0], after[1][1] - before[1][1])
            norm = math.hypot(*tangent)
            if not math.isfinite(norm) or norm <= 1e-12:
                raise core.SlopeError("Kurventangente ist nicht eindeutig.")
        return (point[0] * factor, point[1] * factor), (tangent[0] / norm, tangent[1] / norm)
    return evaluate


def _extract_curve(handle):
    """Read the original native curve; no conversion or edits to the source."""
    if vs.IsPolyClosed(handle):
        raise core.SlopeError(
            "Geschlossene Gefällekurve: bitte am gewünschten Anfangspunkt öffnen, "
            "damit Anfangs- und Endhöhe eindeutig sind.")
    factor = units_to_meters()
    vertices = _curve_vertices(handle, factor)
    # GetVertexVisibility is zero-based; the absent closing edge of an open
    # polyline is not an interruption. Do not silently bridge hidden edges.
    if any(not vs.GetVertexVisibility(handle, i) for i in range(len(vertices) - 1)):
        raise core.SlopeError("Die Gefällekurve enthält ausgeblendete Teilstücke. Bitte eine durchgängige Kurve wählen.")
    length_m = float(vs.HPerimN(handle)) * factor
    evaluate = _curve_evaluator(handle, factor, length_m)
    points, stations, labels = curve_path.station_vertices(vertices, length_m, evaluate)
    curve = dict(kind="polyline", closed=False, vertices=vertices,
                 length_m=length_m, stations_m=stations, labels=labels)
    core.curve_lengths(curve, points)
    return dict(points=points, curve=curve)


def selected_source_path():
    handles = tuple(handle for handle in selected_handles()
                    if int(vs.GetTypeN(handle) or 0)
                    in (TYPE_LINE, TYPE_POLYGON, TYPE_POLYLINE))
    if len(handles) != 1:
        raise core.SlopeError(
            "Vor dem Start genau eine Linie, Polylinie oder ein Polygon markieren.")
    return extract_path(handles[0])


def cancel_point_input():
    """Invalidate callbacks from an abandoned/older command invocation."""
    global _point_input_token
    _point_input_token = None
    try:
        from . import point_tool
        point_tool.cancel()
    except (ImportError, AttributeError):
        # The native tool module is deliberately optional for isolated adapter
        # tests and for the one-point RunTempTool pickers below.
        pass


def draw_points(on_complete, first_point=None, help_text=None,
                undo_name="PD Gefällelinie zeichnen"):
    """Collect an unlimited chain and finish on Vectorworks' real double-click."""
    del undo_name
    _pick_points(None, on_complete, first_point, help_text)


def draw_height_points(on_complete):
    """Collect several independent point positions with the native tool."""
    help_text = ("Höhenpunkte nacheinander anklicken. Doppelklick: Positionsfolge abschließen. "
                 "Esc: ohne Erstellung abbrechen.")
    _pick_points(None, on_complete, help_text=help_text)


def _pick_points(count, on_complete, first_point=None, help_text=None):
    """One native temp-tool session, never nested GetPt calls.

    Python RunTempTool is asynchronous in VW2026. Events 105 (point), 104
    (complete), 4 (cleanup) and the return contract were verified natively.
    The callback remains strongly referenced until the next invocation.
    No geometry or dialogs are created during point acquisition.
    """
    global _point_input_token, _point_input_callback
    factor = units_to_meters()
    points = []
    if first_point is not None:
        points.append((first_point[0] / factor, first_point[1] / factor))
    accepted_counts = []
    token = object()
    _point_input_token = token
    state = dict(native_count=0, finish_requested=False, complete=False, error=None,
                 last_native_click_ms=None, backspace_pending=False,
                 backspace_held=False, suppressed_point=None)
    _start_backspace_watch(token, state)

    def remove_last(native_count, allow_fallback=False):
        """Mirror one native Backspace without accepting its cursor again."""
        removed = None
        if native_count < state["native_count"]:
            while accepted_counts and accepted_counts[-1] > native_count:
                accepted_counts.pop()
                removed = points.pop()
            state["native_count"] = native_count
        elif allow_fallback and accepted_counts:
            accepted_counts.pop()
            removed = points.pop()
        if removed is not None:
            state["suppressed_point"] = removed
        return removed

    def hint(prefix=""):
        if count == 1:
            return help_text or "Höhenpunkt einfügen: Verbindung anklicken. Danach Anschlusshöhe prüfen. Esc: abbrechen."
        if help_text:
            return prefix + help_text
        return ("%sGefälle: Punkt %d anklicken. Abschließen: Doppelklick am letzten Punkt "
                "(mindestens 2 Punkte). Esc: abbrechen.") % (prefix, len(points) + 1)

    def callback(action, _msg1, _msg2):
        if _point_input_token is not token:
            return 0
        try:
            # VW routes Backspace through either draw (103) or generic status
            # (5). Consume its physical edge before dispatching the action.
            undo_requested = False
            if action not in (3, 4):
                pending = bool(state.get("backspace_pending"))
                state["backspace_pending"] = False
                physical_backspace = _backspace_pressed()
                backspace_down = _backspace_down()
                was_held = bool(state.get("backspace_held"))
                undo_requested = physical_backspace or (
                    not was_held and (backspace_down or pending))
                state["backspace_held"] = backspace_down
            if points and undo_requested:
                native_count = int(vs.vstNumPts())
                remove_last(native_count, allow_fallback=True)
                state["last_native_click_ms"] = None
                vs.vstSetHelpString(hint())
            if action == 3:
                # Official vstSetPtBehavior: 4 = any number of points, double-click completes.
                vs.vstSetPtBehavior(4 if count is None else 1)
                vs.vstSetHelpString(hint())
            elif action == 102 and count is None:
                # In VW 2026 the double-click event can arrive while
                # vstNumPts still contains only the preceding click. Accept
                # the current cursor point as the final vertex in that case.
                candidate = _point(vs.vstGetCurrPt2D())
                if candidate is None or not all(math.isfinite(v) for v in candidate):
                    raise core.SlopeError("Vectorworks hat keinen gültigen Doppelklickpunkt geliefert.")
                if not points or math.hypot(candidate[0]-points[-1][0],
                                            candidate[1]-points[-1][1]) * factor > 1e-9:
                    points.append(candidate)
                    accepted_counts.append(max(state["native_count"] + 1, 1))
                if len(points) >= 2:
                    state["finish_requested"] = True
            elif action in (100, 101, 105):
                native_count = int(vs.vstNumPts())
                # VW sends this event repeatedly for the SAME point.
                if native_count > state["native_count"]:
                    candidate = _point(vs.vstGetCurrPt2D())
                    if candidate is None or not all(math.isfinite(v) for v in candidate):
                        raise core.SlopeError("Vectorworks hat keinen gültigen Klickpunkt geliefert.")
                    suppressed = state.get("suppressed_point")
                    if (suppressed is not None and
                            math.hypot(candidate[0]-suppressed[0],
                                       candidate[1]-suppressed[1]) * factor <= 1e-9):
                        state["last_native_click_ms"] = None
                        if count is None and len(points) >= 2 and _enter_pressed():
                            state["finish_requested"] = True
                            state["complete"] = True
                    else:
                        state["suppressed_point"] = None
                        if points and math.hypot(candidate[0]-points[-1][0], candidate[1]-points[-1][1])*factor <= 1e-9:
                            if count is None and len(points) >= 2:
                                state["finish_requested"] = True
                            else:
                                vs.vstSetHelpString(hint("Gleicher Punkt: anderen Punkt wählen. "))
                        else:
                            points.append(candidate)
                            accepted_counts.append(native_count)
                            vs.vstSetHelpString(hint())
                        state["last_native_click_ms"] = _mouse_click_sample()[2]
                elif native_count < state["native_count"]:
                    # Native removal can include an ignored click or several points.
                    remove_last(native_count)
                    state["last_native_click_ms"] = None
                    vs.vstSetHelpString(hint())
                state["native_count"] = native_count
            elif action == 103 and points and not state["finish_requested"]:
                # Backspace is observable here as a reduced vstNumPts count;
                # VW 2026 emits no separate point-removal event for it.
                native_count = int(vs.vstNumPts())
                if native_count < state["native_count"]:
                    remove_last(native_count)
                    state["last_native_click_ms"] = None
                    vs.vstSetHelpString(hint())
                down, pressed, tick_ms, double_click_ms = _mouse_click_sample()
                current = _point(vs.vstGetCurrPt2D())
                last_click = state["last_native_click_ms"]
                if (count is None and len(points) >= 2 and down and pressed and
                        last_click is not None and
                        0 <= tick_ms - last_click <= double_click_ms + 100 and
                        current is not None and
                        math.hypot(current[0]-points[-1][0],
                                   current[1]-points[-1][1]) * factor <= 1e-9):
                    state["finish_requested"] = True
                    state["complete"] = True
                for start, end in zip(points, points[1:]):
                    vs.vstDrawCoordLine(start[0], start[1], end[0], end[1])
                if current is not None:
                    vs.vstDrawCoordLine(points[-1][0], points[-1][1], current[0], current[1])
            elif action == 104:
                # Reconcile Backspace again at completion in case VW
                # coalesced the draw callback that first exposed it.
                native_count = int(vs.vstNumPts())
                if native_count < state["native_count"]:
                    remove_last(native_count)
                enough = len(points) >= 2 if count is None else len(points) == count
                state["complete"] = enough and state["error"] is None
            elif action == 4:
                cancel_point_input()
                vs.SetTempToolHelpStr("")
                if state["error"]:
                    alert("Gefälle konnte nicht erstellt werden: %s" % state["error"])
                elif state["complete"]:
                    on_complete(tuple((x*factor, y*factor) for x, y in points))
                return 0
            finished = state["finish_requested"] or state["complete"]
            # kToolCompleted is required for the real second mouse click:
            # VW's Python RunTempTool suppresses DrawingDoubleClick and does
            # not terminate merely because the draw callback returns zero.
            if count is None and finished:
                return 8
            return 0 if (count is not None and len(points) >= count) or state["error"] else 1
        except Exception as error:
            state["error"] = str(error)
            if action == 4:
                cancel_point_input()
                alert("Gefälle konnte nicht erstellt werden: %s" % error)
            return 0

    _point_input_callback = callback
    try:
        vs.SetTempToolHelpStr(hint())
        # Vectorworks 2026's installed Python wrapper uses the boolean first,
        # although the published parameter table lists the callback first.
        vs.RunTempTool(False, callback)
    except Exception:
        cancel_point_input()
        vs.SetTempToolHelpStr('')
        raise


def draw_branch_points(first_point_m, on_complete):
    draw_points(lambda points: on_complete(points[1:]), first_point=first_point_m)


def pick_connection_point(on_complete, help_text=None):
    """Preview opens only after native tool cleanup, never during a click."""
    _pick_points(1, lambda points: on_complete(points[0]), help_text=help_text)


def pick_height_point(on_complete):
    _pick_points(1, lambda points: on_complete(points[0]),
                 help_text="Einzelnen Höhenpunkt setzen: Position anklicken. Esc: abbrechen.")


def pick_height_object(help_text, excluded_names=()):
    """Graphically track one managed point PIO and return its stable value."""
    from . import live_objects
    excluded = set(str(value) for value in excluded_names)

    def accepted(candidate):
        try:
            data = live_objects.data_of(candidate)
            return bool(data and data["role"] == "point" and
                        str(vs.GetName(candidate)) not in excluded)
        except Exception:
            return False

    vs.SetTempToolHelpStr(str(help_text))
    try:
        handle, _point = vs.TrackObject(accepted)
    finally:
        vs.SetTempToolHelpStr("")
    if not handle:
        return None
    data = live_objects.data_of(handle)
    point = live_objects.read_point(handle, data)
    return handle, data, point


def object_name(handle):
    return str(vs.GetName(handle) or "")


def independent_points():
    from . import live_objects
    return tuple(sorted(((vs.GetName(h), live_objects.read_point(h, data))
                         for h, data in live_objects.objects("point")), key=lambda row: row[1]["number"]))


def network_rows():
    from . import live_objects, networks
    chains = tuple(c for _, c in chain_records())
    levels_by_number = {p["number"]: c["level"] for c in chains for p in c["points"]}
    points = []
    for handle, data in live_objects.objects("point"):
        point = live_objects.read_point(handle, data)
        layer = str(vs.GetLName(vs.GetLayer(handle)))
        fallback = layer[4:] if layer.casefold().startswith("gef-") else layer
        level = data.get("level") or levels_by_number.get(point["number"], fallback)
        points.append((level, point))
    return networks.inventory(chains, points)


def create_independent_point(xy, height, number, level, preferences):
    from . import live_objects
    return live_objects.create_point(xy, height, number, level, preferences)


def create_independent_points(rows, level, preferences):
    from . import live_objects
    return live_objects.create_points(rows, level, preferences)


def connect_existing_points(first_name, second_name, level, preferences):
    from . import live_model, live_objects
    first, second = (live_objects.read_point(vs.GetObject(name)) for name in (first_name, second_name))
    identities = {first["point_id"], second["point_id"]}
    for _, chain in chain_records():
        if not chain.get("curve") and any({a.get("point_id"), b.get("point_id")} == identities
                for a, b in zip(chain["points"], chain["points"][1:])):
            raise core.SlopeError("Diese Höhenpunkte sind bereits mit einer geraden Verbindung verbunden.")
    return live_objects.create(live_model.connection(first, second, level), preferences)


def connection_evaluator(handle, chain):
    if not chain.get("curve"):
        return None
    curves, seen = [], set()
    child = vs.FInGroup(handle)
    while child:
        if str(child) in seen:
            raise core.SlopeError("Ungültige Objektfolge in der Gefällegruppe.")
        seen.add(str(child))
        if vs.GetTypeN(child) == TYPE_POLYLINE:
            curves.append(child)
        child = vs.NextObj(child)
    if len(curves) != 1:
        raise core.SlopeError("Die ursprüngliche Gefällekurve wurde nicht eindeutig gefunden.")
    evaluate = _curve_evaluator(curves[0], units_to_meters(), chain["curve"]["length_m"])
    frame, origin = _connection_frame(handle)

    def world_evaluate(station):
        point, tangent = evaluate(station)
        return frame.offset(origin, *point), frame.model(tangent)
    return world_evaluate


def _connection_frame(handle):
    """Native child geometry uses local XY; chain records use model metres."""
    if object_type(handle) == 86:
        factor = units_to_meters()
        return PlanFrame(vs.GetSymRot(handle)), tuple(v*factor for v in vs.GetSymLoc(handle))
    return PlanFrame(0.), (0., 0.)


def _connection_polygons(handle):
    """Inspect generated groups, never symbol artwork or unrelated point PIOs."""
    polygons, seen = [], set()

    def visit(owner):
        child = vs.FInGroup(owner)
        while child:
            if str(child) in seen:
                raise core.SlopeError("Ungültige Objektfolge in der 3D-Verbindung.")
            seen.add(str(child))
            kind = vs.GetTypeN(child)
            if kind == 25:
                polygons.append(child)
            elif kind == 11:
                visit(child)
            child = vs.NextObj(child)
    visit(handle)
    return polygons


def _ensure_record():
    record = vs.GetObject(RECORD_NAME)
    if not record:
        vs.NewField(RECORD_NAME, RECORD_FIELD, "", 4, 0)
        record = vs.GetObject(RECORD_NAME)
    if not record:
        raise RuntimeError("Gefälle-Datenbank konnte nicht erstellt werden.")
    return record


def write_chain(handle, chain):
    _ensure_record()
    payload = json.dumps(chain, ensure_ascii=False, separators=(",", ":"),
                         sort_keys=True)
    vs.SetRecord(handle, RECORD_NAME)
    vs.SetRField(handle, RECORD_NAME, RECORD_FIELD, payload)
    stored = str(vs.GetRField(handle, RECORD_NAME, RECORD_FIELD) or "")
    if stored != payload:
        raise RuntimeError("Gefälledaten konnten nicht sicher gespeichert werden.")


def read_chain(handle):
    if object_type(handle) == 86:
        from . import live_objects
        return live_objects.read_chain(handle)
    raw = str(vs.GetRField(handle, RECORD_NAME, RECORD_FIELD) or "")
    if not raw:
        return None
    try:
        value = json.loads(raw)
        chain = core.validate_chain(value)
    except (ValueError, TypeError, core.SlopeError):
        return None
    return _with_current_coordinates(handle, chain)


def _with_current_coordinates(handle, chain):
    """Read the managed segments, not the label-dependent bounding box."""
    lines = []
    curves = []
    child = vs.FInGroup(handle)
    seen = set()
    while child:
        if str(child) in seen:
            raise core.SlopeError("Die Gefällegruppe enthält eine ungültige Objektfolge.")
        seen.add(str(child))
        if int(vs.GetTypeN(child)) == TYPE_LINE:
            first, second = _point(vs.GetSegPt1(child)), _point(vs.GetSegPt2(child))
            if first is None or second is None:
                raise core.SlopeError("Gefällelinie nicht lesbar; Original bleibt unverändert.")
            lines.append((first, second))
        elif int(vs.GetTypeN(child)) == TYPE_POLYLINE:
            curves.append(child)
        child = vs.NextObj(child)
    if chain.get("curve") is not None:
        if len(curves) != 1 or lines:
            raise core.SlopeError("Die Gefällekurve wurde manuell zerlegt; Original bleibt unverändert.")
        source = _extract_curve(curves[0])
        if "control_stations_m" in chain["curve"]:
            evaluate = _curve_evaluator(curves[0], units_to_meters(), source["curve"]["length_m"])
            changed = insert_point.rebase_curve(chain, source["curve"], evaluate)
        else:
            if len(source["points"]) != len(chain["points"]):
                raise core.SlopeError("Die Zahl der Kurvenstützpunkte wurde geändert; bitte als neues Gefälle übernehmen.")
            changed = copy.deepcopy(chain)
            changed["curve"] = source["curve"]
            changed["schema"] = core.SCHEMA_VERSION
            for record, point_xy in zip(changed["points"], source["points"]):
                record["x_m"], record["y_m"] = point_xy
        layer = vs.GetLayer(handle)
        if layer:
            changed["layer_name"] = str(vs.GetLName(layer))
        return _with_current_heights(handle, changed)
    if len(lines) != len(chain["points"]) - 1:
        raise core.SlopeError(
            "Die Anzahl der Gefällelinien wurde manuell geändert. "
            "Bitte diese Änderung rückgängig machen; die Gruppe wurde nicht ersetzt.")
    factor = units_to_meters()
    points = [lines[0][0]]
    for first, second in lines:
        if math.hypot(first[0] - points[-1][0], first[1] - points[-1][1]) * factor > 0.000001:
            raise core.SlopeError("Die Gefällelinie ist unterbrochen; Original bleibt unverändert.")
        points.append(second)
    changed = copy.deepcopy(chain)
    for record, point_xy in zip(changed["points"], points):
        record["x_m"], record["y_m"] = point_xy[0] * factor, point_xy[1] * factor
    layer = vs.GetLayer(handle)
    if layer:
        changed["layer_name"] = str(vs.GetLName(layer))
    return _with_current_heights(handle, changed)


def _with_current_heights(handle, chain):
    if chain.get("point_output", {}).get("mode") == "3d":
        factor = units_to_meters()
        layer_z = layer_elevation_units(vs.GetLayer(handle), factor)
        child, loci = vs.FInGroup(handle), []
        while child:
            if vs.GetTypeN(child) == 9:
                loci.append(vs.GetLocus3D(child))
            child = vs.NextObj(child)
        if len(loci) != len(chain["points"]):
            raise core.SlopeError("Höhenpunkte wurden entfernt oder ergänzt; Gefällegruppe bleibt unverändert.")
        for point, (x, y, z) in zip(chain["points"], loci):
            if math.hypot(x*factor-point["x_m"], y*factor-point["y_m"]) > 1e-5:
                raise core.SlopeError("3D-Höhenpunkt und Gefällelinie sind versetzt. XY-Lage zuerst korrigieren.")
            point["height_m"] = (z+layer_z)*factor
    return core.validate_chain(chain)


def chain_records():
    result = []
    errors = []

    def collect(handle):
        # VW can swallow exceptions raised in a traversal callback. A failed
        # curve read must not disappear from the next point-number allocation.
        try:
            result.append((handle, read_chain(handle)))
        except Exception as error:
            errors.append(str(error))

    try:
        vs.ForEachObject(
            collect,
            "((R IN ['%s']))" % RECORD_NAME)
    except Exception as error:
        raise core.SlopeError("Vorhandene Gefälledaten konnten nicht vollständig gelesen werden.") from error
    if errors:
        raise core.SlopeError("Vorhandene Gefällekurve konnte nicht gelesen werden: " + errors[0])
    if any(chain is None for _handle, chain in result):
        raise core.SlopeError("Eine Gefällegruppe enthält beschädigte Daten; keine neuen Punktnummern vergeben.")
    core.validate_document_numbering(chain for _handle, chain in result)
    return tuple((handle, chain) for handle, chain in result if chain)


def selected_chain_record():
    from . import live_objects
    values = live_objects.selected_records(selected_handles())
    if len(values) != 1:
        raise core.SlopeError(
            "Bitte eine Gefälleverbindung oder einen zugehörigen Höhenpunkt markieren. "
            "Bei einem gemeinsamen Anschlusspunkt bitte die gewünschte Verbindung auswählen.")
    return values[0]


def selected_point_display():
    from . import live_objects
    handles = selected_handles()
    if len(handles) != 1:
        return None
    handle = handles[0]
    data = live_objects.data_of(handle)
    if data and data["role"] == "label":
        handle = vs.GetObject(data["owner"])
        data = live_objects.data_of(handle)
    if data and data["role"] == "point":
        live_objects.read_point(handle, data)
        return handle, data
    return None


def replace_point_display(handle, output):
    from . import live_objects
    live_objects.replace_point_display(handle, output)


def independent_point_numbers():
    from . import live_objects
    return live_objects.point_numbers()


def _rgb(value, fallback=(0, 0, 0)):
    try:
        result = tuple(max(0, min(65535, int(part))) for part in value)
    except (TypeError, ValueError):
        result = tuple(fallback)
    return result if len(result) == 3 else tuple(fallback)


def ensure_class(name, color):
    active = str(vs.ActiveClass() or "")
    try:
        vs.NameClass(str(name))
        vs.SetClUseGraphic(name, True)
        vs.SetClFPat(name, 0)
        red, green, blue = _rgb(color)
        vs.SetClPenFore(name, (red, green, blue))
        vs.SetClPenBack(name, (red, green, blue))
        vs.SetClLW(name, 13)
    finally:
        if active:
            vs.NameClass(active)


def ensure_classes(preferences):
    for value in preferences["classes"].values():
        ensure_class(str(value["name"]), value["color"])


def _activate_layer(name):
    # Layer is a PROCEDURE; success returns None, not a layer handle.
    existing = vs.GetObject(str(name))
    if existing and int(vs.GetTypeN(existing)) != 31:
        raise core.SlopeError("Der Ebenenname ist bereits anderweitig vergeben: " + name)
    if not existing:
        existing = vs.CreateLayer(str(name), 1)
    if not existing or int(vs.GetObjectVariableInt(existing, 154)) != 1:
        raise core.SlopeError("Keine geeignete Konstruktionsebene: " + name)
    vs.Layer(str(name))
    active = vs.ActLayer()
    return active if active and str(vs.GetLName(active)) == str(name) else None


def _set_object_graphics(handle, class_value):
    vs.SetClass(handle, str(class_value["name"]))
    vs.SetPenFore(handle, _rgb(class_value['color']))
    vs.SetLSN(handle, 2)


def _create_line(first, second, class_value):
    vs.MoveTo(first)
    vs.LineTo(second)
    handle = vs.LNewObj()
    if not handle:
        raise RuntimeError("Vectorworks hat keine Gefällelinie erzeugt.")
    _set_object_graphics(handle, class_value)
    return handle


def _create_curve(chain, class_value):
    """Rebuild typed vertices, then compare native length and on-curve anchors."""
    curve = chain["curve"]
    factor = units_to_meters()
    vs.BeginPoly()
    try:
        for index, vertex in enumerate(curve["vertices"]):
            point = (vertex["x_m"] / factor, vertex["y_m"] / factor)
            # Seed a genuine polyline (not a polygon), then restore ALL native
            # vertex types/radii below without rounding or polygonalizing.
            if index == 1:
                vs.CurveTo(point)
            else:
                vs.LineTo(point)
    finally:
        vs.EndPoly()
    handle = vs.LNewObj()
    if not handle:
        raise core.SlopeError("Vectorworks hat keine Gefällekurve erzeugt.")
    vs.SetPolyClosed(handle, False)
    for index, vertex in enumerate(curve["vertices"], 1):
        vs.SetPolylineVertex(handle, index, (vertex["x_m"] / factor, vertex["y_m"] / factor),
                             vertex["type"], vertex["radius_m"] / factor,
                             index == len(curve["vertices"]))
    if int(vs.GetTypeN(handle)) != TYPE_POLYLINE:
        raise core.SlopeError("Die Kurvenart wurde von Vectorworks nicht übernommen.")
    new_length = float(vs.HPerimN(handle)) * factor
    tolerance = max(1e-5, curve["length_m"] * 1e-7)
    if not math.isfinite(new_length) or abs(new_length - curve["length_m"]) > tolerance:
        raise core.SlopeError("Die neue Kurvenlänge stimmt nicht mit dem Original überein.")
    evaluate = _curve_evaluator(handle, factor, new_length)
    for record, station in zip(chain["points"], curve["stations_m"]):
        point = evaluate(min(station, new_length))[0]
        if math.hypot(point[0] - record["x_m"], point[1] - record["y_m"]) > tolerance:
            raise core.SlopeError("Die neue Gefällekurve stimmt nicht mit dem Originalverlauf überein.")
    for label, first, second in zip(curve["labels"], curve["stations_m"], curve["stations_m"][1:]):
        point, tangent = evaluate(.5 * (first + second))
        if (math.hypot(point[0] - label["x_m"], point[1] - label["y_m"]) > tolerance
                or tangent[0] * label["tx"] + tangent[1] * label["ty"] < .99999):
            raise core.SlopeError("Bogenverlauf oder Kurventangente wurde nicht korrekt übernommen.")
    _set_object_graphics(handle, class_value)
    vs.SetFPat(handle, 0)
    return handle


def _readable_angle(first, second, reference_angle=0.0):
    angle = (math.degrees(math.atan2(second[1] - first[1], second[0] - first[0]))
             - reference_angle + 180.0) % 360.0 - 180.0
    if angle > 90.0:
        angle -= 180.0
    elif angle < -90.0:
        angle += 180.0
    return angle + reference_angle


def _create_text(value, origin, angle, class_value, preferences):
    text = str(value)
    vs.TextOrigin(origin)
    vs.CreateText(text)
    handle = vs.LNewObj()
    if not handle:
        raise RuntimeError("Vectorworks hat keine Gefällebeschriftung erzeugt.")
    vs.SetTextStyleRef(handle, 0)
    font_id = int(vs.GetFontID(preferences.get('font', 'Arial')) or 0)
    if font_id > 0:
        vs.SetTextFont(handle, 0, len(text), font_id)
    vs.SetTextSize(handle, 0, len(text), float(preferences['point_size']))
    vs.SetTextStyle(handle, 0, len(text), 0)
    vs.SetTextJust(handle, 2)
    vs.SetTextVertAlignN(handle, 3)
    vs.SetTextOrientation(handle, origin, float(angle), False)
    vs.SetClass(handle, str(class_value["name"]))
    vs.SetPenFore(handle, _rgb(class_value['color']))
    vs.SetFPat(handle, 0)
    return handle


def _format_number(value, decimals):
    return (("%%.%df" % max(0, min(6, int(decimals)))) % float(value)).replace(".", ",")


def _drawing_coordinates(chain):
    factor = units_to_meters()
    return tuple((point["x_m"] / factor, point["y_m"] / factor)
                 for point in chain["points"])


def create_chain_group(chain, preferences):
    """Compatibility entry for menus; new drawings contain independent PIOs."""
    from . import live_objects
    return live_objects.create(chain, preferences)


def _create_legacy_chain_group(chain, preferences):
    core.validate_chain(chain)
    preferences = settings.validate(preferences)
    chain = copy.deepcopy(chain)
    output = point_output.for_line_class(
        chain.get("point_output", preferences.get("point_output")), preferences["classes"]["line"]["name"])
    chain["point_output"] = output
    chain["schema"] = core.SCHEMA_VERSION
    # Read before switching layers: that can change the current plan rotation.
    text_frame = (PlanFrame.current(vs) if preferences.get("align_text_to_plan", False)
                  else PlanFrame())
    ensure_classes(preferences)
    ensure_class(output["point_class"], preferences["classes"]["height"]["color"])
    variants = ("2d", "3d") if output["mode"] == "3d" else ("2d",)
    if output["mode"] == "3d":
        ensure_class(point_output.class_3d(output["point_class"]), preferences["classes"]["height"]["color"])
        ensure_class(output["line_class"], preferences["classes"]["line"]["color"])
    symbol_names = {
        mode: point_geometry.ensure_symbol(point_output.marker_options(output, mode),
                                          units_to_meters(), preferences["classes"]["height"]["color"])
        for mode in variants
    }
    previous_layer = vs.ActLayer()
    previous_name = str(vs.GetLName(previous_layer) or "")
    layer_name = str(chain.get("layer_name") or core.level_layer_name(chain.get("level", "Standard")))
    group_handle = None
    try:
        if not _activate_layer(layer_name):
            raise RuntimeError("Ebene '%s' konnte nicht angelegt werden." % layer_name)
        scale = float(vs.GetLScale(vs.ActLayer()) or 1.0)
        factor = units_to_meters()
        layer_z = layer_elevation_units(vs.ActLayer(), factor)
        offset = float(preferences.get("offset_mm", 2.5)) / 1000.0 * max(1.0, scale) / factor
        coordinates = _drawing_coordinates(chain)
        classes = preferences["classes"]
        segments = core.segment_rows(chain)
        vs.BeginGroup()
        try:
            evaluate = None
            if chain.get("curve") is not None:
                curve_handle = _create_curve(chain, classes["line"])
                evaluate = _curve_evaluator(curve_handle, factor, chain["curve"]["length_m"])
            else:
                for first, second in zip(coordinates, coordinates[1:]):
                    _create_line(first, second, classes["line"])
            point_geometry.create(chain, output, symbol_names, factor, layer_z,
                                  classes["height"]["color"], evaluate, classes["line"]["color"])
            shared = bool(chain.get("parent"))
            for index, (point, coordinate) in enumerate(zip(chain["points"], coordinates)):
                if shared and index == 0:
                    continue
                _create_text(
                    "P:%d" % int(point["number"]),
                    text_frame.offset(coordinate, 0.0, offset), text_frame.angle,
                    classes["number"], preferences)
                _create_text(
                    label_format.annotation("height", point["height_m"], preferences),
                    text_frame.offset(coordinate, 0.0, -offset), text_frame.angle,
                    classes["height"], preferences)
            for index, (segment, first, second) in enumerate(zip(segments, coordinates, coordinates[1:])):
                dx, dy = second[0] - first[0], second[1] - first[1]
                length = math.hypot(dx, dy)
                nx, ny = (-dy / length, dx / length)
                middle = ((first[0] + second[0]) * 0.5,
                          (first[1] + second[1]) * 0.5)
                angle = _readable_angle(first, second, text_frame.angle)
                if chain.get("curve") is not None:
                    label = chain["curve"]["labels"][index]
                    middle = (label["x_m"] / factor, label["y_m"] / factor)
                    norm = math.hypot(label["tx"], label["ty"])
                    nx, ny = -label["ty"] / norm, label["tx"] / norm
                    angle = _readable_angle((0, 0), (label["tx"], label["ty"]), text_frame.angle)
                _create_text(
                    label_format.annotation("slope", segment["slope_percent"], preferences),
                    (middle[0] + nx * offset, middle[1] + ny * offset),
                    angle, classes["slope"], preferences)
                _create_text(
                    label_format.annotation("length", segment["length_m"], preferences),
                    (middle[0] - nx * offset, middle[1] - ny * offset),
                    angle, classes["length"], preferences)
        except Exception:
            try:
                vs.EndGroup()
                failed = vs.LNewObj()
            except Exception:
                failed = None
            if failed:
                vs.DelObject(failed)
            raise
        vs.EndGroup()
        group_handle = vs.LNewObj()
        if not group_handle:
            raise RuntimeError("Vectorworks hat keine Gefällegruppe erzeugt.")
        # Assign the public identity only after geometry and metadata validate.
        # A hidden 2D line class must not hide its additional 3D sibling geometry.
        vs.SetClass(group_handle, vs.ClassList(1) if output["mode"] == "3d" else str(classes["line"]["name"]))
        write_chain(group_handle, chain)
        name = GROUP_PREFIX + chain["chain_id"][:8]
        if not vs.GetObject(name):
            vs.SetName(group_handle, name)
    except Exception:
        if group_handle:
            vs.DelObject(group_handle)
        raise
    finally:
        if previous_name:
            vs.Layer(previous_name)
    vs.ReDrawAll()
    return group_handle


def replace_chain_group(old_handle, chain, preferences):
    from . import live_objects
    return live_objects.replace(((old_handle, chain),), preferences)[0]


def _replace_legacy_chain_group(old_handle, chain, preferences):
    new_handle = _create_legacy_chain_group(chain, preferences)
    try:
        if read_chain(new_handle) is None:
            raise RuntimeError("Die neue Gefällegruppe konnte nicht geprüft werden.")
    except Exception:
        vs.DelObject(new_handle)
        raise
    vs.DelObject(old_handle)
    vs.SetName(new_handle, GROUP_PREFIX + chain["chain_id"][:8])
    vs.DSelectAll()
    vs.SetSelect(new_handle)
    vs.ReDrawAll()
    return new_handle


def redraw_all(preferences):
    records = tuple(chain_records())
    updated = 0
    for handle, chain in records:
        replace_chain_group(handle, chain, preferences)
        updated += 1
    return updated


def replace_chain_groups(replacements, preferences):
    from . import live_objects
    return live_objects.replace(replacements, preferences)


def _replace_legacy_chain_groups(replacements, preferences):
    """Stage and validate the ENTIRE connected update before retiring originals."""
    replacements = tuple(replacements)
    if len(replacements) == 1:
        old, chain = replacements[0]
        return (_replace_legacy_chain_group(old, chain, preferences),)
    staged = []
    try:
        for old, chain in replacements:
            new = _create_legacy_chain_group(chain, preferences)
            staged.append((old, new, chain))
            actual = read_chain(new)
            if actual is None or len(actual["points"]) != len(chain["points"]):
                raise core.SlopeError("Neue Anschlussgruppe konnte nicht geprüft werden.")
            for expected, point in zip(chain["points"], actual["points"]):
                if any(abs(point[key]-expected[key]) > 1e-5 for key in ("x_m", "y_m", "height_m")):
                    raise core.SlopeError("Neue Anschlussgruppe hat abweichende Koordinaten.")
    except Exception:
        for _old, new, _chain in staged:
            vs.DelObject(new)
        raise
    for old, new, chain in staged:
        vs.DelObject(old)
        vs.SetName(new, GROUP_PREFIX + chain["chain_id"][:8])
    vs.DSelectAll()
    for _old, new, _chain in staged:
        vs.SetSelect(new)
    vs.ReDrawAll()
    return tuple(new for _old, new, _chain in staged)


def export_terrain_data(kind, preferences):
    """An explicit snapshot of selected groups, ungrouped for the site model.

    Never update or delete an existing terrain/source layer. Export loci OR
    polygons to avoid feeding the same vertices to the DTM twice.
    """
    if kind not in ("points", "lines"):
        raise core.SlopeError("Unbekannte Geländedatenart.")
    from . import live_objects
    records = live_objects.selected_records(selected_handles())
    if not records:
        raise core.SlopeError("Zuerst eine oder mehrere 3D-Gefällegruppen markieren.")
    points, paths = [], []
    factor = units_to_meters()
    for handle, chain in records:
        output = point_output.options(chain.get("point_output"))
        if output["mode"] != "3d":
            raise core.SlopeError("Eine gewählte Gruppe ist 2D. Zuerst 'Punktsymbol / 2D–3D ändern' wählen.")
        if kind == "points":
            points.extend((p["x_m"], p["y_m"], p["height_m"]) for p in chain["points"])
        else:
            if not output["connect_3d"]:
                raise core.SlopeError("In einer Gruppe fehlen 3D-Verbindungen. Diese zuerst in der Punktdarstellung einschalten.")
            polygons = _connection_polygons(handle)
            if len(polygons) != 1:
                raise core.SlopeError("3D-Verbindung fehlt oder wurde zerlegt. Gefälle zuerst neu zeichnen.")
            frame, origin = _connection_frame(handle)
            path = tuple(frame.offset(origin, x*factor, y*factor)+(z*factor,) for x, y, z in
                         (vs.GetPolyPt3D(polygons[0], i) for i in range(vs.GetVertNum(polygons[0]))))
            if len(path) < 2 or vs.IsPolyClosed(polygons[0]):
                raise core.SlopeError("Ungültige 3D-Verbindung. Gefälle zuerst neu zeichnen.")
            for point in chain["points"]:
                if not any(math.hypot(p[0]-point["x_m"], p[1]-point["y_m"]) <= 1e-5
                           and abs(p[2]-point["height_m"]) <= 1e-5 for p in path):
                    raise core.SlopeError("3D-Linie und Höhenpunkte stimmen nicht überein. Gefälle zuerst neu zeichnen.")
            paths.append(path)
    if kind == "points":
        points = point_output.unique_points(points)
    else:
        point_output.unique_points(p for path in paths for p in path)
        deduplicated = {}
        for path in paths:
            key = tuple(tuple(round(v, 6) for v in p) for p in path)
            deduplicated[min(key, tuple(reversed(key)))] = path
        paths = tuple(deduplicated.values())
    previous = str(vs.GetLName(vs.ActLayer()))
    name, suffix = "GEF-Geländedaten", 1
    while vs.GetObject(name):
        suffix += 1
        name = "GEF-Geländedaten-%d" % suffix
    group, moved = None, []
    try:
        if not _activate_layer(name):
            raise core.SlopeError("Die Geländedaten-Ebene konnte nicht angelegt werden.")
        target = vs.ActLayer()
        layer_z = layer_elevation_units(target, factor)
        output = point_output.for_line_class(preferences.get("point_output"), preferences["classes"]["line"]["name"])
        class_name = point_output.class_3d(output["point_class"]) if kind == "points" else output["line_class"]
        color = preferences["classes"]["height"]["color"]
        ensure_class(class_name, color)
        vs.BeginGroup()
        try:
            if kind == "points":
                for point in points:
                    point_geometry.native_locus(point, factor, layer_z, class_name, color)
            else:
                for path in paths:
                    point_geometry.native_polygon(path, factor, layer_z, class_name, color)
        finally:
            vs.EndGroup()
            group = vs.LNewObj()
        while vs.FInGroup(group):
            child = vs.FInGroup(group)
            if not vs.SetParent(child, target) or vs.FInGroup(group) == child:
                raise core.SlopeError("Geländedaten konnten nicht aus der Prüfgruppe gelöst werden.")
            moved.append(child)
            index = len(moved) - 1
            if kind == "points":
                x, y, z = vs.GetLocus3D(child)
                point_geometry._check_xyz((x*factor, y*factor, (z+layer_z)*factor), points[index])
            else:
                for i, expected in enumerate(paths[index]):
                    x, y, z = vs.GetPolyPt3D(child, i)
                    point_geometry._check_xyz((x*factor, y*factor, z*factor), expected)
        vs.DelObject(group)
        group = None
        vs.DSelectAll()
        for handle in moved:
            vs.SetSelect(handle)
        vs.ResetOrientation3D()
        vs.ReDrawAll()
        return name, len(moved)
    except Exception:
        for handle in moved:
            vs.DelObject(handle)
        if group:
            vs.DelObject(group)
        vs.Layer(previous)
        raise
