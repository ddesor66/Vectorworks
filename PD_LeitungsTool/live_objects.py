# -*- coding: utf-8 -*-
"""Persistent PIO storage for one complete utility route."""
from __future__ import absolute_import

import json

import vs

from . import core


PLUGIN = "PD LEI Objekt"
ROLE = "utility_route"


def plugin_of(handle):
    if not handle or int(vs.GetTypeN(handle) or 0) != 86:
        return None
    try:
        record = vs.GetParametricRecord(handle)
        if record and str(vs.GetName(record) or "") == PLUGIN:
            return PLUGIN
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
        raise core.UtilityError("Beschädigte Daten in einer Leitungstrasse.") from error
    if data.get("schema") != core.SCHEMA or data.get("role") != ROLE:
        return None
    core.validate_route(data.get("route"))
    return data


def write_data(handle, data, plugin_name=None):
    plugin = plugin_name or plugin_of(handle)
    if not plugin:
        raise core.UtilityError("Der parametrische Leitungsobjekttyp konnte nicht bestimmt werden.")
    value = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    vs.SetRField(handle, plugin, "Daten", value)
    if vs.GetRField(handle, plugin, "Daten") != value:
        raise core.UtilityError("Leitungsdaten konnten nicht vollständig gespeichert werden.")


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
        return "wrapper", id(handle)


def objects():
    rows = []
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
            if data:
                rows.append((handle, data))
        except Exception as error:
            errors.append(error)
    vs.ForEachObject(collect, "((PON='PD LEI Objekt'))")
    if errors:
        raise errors[0]
    return tuple(rows)


def new_object(xy_document, data, name, created):
    handle = vs.CreateCustomObjectN(PLUGIN, xy_document, 0.0, False)
    if not handle or int(vs.GetTypeN(handle) or 0) != 86:
        raise core.UtilityError(
            "Das parametrische Plug-in 'PD LEI Objekt.vso' fehlt. "
            "Gesamtinstallation durchführen und Vectorworks neu starten.")
    created.append(handle)
    vs.SetName(handle, name)
    if str(vs.GetName(handle) or "") != name:
        raise core.UtilityError("Leitungstrassenidentität konnte nicht reserviert werden.")
    vs.SetClass(handle, vs.ClassList(1))
    write_data(handle, data, PLUGIN)
    return handle
