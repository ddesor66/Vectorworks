# -*- coding: utf-8 -*-
"""Pure rules for adapting sewer covers to a Vectorworks site model.

The site-model query belongs to the Vectorworks adapter.  This module only
decides whether a shaft can carry a cover and returns a copy in which exactly
``kd_m`` is changed.  Invert elevations and every other persisted field are
therefore protected by construction and can be regression-tested without
Vectorworks.
"""
from __future__ import absolute_import

import copy
import math


class TerrainRuleError(ValueError):
    """The requested terrain adjustment would produce invalid shaft data."""


_COVER_STRUCTURES = ("round", "special")


def _finite_number(value, label):
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise TerrainRuleError("%s ist keine gültige Zahl." % label) from error
    if not math.isfinite(result):
        raise TerrainRuleError("%s ist keine endliche Zahl." % label)
    return result


def supports_terrain_cover(shaft):
    """Return whether ``shaft`` is a visible structure with a real cover."""
    if not isinstance(shaft, dict) or not bool(shaft.get("visible", True)):
        return False
    structure = str(shaft.get("structure_type", ""))
    if not structure:
        try:
            structure = "round" if float(shaft.get("diameter_m", 0.0)) > 0.0 else "junction"
        except (TypeError, ValueError):
            return False
    return structure in _COVER_STRUCTURES


def cover_at_surface(shaft, surface_elevation_m):
    """Return a shaft copy with its cover at ``surface_elevation_m``.

    Only ``kd_m`` may change.  A surface below the persisted shaft invert is
    rejected instead of silently moving the invert or the connected pipes.
    The input mapping is never mutated.
    """
    if not isinstance(shaft, dict):
        raise TerrainRuleError("Ungültige Schachtdaten.")
    if not supports_terrain_cover(shaft):
        raise TerrainRuleError("Nur sichtbare runde Schächte und Sonderschächte besitzen einen Schachtdeckel.")
    if "ks_m" not in shaft:
        raise TerrainRuleError("Die unveränderliche Schachtsohle fehlt.")
    invert_m = _finite_number(shaft["ks_m"], "Schachtsohle")
    surface_m = _finite_number(surface_elevation_m, "Geländehöhe")
    if surface_m + 1e-9 < invert_m:
        raise TerrainRuleError(
            "Die Geländehöhe %.3f m liegt unter der Schachtsohle %.3f m; "
            "Schachtsohle und Rohre wurden nicht verändert." % (surface_m, invert_m))
    result = copy.deepcopy(shaft)
    result["kd_m"] = surface_m
    return result


def plan_cover_updates(shafts, surface_elevations_m):
    """Validate a complete batch before any Vectorworks object is written."""
    shaft_rows = tuple(shafts)
    surfaces = tuple(surface_elevations_m)
    if len(shaft_rows) != len(surfaces):
        raise TerrainRuleError("Schächte und Geländehöhen sind nicht vollständig zugeordnet.")
    return tuple(cover_at_surface(shaft, surface)
                 for shaft, surface in zip(shaft_rows, surfaces))
