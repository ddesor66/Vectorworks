# -*- coding: utf-8 -*-
"""Pure class/layer filtering for the automatic-label source dialog."""

from __future__ import absolute_import

import fnmatch


def split_patterns(value):
    if isinstance(value, str):
        values = value.split(";")
    else:
        values = tuple(value or ())
    return tuple(str(item).strip() for item in values if str(item).strip())


def _matches(name, patterns):
    folded = str(name).casefold()
    return any(fnmatch.fnmatchcase(folded, pattern.casefold())
               for pattern in split_patterns(patterns))


def dimension_matches(name, enabled, include=(), exclude=(), manual=()):
    """Apply an optional include/exclude glob filter to one exact name."""
    if not enabled:
        return True
    include = split_patterns(include)
    exclude = split_patterns(exclude)
    manual = set(str(value).casefold() for value in (manual or ()))
    included = (not include and not manual) or _matches(name, include)
    included = included or str(name).casefold() in manual
    return included and not _matches(name, exclude)


def filter_occupied_rows(rows, class_enabled=False, class_include=(),
                         class_exclude=(), manual_classes=(),
                         layer_enabled=False, layer_include=(),
                         layer_exclude=(), manual_layers=()):
    """Return occupied ``(class, layer, count)`` rows in filter scope."""
    result = []
    for class_name, layer_name, count in rows:
        if not dimension_matches(
                class_name, class_enabled, class_include, class_exclude,
                manual_classes):
            continue
        if not dimension_matches(
                layer_name, layer_enabled, layer_include, layer_exclude,
                manual_layers):
            continue
        result.append((str(class_name), str(layer_name), int(count)))
    return tuple(sorted(result, key=lambda row: (
        row[0].casefold(), row[1].casefold(), row[0], row[1])))
