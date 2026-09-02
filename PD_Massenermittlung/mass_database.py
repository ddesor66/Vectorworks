# -*- coding: utf-8 -*-
"""Persistent, reusable quantity database for all Vectorworks documents."""

from __future__ import absolute_import

import json
import os
import sqlite3
import uuid


SCHEMA_VERSION = 3
DATABASE_FILENAME = "Datenbank Massen.sqlite3"
CATALOG_FIELDS = (
    "product", "description", "dimensions", "color", "manufacturer")


class MassDatabaseError(RuntimeError):
    """Raised when the persistent mass database cannot be used safely."""


def _text(value):
    return str(value or "").strip()


def _catalog_record(value):
    if isinstance(value, dict):
        return dict(
            (field, _text(value.get(field, "")))
            for field in CATALOG_FIELDS
            if field in value
        )
    # Compatibility with the earlier class -> product mapping.
    return {"product": _text(value)}


def normalize_catalog(catalog):
    if not isinstance(catalog, dict):
        return {}
    result = {}
    for class_name, value in catalog.items():
        class_name = _text(class_name)
        if class_name:
            result[class_name] = _catalog_record(value)
    return result


def complete_catalog_record(value=None):
    source = _catalog_record(value or {})
    return dict((field, source.get(field, "")) for field in CATALOG_FIELDS)


def _json(values):
    return json.dumps(
        list(values or ()), ensure_ascii=False, separators=(",", ":"))


class MassDatabase(object):
    """SQLite catalog plus immutable snapshots of every quantity run."""

    def __init__(self, path):
        self.path = os.path.abspath(path)

    def _connect(self):
        target_directory = os.path.dirname(self.path)
        connection = None
        try:
            if target_directory and not os.path.isdir(target_directory):
                os.makedirs(target_directory)
            connection = sqlite3.connect(self.path, timeout=5.0)
            connection.execute("PRAGMA foreign_keys = ON")
            self._ensure_schema(connection)
            return connection
        except MassDatabaseError:
            if connection is not None:
                connection.close()
            raise
        except (OSError, sqlite3.Error) as error:
            if connection is not None:
                connection.close()
            raise MassDatabaseError(
                "Die Datenbank Massen konnte nicht geöffnet werden: %s" %
                error)

    @staticmethod
    def _ensure_schema(connection):
        row = connection.execute("PRAGMA user_version").fetchone()
        version = int(row[0] if row else 0)
        if version > SCHEMA_VERSION:
            raise MassDatabaseError(
                "Die Datenbank Massen verwendet das neuere Schema %d; "
                "unterstützt wird Schema %d." % (version, SCHEMA_VERSION))
        if version == 0:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS metadata ("
                    "key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS class_catalog ("
                    "class_name TEXT PRIMARY KEY NOT NULL, "
                    "product TEXT NOT NULL DEFAULT '', "
                    "description TEXT NOT NULL DEFAULT '', "
                    "dimensions TEXT NOT NULL DEFAULT '', "
                    "color TEXT NOT NULL DEFAULT '', "
                    "manufacturer TEXT NOT NULL DEFAULT '', "
                    "updated_at INTEGER NOT NULL, "
                    "source_document TEXT NOT NULL DEFAULT '')"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS mass_runs ("
                    "run_id TEXT PRIMARY KEY NOT NULL, "
                    "created_at INTEGER NOT NULL, "
                    "document_key TEXT NOT NULL, "
                    "document_path TEXT NOT NULL DEFAULT '', "
                    "plugin_version TEXT NOT NULL, "
                    "exact_duplicates_enabled INTEGER NOT NULL, "
                    "worksheet_name TEXT NOT NULL DEFAULT '', "
                    "xlsx_path TEXT NOT NULL DEFAULT '', "
                    "query_element_count INTEGER NOT NULL, "
                    "quantity_row_count INTEGER NOT NULL, "
                    "object_count INTEGER NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS query_elements ("
                    "run_id TEXT NOT NULL REFERENCES mass_runs(run_id) "
                    "ON DELETE CASCADE, "
                    "query_index INTEGER NOT NULL, "
                    "class_name TEXT NOT NULL, layer_id TEXT NOT NULL, "
                    "layer_name TEXT NOT NULL, "
                    "element_kind TEXT NOT NULL DEFAULT 'geometry', "
                    "element_name TEXT NOT NULL DEFAULT 'Geometrie', "
                    "group_id TEXT, group_title TEXT NOT NULL DEFAULT '', "
                    "parallel_detected INTEGER NOT NULL, "
                    "parallel_spacing_cm REAL NOT NULL DEFAULT 0, "
                    "product TEXT NOT NULL DEFAULT '', "
                    "description TEXT NOT NULL DEFAULT '', "
                    "dimensions TEXT NOT NULL DEFAULT '', "
                    "color TEXT NOT NULL DEFAULT '', "
                    "manufacturer TEXT NOT NULL DEFAULT '', "
                    "has_quantity_row INTEGER NOT NULL, "
                    "PRIMARY KEY(run_id, query_index))"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS mass_rows ("
                    "run_id TEXT NOT NULL REFERENCES mass_runs(run_id) "
                    "ON DELETE CASCADE, "
                    "row_index INTEGER NOT NULL, "
                    "class_name TEXT NOT NULL, layer_id TEXT NOT NULL, "
                    "layer_name TEXT NOT NULL, "
                    "element_kind TEXT NOT NULL DEFAULT 'geometry', "
                    "element_name TEXT NOT NULL DEFAULT 'Geometrie', "
                    "group_id TEXT, group_title TEXT NOT NULL DEFAULT '', "
                    "product TEXT NOT NULL DEFAULT '', "
                    "description TEXT NOT NULL DEFAULT '', "
                    "dimensions TEXT NOT NULL DEFAULT '', "
                    "color TEXT NOT NULL DEFAULT '', "
                    "manufacturer TEXT NOT NULL DEFAULT '', "
                    "raw_area_m2 REAL NOT NULL, net_area_m2 REAL NOT NULL, "
                    "raw_length_m REAL NOT NULL, net_length_m REAL NOT NULL, "
                    "raw_piece_count INTEGER NOT NULL, "
                    "net_piece_count INTEGER NOT NULL, "
                    "group_count INTEGER NOT NULL, symbol_count INTEGER NOT NULL, "
                    "representative_id TEXT NOT NULL DEFAULT '', "
                    "adjustment_ids_json TEXT NOT NULL, warnings_json TEXT NOT NULL, "
                    "PRIMARY KEY(run_id, row_index))"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS mass_objects ("
                    "run_id TEXT NOT NULL REFERENCES mass_runs(run_id) "
                    "ON DELETE CASCADE, "
                    "object_id TEXT NOT NULL, "
                    "class_name TEXT NOT NULL, layer_id TEXT NOT NULL, "
                    "layer_name TEXT NOT NULL, "
                    "element_kind TEXT NOT NULL DEFAULT 'geometry', "
                    "element_name TEXT NOT NULL DEFAULT 'Geometrie', "
                    "object_kind TEXT NOT NULL, "
                    "measured_area_m2 REAL NOT NULL, "
                    "measured_length_m REAL NOT NULL, piece_count INTEGER NOT NULL, "
                    "product TEXT NOT NULL DEFAULT '', "
                    "description TEXT NOT NULL DEFAULT '', "
                    "dimensions TEXT NOT NULL DEFAULT '', "
                    "color TEXT NOT NULL DEFAULT '', "
                    "manufacturer TEXT NOT NULL DEFAULT '', "
                    "parent_ids_json TEXT NOT NULL, "
                    "representative_id TEXT NOT NULL DEFAULT '', "
                    "warnings_json TEXT NOT NULL, "
                    "PRIMARY KEY(run_id, object_id))"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS mass_adjustments ("
                    "run_id TEXT NOT NULL REFERENCES mass_runs(run_id) "
                    "ON DELETE CASCADE, "
                    "adjustment_id TEXT NOT NULL, "
                    "class_name TEXT NOT NULL, layer_id TEXT NOT NULL, "
                    "layer_name TEXT NOT NULL, "
                    "element_kind TEXT NOT NULL DEFAULT 'geometry', "
                    "element_name TEXT NOT NULL DEFAULT 'Geometrie', "
                    "adjustment_kind TEXT NOT NULL, "
                    "object_ids_json TEXT NOT NULL, "
                    "length_delta_m REAL NOT NULL, area_delta_m2 REAL NOT NULL, "
                    "piece_delta INTEGER NOT NULL, note TEXT NOT NULL DEFAULT '', "
                    "PRIMARY KEY(run_id, adjustment_id))"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mass_rows_source "
                    "ON mass_rows(class_name, layer_name)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_mass_objects_source "
                    "ON mass_objects(class_name, layer_name)"
                )
                connection.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) "
                    "VALUES('database_name', 'Datenbank Massen')"
                )
                connection.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) "
                    "VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
                connection.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
            version = SCHEMA_VERSION
        if version == 1:
            # Version 1 already contains all mass history. Add the new class
            # field in place so no catalog assignments or run snapshots are
            # rebuilt, copied, or lost. Inserts use explicit column names and
            # therefore remain independent of SQLite's physical column order.
            with connection:
                for table_name in (
                        "class_catalog", "query_elements", "mass_rows",
                        "mass_objects"):
                    connection.execute(
                        "ALTER TABLE %s ADD COLUMN "
                        "color TEXT NOT NULL DEFAULT ''" % table_name)
                connection.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) "
                    "VALUES('schema_version', '2')")
                connection.execute("PRAGMA user_version = 2")
            version = 2
        if version == 2:
            # Element types split symbols and groups inside one class/layer
            # without rebuilding or deleting any earlier quantity history.
            with connection:
                for table_name in (
                        "query_elements", "mass_rows", "mass_objects",
                        "mass_adjustments"):
                    connection.execute(
                        "ALTER TABLE %s ADD COLUMN element_kind "
                        "TEXT NOT NULL DEFAULT 'geometry'" % table_name)
                    connection.execute(
                        "ALTER TABLE %s ADD COLUMN element_name "
                        "TEXT NOT NULL DEFAULT 'Geometrie'" % table_name)
                connection.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) "
                    "VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
                connection.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
            version = SCHEMA_VERSION
        if version != SCHEMA_VERSION:
            raise MassDatabaseError(
                "Das Schema der Datenbank Massen wird nicht unterstützt.")

    @staticmethod
    def _catalog_row(row):
        return {
            "product": _text(row[1]),
            "description": _text(row[2]),
            "dimensions": _text(row[3]),
            "color": _text(row[4]),
            "manufacturer": _text(row[5]),
        }

    def all_catalog(self):
        try:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT class_name, product, description, dimensions, "
                    "color, manufacturer FROM class_catalog "
                    "ORDER BY class_name COLLATE NOCASE"
                ).fetchall()
                return dict(
                    (str(row[0]), self._catalog_row(row)) for row in rows)
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise MassDatabaseError(
                "Die Datenbank Massen konnte nicht gelesen werden: %s" % error)

    def catalog_for_classes(self, class_names):
        requested = set(
            _text(value) for value in (class_names or ()) if _text(value))
        return dict(
            (class_name, value)
            for class_name, value in self.all_catalog().items()
            if class_name in requested)

    def merge_missing(self, catalog, timestamp, source_document=""):
        values = normalize_catalog(catalog)
        try:
            connection = self._connect()
            try:
                with connection:
                    for class_name, partial in values.items():
                        value = complete_catalog_record(partial)
                        if not any(value.values()):
                            continue
                        connection.execute(
                            "INSERT OR IGNORE INTO class_catalog "
                            "(class_name, product, description, dimensions, "
                            "color, manufacturer, updated_at, source_document) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (class_name, value["product"], value["description"],
                             value["dimensions"], value["color"],
                             value["manufacturer"],
                             int(timestamp), _text(source_document)))
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise MassDatabaseError(
                "Vorhandene Massendaten konnten nicht übernommen werden: %s" %
                error)

    def apply_catalog_updates(self, catalog, timestamp, source_document=""):
        values = normalize_catalog(catalog)
        try:
            connection = self._connect()
            try:
                with connection:
                    for class_name, partial in values.items():
                        row = connection.execute(
                            "SELECT class_name, product, description, dimensions, "
                            "color, manufacturer FROM class_catalog "
                            "WHERE class_name = ?",
                            (class_name,)).fetchone()
                        current = (
                            self._catalog_row(row) if row is not None else
                            complete_catalog_record())
                        current.update(partial)
                        if not any(current.values()):
                            connection.execute(
                                "DELETE FROM class_catalog WHERE class_name = ?",
                                (class_name,))
                            continue
                        connection.execute(
                            "INSERT INTO class_catalog "
                            "(class_name, product, description, dimensions, "
                            "color, manufacturer, updated_at, source_document) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                            "ON CONFLICT(class_name) DO UPDATE SET "
                            "product=excluded.product, "
                            "description=excluded.description, "
                            "dimensions=excluded.dimensions, "
                            "color=excluded.color, "
                            "manufacturer=excluded.manufacturer, "
                            "updated_at=excluded.updated_at, "
                            "source_document=excluded.source_document",
                            (class_name, current["product"],
                             current["description"], current["dimensions"],
                             current["color"], current["manufacturer"],
                             int(timestamp),
                             _text(source_document)))
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise MassDatabaseError(
                "Die Zusatzfelder konnten nicht gespeichert werden: %s" % error)

    def remap_class_names(self, mapping, timestamp, source_document=""):
        rename = dict(
            (_text(old_name), _text(new_name))
            for old_name, new_name in (mapping or {}).items()
            if _text(old_name) and _text(new_name))
        if not rename:
            return
        try:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT class_name, product, description, dimensions, "
                    "color, manufacturer, updated_at, source_document "
                    "FROM class_catalog"
                ).fetchall()
                catalog = {}
                for row in rows:
                    class_name = rename.get(str(row[0]), str(row[0]))
                    catalog[class_name] = (
                        str(row[1]), str(row[2]), str(row[3]), str(row[4]),
                        str(row[5]),
                        (int(timestamp) if str(row[0]) in rename else int(row[6])),
                        (_text(source_document) if str(row[0]) in rename else
                         str(row[7])))
                with connection:
                    connection.execute("DELETE FROM class_catalog")
                    for class_name, row in catalog.items():
                        connection.execute(
                            "INSERT INTO class_catalog "
                            "(class_name, product, description, dimensions, "
                            "color, manufacturer, updated_at, source_document) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (class_name,) + row)
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise MassDatabaseError(
                "Die Datenbank Massen konnte nach der Klassenumbenennung "
                "nicht aktualisiert werden: %s" % error)

    def record_run(
            self, timestamp, document_key, document_path, plugin_version,
            query_keys, rows, facts, adjustments, group_titles, catalog,
            worksheet_name="", xlsx_path="", exact_enabled=False,
            group_assignments=None, parallel_spacing_cm=None):
        """Atomically store every query element, fact, total and adjustment."""

        run_id = str(uuid.uuid4())
        query_keys = tuple(query_keys or ())
        rows = tuple(rows or ())
        facts = tuple(facts or ())
        adjustments = tuple(adjustments or ())
        catalog = normalize_catalog(catalog)
        group_assignments = dict(group_assignments or {})
        parallel_spacing_cm = dict(parallel_spacing_cm or {})
        quantity_keys = set(row.source_key for row in rows)

        def fields(class_name):
            return complete_catalog_record(catalog.get(class_name, {}))

        try:
            connection = self._connect()
            try:
                with connection:
                    connection.execute(
                        "INSERT INTO mass_runs "
                        "(run_id, created_at, document_key, document_path, "
                        "plugin_version, exact_duplicates_enabled, "
                        "worksheet_name, xlsx_path, "
                        "query_element_count, quantity_row_count, object_count) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (run_id, int(timestamp), _text(document_key),
                         _text(document_path), _text(plugin_version),
                         1 if exact_enabled else 0,
                         _text(worksheet_name), _text(xlsx_path), len(query_keys),
                         len(rows), len(facts)))
                    for index, key in enumerate(query_keys):
                        value = fields(key.class_name)
                        group_id = group_assignments.get(key)
                        connection.execute(
                            "INSERT INTO query_elements "
                            "(run_id, query_index, class_name, layer_id, "
                            "layer_name, element_kind, element_name, "
                            "group_id, group_title, "
                            "parallel_detected, parallel_spacing_cm, product, "
                            "description, dimensions, color, manufacturer, "
                            "has_quantity_row) VALUES "
                            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (run_id, index, key.class_name, key.layer_id,
                             key.layer_name, key.element_kind,
                             key.element_name, group_id,
                             _text(group_titles.get(group_id, "")),
                             1 if key in parallel_spacing_cm else 0,
                             float(parallel_spacing_cm.get(key, 0.0)),
                             value["product"],
                             value["description"], value["dimensions"],
                             value["color"], value["manufacturer"],
                             1 if key in quantity_keys else 0))
                    for index, row in enumerate(rows):
                        key = row.source_key
                        value = fields(key.class_name)
                        connection.execute(
                            "INSERT INTO mass_rows "
                            "(run_id, row_index, class_name, layer_id, "
                            "layer_name, element_kind, element_name, "
                            "group_id, group_title, product, "
                            "description, dimensions, color, manufacturer, "
                            "raw_area_m2, net_area_m2, raw_length_m, "
                            "net_length_m, raw_piece_count, net_piece_count, "
                            "group_count, symbol_count, representative_id, "
                            "adjustment_ids_json, warnings_json) VALUES "
                            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                            "?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (run_id, index, key.class_name, key.layer_id,
                             key.layer_name, key.element_kind,
                             key.element_name, row.group_id,
                             _text(group_titles.get(row.group_id, "")),
                             value["product"], value["description"],
                             value["dimensions"], value["color"],
                             value["manufacturer"],
                             float(row.raw_area_m2), float(row.net_area_m2),
                             float(row.raw_length_m), float(row.net_length_m),
                             int(row.raw_piece_count), int(row.net_piece_count),
                             int(row.group_count), int(row.symbol_count),
                             _text(row.representative_id),
                             _json(row.adjustment_ids), _json(row.warnings)))
                    for fact in facts:
                        key = fact.source_key
                        value = fields(key.class_name)
                        kind = getattr(fact.kind, "value", str(fact.kind))
                        connection.execute(
                            "INSERT INTO mass_objects "
                            "(run_id, object_id, class_name, layer_id, "
                            "layer_name, element_kind, element_name, "
                            "object_kind, measured_area_m2, "
                            "measured_length_m, piece_count, product, "
                            "description, dimensions, color, manufacturer, "
                            "parent_ids_json, representative_id, warnings_json) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                            "?, ?, ?, ?, ?)",
                            (run_id, fact.object_id, key.class_name, key.layer_id,
                             key.layer_name, key.element_kind,
                             key.element_name, str(kind),
                             float(fact.measured_area_m2),
                             float(fact.measured_length_m), int(fact.piece_count),
                             value["product"], value["description"],
                             value["dimensions"], value["color"],
                             value["manufacturer"],
                             _json(fact.parent_ids),
                             _text(fact.representative_id),
                             _json(fact.warnings)))
                    for adjustment in adjustments:
                        key = adjustment.source_key
                        connection.execute(
                            "INSERT INTO mass_adjustments "
                            "(run_id, adjustment_id, class_name, layer_id, "
                            "layer_name, element_kind, element_name, "
                            "adjustment_kind, object_ids_json, length_delta_m, "
                            "area_delta_m2, piece_delta, note) VALUES "
                            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (run_id, adjustment.adjustment_id, key.class_name,
                             key.layer_id, key.layer_name, key.element_kind,
                             key.element_name, adjustment.kind,
                             _json(adjustment.object_ids),
                             float(adjustment.length_delta_m),
                             float(adjustment.area_delta_m2),
                             int(adjustment.piece_delta), adjustment.note))
                return run_id
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise MassDatabaseError(
                "Der Abfragelauf konnte nicht in der Datenbank Massen "
                "gespeichert werden: %s" % error)

    def counts(self):
        try:
            connection = self._connect()
            try:
                return {
                    "catalog": int(connection.execute(
                        "SELECT COUNT(*) FROM class_catalog").fetchone()[0]),
                    "runs": int(connection.execute(
                        "SELECT COUNT(*) FROM mass_runs").fetchone()[0]),
                    "objects": int(connection.execute(
                        "SELECT COUNT(*) FROM mass_objects").fetchone()[0]),
                }
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise MassDatabaseError(
                "Die Datenbank Massen konnte nicht gezählt werden: %s" % error)

    def latest_query(self, document_key):
        """Return the most recent repeatable query for one document."""

        try:
            connection = self._connect()
            try:
                run = connection.execute(
                    "SELECT run_id, exact_duplicates_enabled FROM mass_runs "
                    "WHERE document_key = ? "
                    "ORDER BY created_at DESC, rowid DESC LIMIT 1",
                    (_text(document_key),),
                ).fetchone()
                if run is None:
                    return None
                rows = connection.execute(
                    "SELECT class_name, layer_id, layer_name, element_kind, "
                    "element_name, group_id, parallel_detected, "
                    "parallel_spacing_cm FROM query_elements "
                    "WHERE run_id = ? ORDER BY query_index",
                    (str(run[0]),),
                ).fetchall()
                keys = []
                assignments = []
                spacing = []
                for row in rows:
                    source = {
                        "class_name": str(row[0]),
                        "layer_id": str(row[1]),
                        "layer_name": str(row[2]),
                        "element_kind": str(row[3]),
                        "element_name": str(row[4]),
                    }
                    keys.append(source)
                    if row[5]:
                        assignments.append({
                            "source": dict(source),
                            "group_id": str(row[5]),
                        })
                    if bool(row[6]) and float(row[7]) > 0.01:
                        spacing.append({
                            "source": dict(source),
                            "value": float(row[7]),
                        })
                return {
                    "keys": keys,
                    "exact": bool(run[1]),
                    "group_assignments": assignments,
                    "parallel_spacing_cm": spacing,
                    "worksheet": True,
                    "xlsx": False,
                    "show_results": False,
                }
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise MassDatabaseError(
                "Die letzte Mengenabfrage konnte nicht gelesen werden: %s" %
                error)
