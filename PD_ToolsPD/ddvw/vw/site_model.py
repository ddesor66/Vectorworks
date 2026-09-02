# -*- coding: utf-8 -*-
"""Verified Vectorworks 2026 site-model selection and elevation sampling."""
from __future__ import absolute_import

import math

import vs


class SiteModelError(RuntimeError):
    pass


def _model(name="", allow_pick=True):
    handle = vs.GetObject(str(name)) if name else None
    if handle and not vs.DTM6_IsDTM6Object(handle):
        handle = None
    if not handle:
        # NIL layer searches the document; with several models Vectorworks
        # asks the user to select one when allow_pick is true.
        handle = vs.DTM6_GetDTMObject(0, bool(allow_pick))
    if not handle or not vs.DTM6_IsDTM6Object(handle):
        raise SiteModelError("Kein Geländemodell gefunden oder ausgewählt.")
    if not vs.DTM6_IsObjectReady(handle):
        vs.ResetObject(handle)
    if not vs.DTM6_IsObjectReady(handle):
        raise SiteModelError("Das gewählte Geländemodell ist noch nicht auswertbar.")
    return handle


def select(name="", allow_pick=True):
    handle = _model(name, allow_pick)
    model_name = str(vs.GetName(handle) or "").strip()
    return handle, model_name


def elevation(handle, point_document_units, tin_type=2):
    if not handle or not vs.DTM6_IsDTM6Object(handle):
        raise SiteModelError("Ungültiges Geländemodell.")
    if int(tin_type) not in (0, 1, 2):
        raise SiteModelError("Ungültiger Geländemodellzustand.")
    try:
        x, y = float(point_document_units[0]), float(point_document_units[1])
    except (TypeError, ValueError, IndexError) as error:
        raise SiteModelError("Ungültiger Abfragepunkt am Geländemodell.") from error
    value = vs.DTM6_GetZatXY(handle, int(tin_type), x, y)
    if (not isinstance(value, (tuple, list)) or len(value) < 2 or
            not bool(value[0])):
        raise SiteModelError(
            "Ein Leitungspunkt liegt außerhalb des gewählten Geländemodells.")
    try:
        result = float(value[1])
    except (TypeError, ValueError) as error:
        raise SiteModelError("Geländehöhe konnte nicht gelesen werden.") from error
    if not math.isfinite(result):
        raise SiteModelError("Geländehöhe ist ungültig.")
    return result


def sample_meters(points_m, units_to_meters, tin_type=2, name="", allow_pick=True):
    factor = float(units_to_meters)
    if not math.isfinite(factor) or factor <= 0.0:
        raise SiteModelError("Dokumenteinheiten sind ungültig.")
    handle, model_name = select(name, allow_pick)
    values = tuple(elevation(handle, (point[0] / factor, point[1] / factor), tin_type) * factor
                   for point in points_m)
    return values, model_name
