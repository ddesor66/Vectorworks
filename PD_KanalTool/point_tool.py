"""Event-enabled native drawing tool: double-click ends an unlimited chain.

Unlike RunTempTool, a native script tool receives DrawingDoubleClick (102).
Event and result constants: Vectorworks SDK2026 MiniCadCallBacks/HookIntf.h.
"""
import math

import vs

from . import core
from . import vw_adapter as adapter


TOOL = "PD Kanal zeichnen"
_session = None

# Vectorworks SDK 2026, MiniCadHookIntf.h.  The script tool receives the
# numeric ToolMessage actions via ``vstGetEventInfo``.  Keep the values named
# here so keyboard and point-removal handling is reviewable instead of being
# spread across magic numbers.
ACTION_SETUP = 3
ACTION_CANCEL = 4
ACTION_POINT_ADDED = 100
ACTION_POINT_REMOVED = 101
ACTION_DRAWING_DOUBLE_CLICK = 102
ACTION_DRAW = 103
ACTION_COMPLETE = 104
ACTION_GET_STATUS = 105

TOOL_WAITING_FOR_FIRST_POINT = 5
TOOL_COLLECTING_POINTS = 6
TOOL_COMPLETED = 8
TOOL_CANCEL = 9
TOOL_READY_TO_COMPLETE_WITH_ENTER = 18

KEY_BACKSPACE = 8
KEY_RETURN = 13
KEY_ENTER = 10


def start(on_complete, first_point=None, help_text=None,
          undo_name="PD Kanalhaltung zeichnen"):
    global _session
    factor = adapter.units_to_meters()
    points = [] if first_point is None else [tuple(v / factor for v in first_point)]
    _session = dict(points=points, accepted=[], native_count=0, factor=factor,
                    done=False, callback=on_complete,
                    help_text=help_text or
                    "Kanalpunkte anklicken. Doppelklick oder Enter: abschließen. "
                    "Zurücktaste: letzten Punkt entfernen. Esc: abbrechen.",
                    undo_name=str(undo_name))
    try:
        if not vs.CallToolByName(TOOL):
            # A VST copied while Vectorworks was already running is only
            # registered after the next application start. Keep the module
            # usable in that session and prefer the event-enabled tool again
            # automatically after restart.
            _session = None
            if help_text is None:
                adapter._pick_points(None, on_complete, first_point)
            else:
                adapter._pick_points(None, on_complete, first_point, help_text)
    except Exception:
        _session = None
        raise


def cancel():
    global _session
    _session = None


def _sync(state):
    count = int(vs.vstNumPts())
    if count > state["native_count"]:
        xy = adapter._point(vs.vstGetCurrPt2D())
        if xy is None or not all(math.isfinite(v) for v in xy):
            raise core.SewerError("Vectorworks hat keinen gültigen Klickpunkt geliefert.")
        if not state["points"] or math.dist(xy, state["points"][-1]) * state["factor"] > 1e-9:
            state["points"].append(xy)
            state["accepted"].append(count)
        elif len(state["points"]) >= 2:
            state["done"] = True  # Preserve the existing repeat-last-point shortcut.
    elif count < state["native_count"]:
        while state["accepted"] and state["accepted"][-1] > count:
            state["accepted"].pop()
            state["points"].pop()
    state["native_count"] = count


def _accept_double_click_point(state):
    """VW 2026 can report DrawingDoubleClick before increasing vstNumPts."""
    xy = adapter._point(vs.vstGetCurrPt2D())
    if xy is None or not all(math.isfinite(value) for value in xy):
        raise core.SewerError("Vectorworks hat keinen gültigen Doppelklickpunkt geliefert.")
    if not state["points"] or math.dist(xy, state["points"][-1]) * state["factor"] > 1e-9:
        state["points"].append(xy)
        state["accepted"].append(max(state["native_count"] + 1, 1))


def _pressed_key(message1, message2):
    """Return the current non-modifier key without blocking the tool.

    ``KeyDown`` is the documented non-blocking API.  Some Vectorworks tool
    messages additionally carry the key code in message2; that fallback keeps
    Enter reliable when the keyboard state was consumed before Python runs.
    """
    try:
        down, code = vs.KeyDown()
        if down:
            return int(code)
    except (AttributeError, TypeError, ValueError):
        pass
    try:
        code = int(message2)
        if int(message1) == 1 and code in (KEY_BACKSPACE, KEY_ENTER, KEY_RETURN):
            return code
    except (TypeError, ValueError):
        pass
    return None


def _status(state):
    if state["done"] and len(state["points"]) >= 2:
        return TOOL_COMPLETED
    if state["points"]:
        return TOOL_COLLECTING_POINTS
    return TOOL_WAITING_FOR_FIRST_POINT


def run():
    global _session
    action, message1, message2 = vs.vstGetEventInfo()
    state = _session
    if state is None:
        vs.vstSetEventResult(-1 if action == ACTION_SETUP else 0)
        return
    try:
        if action == ACTION_SETUP:
            vs.vstSetPtBehavior(4)
            vs.vstSetHelpString(state["help_text"])
            vs.vstSetEventResult(0)
        elif action == ACTION_GET_STATUS:
            _sync(state)
            key = _pressed_key(message1, message2)
            if key in (KEY_ENTER, KEY_RETURN) and len(state["points"]) >= 2:
                state["done"] = True
            vs.vstSetEventResult(_status(state))
        elif action == ACTION_POINT_ADDED:
            # In the native VW 2026 point framework the second physical click
            # of a double-click can arrive as PointAdded before (or instead
            # of) DrawingDoubleClick. A repeated final coordinate therefore
            # completes immediately; waiting for a later status event caused
            # the apparent third-click requirement.
            _sync(state)
            vs.vstSetEventResult(
                TOOL_COMPLETED if state["done"] and len(state["points"]) >= 2 else 0)
        elif action == ACTION_POINT_REMOVED:
            _sync(state)
            vs.vstSetEventResult(0)
        elif action == ACTION_DRAWING_DOUBLE_CLICK:
            _sync(state)
            _accept_double_click_point(state)
            state["done"] = len(state["points"]) >= 2
            # kToolCompleted calls ToolComplete immediately.  Returning the
            # handled-double-click value (4) would insert another point and is
            # the source of the apparent third click.
            vs.vstSetEventResult(TOOL_COMPLETED if state["done"] else 4)
        elif action == ACTION_DRAW:
            points = state["points"]
            for a, b in zip(points, points[1:]):
                vs.vstDrawCoordLine(*a, *b)
            current = adapter._point(vs.vstGetCurrPt2D())
            if points and current is not None:
                vs.vstDrawCoordLine(*points[-1], *current)
        elif action == ACTION_COMPLETE:
            _sync(state)
            _session = None  # Prevent re-entry from created point/chain PIOs.
            if state["done"] and len(state["points"]) >= 2:
                vs.vstNameUndoEvent(state["undo_name"])
                points = tuple(tuple(v * state["factor"] for v in p) for p in state["points"])
                state["callback"](points)
            vs.vstSetEventResult(0)
        elif action == ACTION_CANCEL:
            cancel()
            vs.vstSetEventResult(0)
        else:
            # Backspace/Delete is processed by the native point framework. It
            # reduces ``vstNumPts`` and sends a point-removed/state-change
            # message.  Synchronising on every remaining tool message makes
            # that removal visible to the Python preview and callback without
            # guessing a version-specific action number.
            _sync(state)
            key = _pressed_key(message1, message2)
            if key in (KEY_ENTER, KEY_RETURN) and len(state["points"]) >= 2:
                state["done"] = True
                # The Enter/Return query expects 18. Vectorworks then asks for
                # the regular status, where ``_status`` returns 8 and invokes
                # the complete handler.
                vs.vstSetEventResult(TOOL_READY_TO_COMPLETE_WITH_ENTER)
            elif key in (KEY_ENTER, KEY_RETURN):
                vs.vstSetEventResult(0)
            else:
                vs.vstSetEventResult(0)
    except Exception as error:
        cancel()
        vs.vstSetEventResult(TOOL_CANCEL)
        adapter.alert("Kanalhaltung konnte nicht erstellt werden: %s" % error)
