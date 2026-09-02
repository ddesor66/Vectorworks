"""Verified direct Vectorworks calls for open-filled-shape review.

Only polygons/polylines placed on design layers (including ordinary groups)
are changed. Symbol definitions, plug-in internals and sheet layers stay out.
"""
from dataclasses import dataclass

import vs

from .core_open_shapes import ShapeState, candidate_reason


@dataclass
class Candidate:
    handle: object
    layer: object
    class_name: str
    layer_name: str
    ancestors: tuple = ()


def is_locked(handle):
    result = vs.IsLocked(handle)
    # The 2026 binding may return a bool or the documented (bool, handle).
    if isinstance(result, tuple):
        return bool(result[0])
    return bool(result)


def read_state(handle, ancestors=()):
    kind = vs.GetTypeN(handle)
    if kind not in (5, 21):
        return ShapeState(kind, False, 0, 0)
    pattern = (vs.GetClFPat(vs.GetClass(handle)) if vs.IsFPatByClass(handle)
               else vs.GetFPat(handle))
    resource_type = 0
    if pattern < 0:
        resource = vs.GetObject(vs.Index2Name(-pattern))
        resource_type = vs.GetTypeN(resource) if resource else 0
    return ShapeState(kind, bool(vs.IsPolyClosed(handle)), vs.GetVertNum(handle),
                      pattern, resource_type,
                      is_locked(handle) or any(is_locked(h) for h in ancestors))


def scan():
    candidates, skipped = [], {"locked": 0, "too_few_vertices": 0,
                              "containers_not_entered": 0, "scanned": 0}

    def walk(first, layer, ancestors=()):
        handle = first
        while handle:
            following = vs.NextObj(handle)
            kind = vs.GetTypeN(handle)
            skipped["scanned"] += 1
            if kind == 11:
                walk(vs.FInGroup(handle), layer, ancestors + (handle,))
            elif kind in (15, 86):
                skipped["containers_not_entered"] += 1
            elif kind in (5, 21):
                reason = candidate_reason(read_state(handle, ancestors))
                if reason == "eligible":
                    candidates.append(Candidate(handle, layer, vs.GetClass(handle),
                                                vs.GetLName(layer), ancestors))
                elif reason in ("locked", "too_few_vertices"):
                    skipped[reason] += 1
            handle = following

    layer = vs.FLayer()
    while layer:
        if vs.GetObjectVariableInt(layer, 154) == 1:  # Appendix G: design layer
            walk(vs.FInLayer(layer), layer)
        layer = vs.NextLayer(layer)
    return candidates, skipped


def close_candidates(candidates):
    """Close this confirmed batch; roll back its changes on any failure."""
    candidates = tuple(candidates)
    for candidate in candidates:
        if candidate_reason(read_state(candidate.handle, candidate.ancestors)) != "eligible":
            raise RuntimeError("Ein Fund wurde geändert oder gesperrt. Bitte erneut prüfen.")
    if not candidates:
        return 0
    vs.NameUndoEvent("Gefüllte offene Flächen schließen")
    changed = []
    try:
        for candidate in candidates:
            # Journal before mutation: a call can fail after changing the flag.
            changed.append(candidate)
            vs.SetPolyClosed(candidate.handle, True)
            vs.ResetObject(candidate.handle)
            if not vs.IsPolyClosed(candidate.handle):
                raise RuntimeError("Vectorworks hat eine Fläche nicht geschlossen.")
    except Exception as error:
        failures = []
        for candidate in reversed(changed):
            try:
                vs.SetPolyClosed(candidate.handle, False)
                vs.ResetObject(candidate.handle)
                if vs.IsPolyClosed(candidate.handle):
                    failures.append(candidate.class_name)
            except Exception:
                failures.append(candidate.class_name)
        vs.ReDrawAll()
        if failures:
            raise RuntimeError("Schließen fehlgeschlagen; Rücksetzung unvollständig. "
                               "Bitte Rückgängig verwenden: " + ", ".join(failures)) from error
        raise
    vs.ReDrawAll()
    return len(changed)


class ReviewView:
    """Restore selection and any temporarily revealed class/layer state."""

    def __init__(self):
        self.layer = vs.ActLayer()
        self.class_options = vs.GetClassOptions()
        self.layer_options = vs.GetLayerOptions()
        self.classes = {}
        self.layers = {}
        self.selection = []
        vs.ForEachObject(self.selection.append, "(SEL=TRUE)")

    def focus(self, candidate):
        name = candidate.layer_name
        if name not in self.layers:
            self.layers[name] = vs.GetLVis(candidate.layer)
        vs.Layer(name)
        vs.ShowLayer()
        for handle in candidate.ancestors + (candidate.handle,):
            class_name = vs.GetClass(handle)
            if class_name not in self.classes:
                self.classes[class_name] = vs.GetCVis(class_name)
            vs.ShowClass(class_name)
        vs.SetClassOptions(5)
        vs.SetLayerOptions(5)
        vs.DSelectAll()
        # Selecting the outer group makes a nested object's context visible.
        if candidate.ancestors:
            vs.SetSelect(candidate.ancestors[0])
        vs.SetSelect(candidate.handle)
        vs.DoMenuTextByName("Fit To Objects", 0)
        vs.ReDrawAll()

    def restore(self):
        for name, state in self.classes.items():
            if state == -1:
                vs.HideClass(name)
            elif state == 2:
                vs.GrayClass(name)
            else:
                vs.ShowClass(name)
        for name, state in self.layers.items():
            vs.Layer(name)
            if state == -1:
                vs.HideLayer()
            elif state == 2:
                vs.GrayLayer()
            else:
                vs.ShowLayer()
        if self.layer:
            vs.Layer(vs.GetLName(self.layer))
        vs.SetClassOptions(self.class_options)
        vs.SetLayerOptions(self.layer_options)
        vs.DSelectAll()
        for handle in self.selection:
            if vs.GetTypeN(handle):
                vs.SetSelect(handle)
        vs.ReDrawAll()
