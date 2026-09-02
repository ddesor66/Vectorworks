# -*- coding: utf-8 -*-
"""Persistent PD Kanaltool PIO data with read-only legacy compatibility."""

from __future__ import absolute_import

import json

import vs

from . import core


PLUGIN = "PD KAN Objekt"
ROLES = ("sewer_pipe", "sewer_shaft", "sewer_label", "sewer_fitting")


def plugin_of(handle):
    if not handle or int(vs.GetTypeN(handle) or 0) != 86:
        return None
    try:
        record = vs.GetParametricRecord(handle)
        name = str(vs.GetName(record) or "") if record else ""
        if name == PLUGIN:
            return name
    except Exception:
        pass
    try:
        if vs.GetRField(handle, PLUGIN, "Daten"):
            return PLUGIN
    except Exception:
        pass
    return None


def data_of(handle):
    plugin = plugin_of(handle)
    if not plugin:
        return None
    raw = vs.GetRField(handle, plugin, "Daten")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise core.SewerError("Beschädigte Daten in einem Kanalobjekt.") from error
    if data.get("schema") != core.SCHEMA or data.get("role") not in ROLES:
        return None
    return data


def write_data(handle, data, plugin_name=None):
    plugin = plugin_name or plugin_of(handle)
    if not plugin:
        raise core.SewerError("Der parametrische Kanalobjekttyp konnte nicht bestimmt werden.")
    value = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    vs.SetRField(handle, plugin, "Daten", value)
    if vs.GetRField(handle, plugin, "Daten") != value:
        raise core.SewerError("Kanaldaten konnten nicht vollständig gespeichert werden.")


def _handle_key(handle):
    """Return a stable key for integer and VW 2026 HandleContainer handles."""
    try:
        name = str(vs.GetName(handle) or "")
    except Exception:
        name = ""
    if name:
        return "name", name
    try:
        return "native", int(handle)
    except (TypeError, ValueError):
        # Unnamed wrappers are still unique for this ForEachObject traversal.
        return "wrapper", id(handle)


def objects(role=None):
    result = []
    errors = []
    seen = set()

    def collect(handle):
        if not handle:
            return
        key = _handle_key(handle)
        if key in seen:
            return
        seen.add(key)
        try:
            data = data_of(handle)
            if data and (role is None or data.get("role") == role):
                result.append((handle, data))
        except Exception as error:
            errors.append(error)
    vs.ForEachObject(collect, "((PON='PD KAN Objekt'))")
    if errors:
        raise errors[0]
    return tuple(result)


def _new_object(xy, data, name, created):
    handle = vs.CreateCustomObjectN(PLUGIN, xy, 0.0, False)
    if not handle or int(vs.GetTypeN(handle) or 0) != 86:
        raise core.SewerError(
            "Das parametrische Plug-in 'PD KAN Objekt.vso' fehlt. Gesamtinstallation durchführen und Vectorworks neu starten.")
    created.append(handle)
    vs.SetName(handle, name)
    if str(vs.GetName(handle) or "") != name:
        raise core.SewerError("Kanalobjektidentität konnte nicht reserviert werden.")
    vs.SetClass(handle, vs.ClassList(1))
    write_data(handle, data, PLUGIN)
    return handle
