# -*- coding: utf-8 -*-
"""Persistent, project-scoped state for the PD class and quantity tools."""

from __future__ import absolute_import

import json
import os
import tempfile


SCHEMA_VERSION = 1
MAX_DOCUMENTS = 25
MAX_VISIBILITY_STEPS = 3


class StateStore(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)

    def _empty(self):
        return {"schema": SCHEMA_VERSION, "documents": {}}

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8-sig") as stream:
                value = json.load(stream)
        except FileNotFoundError:
            return self._empty()
        except (OSError, ValueError, TypeError) as error:
            raise RuntimeError(
                "Die Statusdatei konnte nicht sicher gelesen werden: %s. "
                "Sie wurde nicht überschrieben. Bitte die Datei sichern "
                "und prüfen lassen." % self.path) from error
        if not isinstance(value, dict) or not isinstance(value.get("documents"), dict):
            raise RuntimeError("Ungültige Statusdatei (unverändert): " + self.path)
        if int(value.get("schema", 0)) != SCHEMA_VERSION:
            return self._migrate(value)
        return value

    def _migrate(self, value):
        # Version 1 is the first public schema. Unknown state is intentionally
        # rejected instead of risking an invalid restore or overwriting data.
        raise RuntimeError("Nicht unterstützte Statusversion (unverändert): " + self.path)

    def save(self, value):
        target_directory = os.path.dirname(self.path)
        if target_directory and not os.path.isdir(target_directory):
            os.makedirs(target_directory)
        descriptor, temporary = tempfile.mkstemp(
            prefix="pd_km_state_", suffix=".json", dir=target_directory or None)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.remove(temporary)

    def document(self, document_key, create=True):
        data = self.load()
        documents = data["documents"]
        document = documents.get(document_key)
        if document is None and create:
            document = {
                "undo": [],
                "redo": [],
                "last_quantities": None,
                "last_used": 0,
            }
            documents[document_key] = document
            self._trim(documents, keep=document_key)
            self.save(data)
        return data, document

    @staticmethod
    def _trim(documents, keep):
        while len(documents) > MAX_DOCUMENTS:
            candidates = [
                (int(value.get("last_used", 0)), key)
                for key, value in documents.items() if key != keep
            ]
            if not candidates:
                break
            del documents[min(candidates)[1]]

    def push_visibility(self, document_key, snapshot, timestamp):
        data, document = self.document(document_key)
        document["undo"] = (document.get("undo") or [])[-(MAX_VISIBILITY_STEPS - 1):] + [snapshot]
        document["redo"] = []
        document["last_used"] = int(timestamp)
        self.save(data)

    def pop_visibility_undo(self, document_key, current_snapshot, timestamp):
        snapshot = self.peek_visibility_undo(document_key)
        if snapshot is None:
            return None
        self.commit_visibility_undo(
            document_key, snapshot, current_snapshot, timestamp)
        return snapshot

    def peek_visibility_undo(self, document_key):
        _data, document = self.document(document_key, create=False)
        if document is None:
            return None
        undo = document.get("undo") or []
        return undo[-1] if undo else None

    def discard_visibility_undo(self, document_key, expected_snapshot, timestamp):
        """Remove a journal entry which does not change any visibility value."""
        data, document = self.document(document_key)
        undo = document.get("undo") or []
        if not undo or undo[-1] != expected_snapshot:
            raise RuntimeError("Sichtbarkeitsverlauf wurde zwischenzeitlich geändert.")
        undo.pop()
        document["undo"] = undo
        document["last_used"] = int(timestamp)
        self.save(data)

    def commit_visibility_undo(self, document_key, expected_snapshot,
                               current_snapshot, timestamp):
        data, document = self.document(document_key)
        undo = document.get("undo") or []
        if not undo or undo[-1] != expected_snapshot:
            raise RuntimeError("Sichtbarkeitsverlauf wurde zwischenzeitlich geändert.")
        snapshot = undo.pop()
        document["undo"] = undo
        document["redo"] = ((document.get("redo") or []) + [current_snapshot])[-MAX_VISIBILITY_STEPS:]
        document["last_used"] = int(timestamp)
        self.save(data)
        return snapshot

    def pop_visibility_redo(self, document_key, current_snapshot, timestamp):
        snapshot = self.peek_visibility_redo(document_key)
        if snapshot is None:
            return None
        self.commit_visibility_redo(
            document_key, snapshot, current_snapshot, timestamp)
        return snapshot

    def peek_visibility_redo(self, document_key):
        _data, document = self.document(document_key, create=False)
        if document is None:
            return None
        redo = document.get("redo") or []
        return redo[-1] if redo else None

    def commit_visibility_redo(self, document_key, expected_snapshot,
                               current_snapshot, timestamp):
        data, document = self.document(document_key)
        redo = document.get("redo") or []
        if not redo or redo[-1] != expected_snapshot:
            raise RuntimeError("Sichtbarkeitsverlauf wurde zwischenzeitlich geändert.")
        snapshot = redo.pop()
        document["redo"] = redo
        document["undo"] = ((document.get("undo") or []) + [current_snapshot])[-MAX_VISIBILITY_STEPS:]
        document["last_used"] = int(timestamp)
        self.save(data)
        return snapshot

    def set_last_quantities(self, document_key, payload, timestamp):
        data, document = self.document(document_key)
        document["last_quantities"] = payload
        document["last_used"] = int(timestamp)
        self.save(data)

    def get_last_quantities(self, document_key):
        _data, document = self.document(document_key, create=False)
        if not document:
            return None
        return document.get("last_quantities")

    def remap_class_names(self, document_key, mapping, timestamp):
        """Keep saved visibility/results valid after a class rename."""
        rename = dict(mapping or {})
        if not rename:
            return
        data, document = self.document(document_key)

        def remap_snapshot(snapshot):
            value = dict(snapshot)
            classes = {}
            for old_name, visibility in (snapshot.get("classes") or {}).items():
                classes[rename.get(old_name, old_name)] = visibility
            value["classes"] = classes
            active = snapshot.get("active_class")
            if active:
                value["active_class"] = rename.get(active, active)
            viewport = snapshot.get("viewport")
            if isinstance(viewport, dict):
                viewport = dict(viewport)
                viewport["classes"] = dict(
                    (rename.get(old_name, old_name), visibility)
                    for old_name, visibility in
                    (viewport.get("classes") or {}).items()
                )
                value["viewport"] = viewport
            return value

        document["undo"] = [
            remap_snapshot(snapshot)
            for snapshot in (document.get("undo") or [])
        ]
        document["redo"] = [
            remap_snapshot(snapshot)
            for snapshot in (document.get("redo") or [])
        ]
        quantities = document.get("last_quantities")
        if isinstance(quantities, dict):
            quantities = dict(quantities)
            remapped_rows = []
            for row in quantities.get("rows") or []:
                row = dict(row)
                old_name = row.get("class_name")
                if old_name:
                    row["class_name"] = rename.get(old_name, old_name)
                remapped_rows.append(row)
            quantities["rows"] = remapped_rows
            remapped_products = {}
            for old_name, product in (quantities.get("products") or {}).items():
                remapped_products[rename.get(old_name, old_name)] = product
            quantities["products"] = remapped_products
            remapped_catalog = {}
            for old_name, values in (quantities.get("catalog") or {}).items():
                remapped_catalog[rename.get(old_name, old_name)] = values
            quantities["catalog"] = remapped_catalog
            query = quantities.get("query")
            if isinstance(query, dict):
                query = dict(query)

                def remap_source(source):
                    if not isinstance(source, dict):
                        return source
                    source = dict(source)
                    old_name = source.get("class_name")
                    if old_name:
                        source["class_name"] = rename.get(
                            old_name, old_name)
                    return source

                query["keys"] = [
                    remap_source(source)
                    for source in (query.get("keys") or [])
                ]
                for field_name in (
                        "group_assignments", "parallel_spacing_cm"):
                    remapped_items = []
                    for item in query.get(field_name) or []:
                        if not isinstance(item, dict):
                            remapped_items.append(item)
                            continue
                        item = dict(item)
                        item["source"] = remap_source(item.get("source"))
                        remapped_items.append(item)
                    query[field_name] = remapped_items
                quantities["query"] = query
            document["last_quantities"] = quantities
        document["last_used"] = int(timestamp)
        self.save(data)
