# -*- coding: utf-8 -*-
"""Reusable class/product database for quantity worksheets."""

from __future__ import absolute_import

import os
import sqlite3


SCHEMA_VERSION = 1


class ProductDatabaseError(RuntimeError):
    """Raised when the reusable product database cannot be used safely."""


def _normalized_products(products):
    if not isinstance(products, dict):
        return {}
    normalized = {}
    for class_name, product in products.items():
        class_name = str(class_name or "").strip()
        if not class_name:
            continue
        normalized[class_name] = str(product or "").strip()
    return normalized


class ProductDatabase(object):
    """SQLite-backed product assignments shared by all Vectorworks documents."""

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
        except ProductDatabaseError:
            if connection is not None:
                connection.close()
            raise
        except (OSError, sqlite3.Error) as error:
            if connection is not None:
                connection.close()
            raise ProductDatabaseError(
                "Die wiederverwendbare Produktdatenbank konnte nicht geöffnet "
                "werden: %s" % error)

    @staticmethod
    def _ensure_schema(connection):
        row = connection.execute("PRAGMA user_version").fetchone()
        version = int(row[0] if row else 0)
        if version > SCHEMA_VERSION:
            raise ProductDatabaseError(
                "Die Produktdatenbank verwendet das neuere Schema %d; "
                "unterstützt wird Schema %d." % (version, SCHEMA_VERSION))
        if version == 0:
            with connection:
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS metadata ("
                    "key TEXT PRIMARY KEY NOT NULL, "
                    "value TEXT NOT NULL)"
                )
                connection.execute(
                    "CREATE TABLE IF NOT EXISTS class_products ("
                    "class_name TEXT PRIMARY KEY NOT NULL, "
                    "product TEXT NOT NULL, "
                    "updated_at INTEGER NOT NULL, "
                    "source_document TEXT NOT NULL DEFAULT '')"
                )
                connection.execute(
                    "INSERT OR REPLACE INTO metadata(key, value) "
                    "VALUES('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
                connection.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
            version = SCHEMA_VERSION
        if version != SCHEMA_VERSION:
            raise ProductDatabaseError(
                "Das Schema der Produktdatenbank wird nicht unterstützt.")

    def all_products(self):
        try:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT class_name, product FROM class_products "
                    "ORDER BY class_name COLLATE NOCASE"
                ).fetchall()
                return dict((str(row[0]), str(row[1])) for row in rows)
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise ProductDatabaseError(
                "Die Produktdatenbank konnte nicht gelesen werden: %s" % error)

    def products_for_classes(self, class_names):
        requested = set(
            str(class_name or "").strip()
            for class_name in class_names or ()
            if str(class_name or "").strip()
        )
        return dict(
            (class_name, product)
            for class_name, product in self.all_products().items()
            if class_name in requested
        )

    def merge_missing(self, products, timestamp, source_document=""):
        """Import legacy assignments without replacing newer shared values."""
        values = _normalized_products(products)
        try:
            connection = self._connect()
            try:
                with connection:
                    for class_name, product in values.items():
                        if not product:
                            continue
                        connection.execute(
                            "INSERT OR IGNORE INTO class_products "
                            "(class_name, product, updated_at, source_document) "
                            "VALUES (?, ?, ?, ?)",
                            (class_name, product, int(timestamp),
                             str(source_document or "")),
                        )
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise ProductDatabaseError(
                "Vorhandene Produktzuordnungen konnten nicht übernommen "
                "werden: %s" % error)

    def apply_updates(self, products, timestamp, source_document=""):
        """Apply worksheet edits; an empty product deliberately deletes a row."""
        values = _normalized_products(products)
        try:
            connection = self._connect()
            try:
                with connection:
                    for class_name, product in values.items():
                        if not product:
                            connection.execute(
                                "DELETE FROM class_products WHERE class_name = ?",
                                (class_name,),
                            )
                            continue
                        connection.execute(
                            "INSERT INTO class_products "
                            "(class_name, product, updated_at, source_document) "
                            "VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(class_name) DO UPDATE SET "
                            "product = excluded.product, "
                            "updated_at = excluded.updated_at, "
                            "source_document = excluded.source_document",
                            (class_name, product, int(timestamp),
                             str(source_document or "")),
                        )
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise ProductDatabaseError(
                "Änderungen konnten nicht in der Produktdatenbank gespeichert "
                "werden: %s" % error)

    def remap_class_names(self, mapping, timestamp, source_document=""):
        """Rename database keys simultaneously, including cyclic mappings."""
        rename = dict(
            (str(old_name or "").strip(), str(new_name or "").strip())
            for old_name, new_name in (mapping or {}).items()
            if str(old_name or "").strip() and str(new_name or "").strip()
        )
        if not rename:
            return
        try:
            connection = self._connect()
            try:
                rows = connection.execute(
                    "SELECT class_name, product, updated_at, source_document "
                    "FROM class_products"
                ).fetchall()
                stationary = {}
                moved = []
                for row in rows:
                    old_name = str(row[0])
                    record = (str(row[1]), int(row[2]), str(row[3]))
                    if old_name in rename:
                        moved.append((rename[old_name], record[0]))
                    else:
                        stationary[old_name] = record
                # A renamed, currently existing class is authoritative over an
                # orphaned catalog entry that already used its destination.
                for new_name, product in moved:
                    stationary[new_name] = (
                        product, int(timestamp), str(source_document or ""))
                with connection:
                    connection.execute("DELETE FROM class_products")
                    for class_name, record in stationary.items():
                        connection.execute(
                            "INSERT INTO class_products "
                            "(class_name, product, updated_at, source_document) "
                            "VALUES (?, ?, ?, ?)",
                            (class_name, record[0], record[1], record[2]),
                        )
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise ProductDatabaseError(
                "Die Produktdatenbank konnte nach der Klassenumbenennung "
                "nicht aktualisiert werden: %s" % error)

    def count(self):
        try:
            connection = self._connect()
            try:
                row = connection.execute(
                    "SELECT COUNT(*) FROM class_products").fetchone()
                return int(row[0] if row else 0)
            finally:
                connection.close()
        except sqlite3.Error as error:
            raise ProductDatabaseError(
                "Die Produktdatenbank konnte nicht gezählt werden: %s" % error)
