"""Event-enabled native drawing tool: double-click ends an unlimited chain.

Unlike RunTempTool, a native script tool receives DrawingDoubleClick (102).
Event and result constants: Vectorworks SDK2026 MiniCadCallBacks/HookIntf.h.
"""
import math

import vs

from . import core
from . import vw_adapter as adapter


TOOL = "PD Gefaelle zeichnen"
_session = None


def start(on_complete, first_point=None, help_text=None,
          undo_name="PD Gefällelinie zeichnen"):
    global _session
    factor = adapter.units_to_meters()
    points = [] if first_point is None else [tuple(v / factor for v in first_point)]
    _session = dict(points=points, accepted=[], native_count=0, factor=factor,
                    done=False, callback=on_complete,
                    help_text=help_text or
                    "Gefällepunkte anklicken. Doppelklick: Linie abschließen. Esc: abbrechen.",
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
            raise core.SlopeError("Vectorworks hat keinen gültigen Klickpunkt geliefert.")
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
        raise core.SlopeError("Vectorworks hat keinen gültigen Doppelklickpunkt geliefert.")
    if not state["points"] or math.dist(xy, state["points"][-1]) * state["factor"] > 1e-9:
        state["points"].append(xy)
        state["accepted"].append(max(state["native_count"] + 1, 1))


def run():
    global _session
    action, _m1, _m2 = vs.vstGetEventInfo()
    state = _session
    if state is None:
        vs.vstSetEventResult(-1 if action == 3 else 0)
        return
    try:
        if action == 3:
            vs.vstSetPtBehavior(4)
            vs.vstSetHelpString(state["help_text"])
            vs.vstSetEventResult(0)
        elif action == 105:
            _sync(state)
            vs.vstSetEventResult(8 if state["done"] else (6 if state["points"] else 5))
        elif action == 100:
            # VW can deliver the second click as PointAdded. Finish directly
            # when it repeats the final coordinate instead of requiring a
            # third click/status cycle.
            _sync(state)
            vs.vstSetEventResult(8 if state["done"] and len(state["points"]) >= 2 else 0)
        elif action == 101:
            _sync(state)
            vs.vstSetEventResult(0)
        elif action == 102:
            _sync(state)
            _accept_double_click_point(state)
            state["done"] = len(state["points"]) >= 2
            vs.vstSetEventResult(8 if state["done"] else 4)
        elif action == 103:
            points = state["points"]
            for a, b in zip(points, points[1:]):
                vs.vstDrawCoordLine(*a, *b)
            current = adapter._point(vs.vstGetCurrPt2D())
            if points and current is not None:
                vs.vstDrawCoordLine(*points[-1], *current)
        elif action == 104:
            _sync(state)
            _session = None  # Prevent re-entry from created point/chain PIOs.
            if state["done"] and len(state["points"]) >= 2:
                vs.vstNameUndoEvent(state["undo_name"])
                points = tuple(tuple(v * state["factor"] for v in p) for p in state["points"])
                state["callback"](points)
            vs.vstSetEventResult(0)
        elif action == 4:
            cancel()
            vs.vstSetEventResult(0)
    except Exception as error:
        cancel()
        vs.vstSetEventResult(9)  # kToolCancel
        adapter.alert("Gefälle konnte nicht erstellt werden: %s" % error)
