# -*- coding: utf-8 -*-
"""Narrow Vectorworks 2026 adapter for the independent channel tool."""

from __future__ import absolute_import

import math

import vs

from . import core


TYPE_LINE = 2
TYPE_POLYGON = 5
TYPE_POLYLINE = 21
_point_input_token = None
_point_input_callback = None


def _mouse_click_sample():
    """Return the real Windows left-button edge for VW's temp tool.

    VW 2026's Python RunTempTool binding consumes the second physical click
    without emitting DrawingDoubleClick.  GetAsyncKeyState's low bit records
    that otherwise lost click until this callback reads it.  The helper is
    deliberately isolated and fails closed on non-Windows/test runtimes.
    """
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
    """Remember a Backspace edge while VW is between Python callbacks."""
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

    threading.Thread(target=watch, name="PD-Kanal-Backspace", daemon=True).start()


def object_type(handle):
    return int(vs.GetTypeN(handle) or 0) if handle else 0


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
        raise core.SewerError("Dokumenteinheiten konnten nicht gelesen werden.") from error
    if not math.isfinite(units_per_inch) or units_per_inch <= 0.0:
        raise core.SewerError("Die Dokumenteinheiten sind ungültig.")
    return 0.0254 / units_per_inch


def _point(value):
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    return None


def symbol_location_2d(handle, fallback=None):
    """Return a finite symbol/PIO insertion point at the native API boundary."""
    try:
        result = vs.GetSymLoc(handle) if handle else None
    except Exception:
        result = None
    value = _point(result)
    if value is None:
        value = _point(fallback)
    if value is None or not all(math.isfinite(component) for component in value):
        raise core.SewerError(
            "Vectorworks hat die Einfügeposition des Kanalobjekts nicht bereitgestellt.")
    return value


def selected_handles():
    result = []

    def collect(handle):
        if vs.Selected(handle):
            result.append(handle)
    try:
        vs.ForEachObject(collect, "(SEL=TRUE)")
    except Exception as error:
        raise core.SewerError("Die Zeichnungsauswahl konnte nicht gelesen werden.") from error
    return tuple(result)


def extract_path(handle):
    kind = object_type(handle)
    points = []
    if kind == TYPE_LINE:
        points = [_point(vs.GetSegPt1(handle)), _point(vs.GetSegPt2(handle))]
    elif kind in (TYPE_POLYGON, TYPE_POLYLINE):
        for index in range(1, int(vs.GetVertNum(handle) or 0) + 1):
            if kind == TYPE_POLYLINE:
                value = vs.GetPolylineVertex(handle, index)
                if not isinstance(value, (tuple, list)) or len(value) < 2:
                    raise core.SewerError("Polylinienpunkt konnte nicht gelesen werden.")
                if int(value[1] or 0) != 0:
                    raise core.SewerError(
                        "Gebogene Polylinien vor der Kanalumwandlung in gerade Teilstrecken zerlegen.")
                points.append(_point(value[0]))
            else:
                points.append(_point(vs.GetPolyPt(handle, index)))
    else:
        raise core.SewerError("Bitte eine Linie, Polylinie oder ein Polygon wählen.")
    if len(points) < 2 or any(value is None for value in points):
        raise core.SewerError("Die Stützpunkte konnten nicht vollständig gelesen werden.")
    factor = units_to_meters()
    return {"points": tuple((x * factor, y * factor) for x, y in points), "curve": None}


def cancel_point_input():
    global _point_input_token
    _point_input_token = None
    try:
        from . import point_tool
        point_tool.cancel()
    except (ImportError, AttributeError):
        pass


def draw_points(on_complete, first_point=None, help_text=None,
                undo_name="PD Kanalhaltung zeichnen"):
    from . import point_tool
    point_tool.start(on_complete, first_point, help_text, undo_name)


def _pick_points(count, on_complete, first_point=None, help_text=None):
    """Compatibility picker; production uses the event-enabled native VST."""
    global _point_input_token, _point_input_callback
    factor = units_to_meters()
    points = [] if first_point is None else [tuple(value / factor for value in first_point)]
    accepted = []
    token = object()
    _point_input_token = token
    state = {"native_count": 0, "done": False, "error": None,
             "last_native_click_ms": None, "backspace_pending": False,
             "backspace_held": False, "suppressed_point": None}
    _start_backspace_watch(token, state)

    def remove_last(native_count, allow_fallback=False):
        """Mirror one native Backspace without accepting its cursor again."""
        removed = None
        if native_count < state["native_count"]:
            while accepted and accepted[-1] > native_count:
                accepted.pop()
                removed = points.pop()
            state["native_count"] = native_count
        elif allow_fallback and accepted:
            accepted.pop()
            removed = points.pop()
        if removed is not None:
            # After Backspace, RunTempTool raises vstNumPts again for the
            # unchanged rubber-band cursor (and for Enter).  It is not a new
            # mouse click and must not restore the deleted vertex.
            state["suppressed_point"] = removed
        return removed

    def callback(action, _message1, _message2):
        if _point_input_token is not token:
            return 0
        try:
            # VW may surface Backspace on draw (103) or the generic tool
            # status event (5). Consume the physical edge at the common
            # callback entry so the result is independent of that routing.
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
            if action == 3:
                vs.vstSetPtBehavior(4 if count is None else 1)
                vs.vstSetHelpString(help_text or "Kanalpunkte anklicken; Doppelklick beendet.")
            elif action in (100, 101, 105):
                native_count = int(vs.vstNumPts())
                if native_count > state["native_count"]:
                    value = _point(vs.vstGetCurrPt2D())
                    if value is None:
                        raise core.SewerError("Ungültiger Klickpunkt.")
                    suppressed = state.get("suppressed_point")
                    if (suppressed is not None and
                            math.dist(value, suppressed) * factor <= 1e-9):
                        state["last_native_click_ms"] = None
                        if count is None and len(points) >= 2 and _enter_pressed():
                            state["done"] = True
                    else:
                        state["suppressed_point"] = None
                        if not points or math.dist(value, points[-1]) * factor > 1e-9:
                            points.append(value)
                            accepted.append(native_count)
                        elif count is None and len(points) >= 2:
                            state["done"] = True
                        state["last_native_click_ms"] = _mouse_click_sample()[2]
                elif native_count < state["native_count"]:
                    remove_last(native_count)
                    state["last_native_click_ms"] = None
                state["native_count"] = native_count
            elif action == 102 and count is None:
                value = _point(vs.vstGetCurrPt2D())
                if value is not None and (not points or math.dist(value, points[-1]) * factor > 1e-9):
                    points.append(value)
                state["done"] = len(points) >= 2
            elif action == 103 and points:
                # In VW 2026 Backspace lowers vstNumPts during the draw event;
                # it does not send a separate point-removed/status event.
                native_count = int(vs.vstNumPts())
                if native_count < state["native_count"]:
                    remove_last(native_count)
                    state["last_native_click_ms"] = None
                down, pressed, tick_ms, double_click_ms = _mouse_click_sample()
                current = _point(vs.vstGetCurrPt2D())
                last_click = state["last_native_click_ms"]
                if (count is None and len(points) >= 2 and down and pressed and
                        last_click is not None and
                        0 <= tick_ms - last_click <= double_click_ms + 100 and
                        current is not None and
                        math.dist(current, points[-1]) * factor <= 1e-9):
                    state["done"] = True
                for first, second in zip(points, points[1:]):
                    vs.vstDrawCoordLine(*first, *second)
                if current is not None:
                    vs.vstDrawCoordLine(*points[-1], *current)
            elif action == 104:
                # Reconcile once more at completion. Depending on UI timing,
                # the draw event that exposes Backspace can be coalesced.
                native_count = int(vs.vstNumPts())
                if native_count < state["native_count"]:
                    remove_last(native_count)
                state["done"] = (len(points) >= 2 if count is None else len(points) == count)
            elif action == 4:
                cancel_point_input()
                vs.SetTempToolHelpStr("")
                if state["error"]:
                    alert(state["error"])
                elif state["done"]:
                    on_complete(tuple((x * factor, y * factor) for x, y in points))
                return 0
            # RunTempTool ignores a generic zero result for a swallowed
            # physical double-click.  Returning the native kToolCompleted
            # status (8) causes the required cleanup event immediately.
            # Fixed-count pickers retain their proven zero-result contract.
            if count is None and state["done"]:
                return 8
            return 0 if count is not None and len(points) >= count else 1
        except Exception as error:
            state["error"] = str(error)
            return 0

    _point_input_callback = callback
    vs.SetTempToolHelpStr(
        help_text or
        "Kanalpunkte anklicken. Doppelklick oder Enter: abschließen. "
        "Zurücktaste: letzten Punkt entfernen. Esc: abbrechen.")
    # Vectorworks 2026's shipped Python binding expects initialScroll first.
    # This order is verified in the installed application; the published
    # parameter listing is reversed for this particular Python wrapper.
    vs.RunTempTool(False, callback)


def pick_connection_point(on_complete, help_text=None):
    _pick_points(1, lambda points: on_complete(points[0]), help_text=help_text)


def pick_object(predicate, help_text):
    """Return the tracked handle, or ``None`` when Vectorworks cancels.

    Vectorworks 2026 normally returns ``(handle, point)`` from TrackObject,
    but the Windows Python binding returns ``None`` for some cancellation and
    failed-hit paths.  Those paths are normal user input, not an exception.
    """
    vs.SetTempToolHelpStr(str(help_text))
    try:
        result = vs.TrackObject(predicate)
    finally:
        vs.SetTempToolHelpStr("")
    if result is None:
        return None
    if isinstance(result, (tuple, list)):
        handle = result[0] if result else None
    else:
        # A few Vectorworks service-pack bindings have returned the handle
        # alone. Supporting that shape keeps the adapter boundary safe.
        handle = result
    if not handle:
        return None
    # TrackObject can hand the callback a stale/NIL handle after a cancelled
    # or failed pick. Re-check the final result before any native geometry
    # accessor receives it; those accessors are not safe for invalid handles.
    try:
        return handle if predicate(handle) else None
    except Exception:
        return None


def pick_pipe(help_text="Kanalhaltung grafisch anklicken. Esc: abbrechen."):
    from . import live_objects

    def accepted(handle):
        data = live_objects.data_of(handle)
        if data and data.get("role") == "sewer_label":
            data = live_objects.data_of(vs.GetObject(data.get("owner", "")))
        return bool(data and data.get("role") == "sewer_pipe")
    handle = pick_object(accepted, help_text)
    data = live_objects.data_of(handle)
    if data and data.get("role") == "sewer_label":
        handle = vs.GetObject(data.get("owner", ""))
    return handle


def pick_shaft(help_text="Kanalschacht grafisch anklicken. Esc: abbrechen."):
    from . import live_objects

    def accepted(handle):
        data = live_objects.data_of(handle)
        if data and data.get("role") == "sewer_label":
            data = live_objects.data_of(vs.GetObject(data.get("owner", "")))
        return bool(data and data.get("role") == "sewer_shaft")
    handle = pick_object(accepted, help_text)
    data = live_objects.data_of(handle)
    if data and data.get("role") == "sewer_label":
        handle = vs.GetObject(data.get("owner", ""))
    return handle


def _top_level_object(handle):
    """Return True only for a live object directly on its design layer.

    Geometry inside a parametric object can also report polygon type 5 while
    TrackObject is hovering. Treating that transient subobject as the user's
    construction contour leaves a stale handle as soon as the owning PIO is
    reset and can crash Vectorworks on the next attempt.
    """
    if not handle:
        return False
    try:
        parent = vs.GetParent(handle)
        layer = vs.GetLayer(handle)
        return bool(parent and layer and parent == layer)
    except Exception:
        return False


def pick_polygon(help_text="Polygon oder Polylinie für den Sonderschacht anklicken. Esc: abbrechen."):
    def accepted(handle):
        return (object_type(handle) in (TYPE_POLYGON, TYPE_POLYLINE) and
                _top_level_object(handle))
    return pick_object(accepted, help_text)
