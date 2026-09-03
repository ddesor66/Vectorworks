# -*- coding: utf-8 -*-
"""Persistent PIO storage for one complete utility route."""
from __future__ import absolute_import

import json

import vs

from . import core


PLUGIN = "PD LEI Objekt"
ROLE = "utility_route"
CONTAINER_CLASS = "PD-LEI-Objekte"
_LAST_OBJECT_ERRORS = ()


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
    if not isinstance(data, dict):
        raise core.UtilityError("Beschädigte Daten in einer Leitungstrasse: Objekt erwartet.")
    if data.get("schema") != core.SCHEMA:
        raise core.UtilityError(
            "Nicht unterstützte Leitungstrassen-Datenversion %r." % data.get("schema"))
    if data.get("role") != ROLE:
        raise core.UtilityError("Ungültige Objektrolle in einer Leitungstrasse.")
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
    global _LAST_OBJECT_ERRORS
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
    _LAST_OBJECT_ERRORS = tuple(str(error) for error in errors)
    return tuple(rows)


def object_errors():
    """Return controlled diagnostics for malformed routes skipped by objects()."""
    return _LAST_OBJECT_ERRORS


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
    active = str(vs.ActiveClass() or "")
    try:
        vs.NameClass(CONTAINER_CLASS)
        vs.SetClass(handle, CONTAINER_CLASS)
    finally:
        if active and str(vs.ActiveClass() or "") != active:
            vs.NameClass(active)
    write_data(handle, data, PLUGIN)
    return handle
