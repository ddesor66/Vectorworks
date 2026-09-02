# -*- coding: utf-8 -*-
"""Per-user writable storage, with non-destructive migration of older data."""

import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


def data_path(filename, legacy_directory, user_directory):
    if not user_directory or not os.path.isabs(user_directory):
        raise RuntimeError("Der Vectorworks-Benutzerordner konnte nicht ermittelt werden.")
    directory = os.path.join(user_directory, "PD_ToolsPD", "Massenermittlung")
    os.makedirs(directory, exist_ok=True)
    target = os.path.join(directory, filename)
    legacy = os.path.join(legacy_directory, filename)
    if os.path.isfile(target) or not os.path.isfile(legacy):
        return target
    descriptor, temporary = tempfile.mkstemp(prefix="migration_", dir=directory)
    os.close(descriptor)
    try:
        if filename.lower().endswith((".sqlite3", ".sqlite", ".db")):
            # SQLite's backup includes committed WAL data; copying only the
            # main file could silently omit recent catalogue entries.
            with closing(sqlite3.connect(Path(legacy).resolve().as_uri() + "?mode=ro", uri=True)) as source:
                with closing(sqlite3.connect(temporary)) as destination:
                    source.backup(destination)
        else:
            shutil.copy2(legacy, temporary)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return target
