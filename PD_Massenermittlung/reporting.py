# -*- coding: utf-8 -*-
"""Vectorworks worksheet and XLSX reporting for quantity results."""

from __future__ import absolute_import

import datetime
import os

import vs

from .mass_database import complete_catalog_record
from .report_columns import (
    HEADERS,
    WORKSHEET_WIDTHS,
    XLSX_WIDTHS,
    normalize_visible_columns,
    validate_editable_columns,
    project_values,
    project_widths,
    visible_column_indices,
)
from .xlsx_writer import (
    STYLE_GROUP,
    STYLE_HEADER,
    STYLE_INTEGER,
    STYLE_NUMBER,
    STYLE_TOTAL,
    STYLE_TOTAL_INTEGER,
    STYLE_WARNING,
    styled,
    write_xlsx,
)


CATALOG_HEADERS = (
    ("product", "Produkt"),
    ("description", "Beschreibung"),
    ("dimensions", "Abmessung"),
    ("color", "Farbe"),
    ("manufacturer", "Hersteller"),
)

AUDIT_HEADERS = (
    "Art", "Klasse", "Konstruktionsebene", "Objekte",
    "Längenabzug [m]", "Flächenabzug [m²]", "Stückabzug", "Hinweis",
)

_NO_DEFAULT = object()


def _natural(value):
    return str(value or "").casefold()


def _ordered_groups(rows, group_titles):
    groups = {}
    for row in rows:
        group_id = row.group_id
        groups.setdefault(group_id, []).append(row)
    order = sorted(
        groups,
        key=lambda group_id: (
            group_id is None,
            _natural(group_titles.get(group_id, "Nicht gruppiert")),
        ),
    )
    return [(group_id, group_titles.get(group_id, "Nicht gruppiert"), groups[group_id])
            for group_id in order]


def _group_totals(group_rows):
    return {
        "raw_area": sum(row.raw_area_m2 for row in group_rows),
        "net_area": sum(row.net_area_m2 for row in group_rows),
        "raw_length": sum(row.raw_length_m for row in group_rows),
        "net_length": sum(row.net_length_m for row in group_rows),
        "raw_pieces": sum(row.raw_piece_count for row in group_rows),
        "net_pieces": sum(row.net_piece_count for row in group_rows),
        "groups": sum(row.group_count for row in group_rows),
        "symbols": sum(row.symbol_count for row in group_rows),
    }


def _class_catalog(catalog, class_name):
    value = dict(catalog or {}).get(class_name, {})
    return complete_catalog_record(value)


def report_records(rows, group_titles, catalog=None):
    records = []
    for group_id, title, group_rows in _ordered_groups(rows, group_titles):
        records.append({"kind": "group", "title": title, "group_id": group_id})
        for row in group_rows:
            class_catalog = _class_catalog(
                catalog, row.source_key.class_name)
            records.append({
                "kind": "row",
                "title": title,
                "row": row,
                "values": (
                    "", title, row.source_key.class_name,
                    row.source_key.element_label,
                    class_catalog["product"], class_catalog["description"],
                    class_catalog["dimensions"], class_catalog["color"],
                    class_catalog["manufacturer"],
                    row.source_key.layer_name, row.raw_area_m2, row.net_area_m2,
                    row.raw_length_m, row.net_length_m,
                    row.raw_piece_count, row.net_piece_count,
                    row.group_count, row.symbol_count,
                    "; ".join(row.warnings),
                ),
            })
        records.append({
            "kind": "total",
            "title": title,
            "group_id": group_id,
            "totals": _group_totals(group_rows),
        })
    return records


def xlsx_rows(rows, group_titles, catalog=None, visible_columns=None):
    visible_columns = xlsx_columns(visible_columns)
    indices = visible_column_indices(visible_columns)
    result = [[styled(value, STYLE_HEADER) for value in visible_columns]]
    for record in report_records(rows, group_titles, catalog):
        if record["kind"] == "group":
            values = [""] * len(HEADERS)
            values[1] = record["title"]
            projected = list(project_values(values, visible_columns))
            if "Gruppe" not in visible_columns:
                projected[0] = record["title"]
            result.append([
                styled(value, STYLE_GROUP) for value in projected])
        elif record["kind"] == "row":
            values = list(record["values"])
            values[0] = "Objektbild im Vectorworks-Arbeitsblatt"
            styled_values = []
            for index in indices:
                value = values[index]
                if 10 <= index <= 13:
                    style = STYLE_NUMBER
                elif 14 <= index <= 17:
                    style = STYLE_INTEGER
                else:
                    style = 0
                if index == 18 and value:
                    style = STYLE_WARNING
                styled_values.append(styled(value, style))
            result.append(styled_values)
        else:
            totals = record["totals"]
            values = (
                "", "SUMME " + record["title"], "", "", "", "", "", "", "", "",
                totals["raw_area"], totals["net_area"],
                totals["raw_length"], totals["net_length"],
                totals["raw_pieces"], totals["net_pieces"],
                totals["groups"], totals["symbols"], "",
            )
            projected = list(project_values(values, visible_columns))
            if "Gruppe" not in visible_columns:
                projected[0] = "SUMME " + record["title"]
            result.append([
                styled(
                    value,
                    STYLE_TOTAL_INTEGER if 14 <= index <= 17 else STYLE_TOTAL,
                )
                for index, value in zip(indices, projected)
            ])
    return result


def _audit_values(analysis):
    values = []
    for adjustment in analysis.adjustments:
        values.append((
            adjustment.kind,
            adjustment.source_key.class_name,
            adjustment.source_key.layer_name,
            ", ".join(adjustment.object_ids),
            adjustment.length_delta_m,
            adjustment.area_delta_m2,
            adjustment.piece_delta,
            adjustment.note,
        ))
    for warning in analysis.warnings:
        values.append(("WARNUNG", "", "", "", "", "", "", warning))
    if not values:
        values.append((
            "INFO", "", "", "", 0.0, 0.0, 0,
            "Keine Kürzungen oder Warnungen",
        ))
    return values


def audit_rows(analysis):
    rows = [[styled(value, STYLE_HEADER) for value in AUDIT_HEADERS]]
    for values in _audit_values(analysis):
        row = []
        for index, value in enumerate(values):
            if index in (4, 5):
                style = STYLE_NUMBER
            elif index == 6:
                style = STYLE_INTEGER
            elif values[0] == "WARNUNG" and index in (0, 7):
                style = STYLE_WARNING
            else:
                style = 0
            row.append(styled(value, style))
        rows.append(row)
    return rows


def default_xlsx_path(document_path):
    if not document_path:
        return ""
    directory = os.path.dirname(os.path.abspath(document_path))
    base = os.path.splitext(os.path.basename(document_path))[0]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    return os.path.join(directory, "%s_Massenermittlung_%s.xlsx" % (base, stamp))


def xlsx_columns(values):
    return tuple(name for name in normalize_visible_columns(values)
                 if name != "Grafik") or ("Klasse",)


def export_xlsx(
        path, rows, group_titles, analysis, catalog=None,
        visible_columns=None, show_audit=True):
    visible_columns = xlsx_columns(visible_columns)
    sheets = [{
        "name": "Mengen",
        "rows": xlsx_rows(
            rows, group_titles, catalog, visible_columns),
        "widths": project_widths(XLSX_WIDTHS, visible_columns),
        "freeze_rows": 1,
        "auto_filter": True,
    }]
    if show_audit:
        sheets.append({
            "name": "Prüfprotokoll",
            "rows": audit_rows(analysis),
            "widths": (22, 34, 28, 55, 18, 18, 14, 48),
            "freeze_rows": 1,
            "auto_filter": True,
        })
    return write_xlsx(path, sheets)


def _ws_call(name, *args, **kwargs):
    default = kwargs.pop("default", _NO_DEFAULT)
    try:
        return getattr(vs, name)(*args)
    except Exception:
        if default is _NO_DEFAULT:
            raise
        return default


def _ws_text(value):
    text = str(value if value is not None else "")
    # Worksheet formulas begin with '='. User-controlled names remain text.
    return "'" + text if text.startswith("=") else text


def _set_cell(ws, row, column, value):
    if isinstance(value, float):
        text = ("%.12f" % value).rstrip("0").rstrip(".") or "0"
    else:
        text = _ws_text(value)
    _ws_call("SetWSCellFormulaN", ws, row, column, row, column, text)


def _criteria_value(value):
    return str(value or "").replace("'", "''")


def _image_formula(source_key):
    class_value = _criteria_value(source_key.class_name)
    layer_value = _criteria_value(source_key.layer_name)
    criteria = ["(C='%s')" % class_value, "(L='%s')" % layer_value]
    if source_key.element_kind == "symbol":
        # ``S`` is Vectorworks' documented symbol-name criterion. Without
        # this additional predicate every symbol row would show the complete
        # class/layer geometry instead of the named symbol type.
        criteria.append("(S='%s')" % _criteria_value(
            source_key.element_name))
    # The German Vectorworks 2026 worksheet function is named GRAFIK. The
    # documented search criteria do not expose an object UUID predicate. An
    # exact UUID image would therefore require a document script resource via
    # RUNSCRIPT + WSScript_SetResImage; Vectorworks asks the user to approve
    # worksheet scripts. Keep this ordinary, non-scripted preview here.
    return "=GRAFIK(%s)" % " & ".join(criteria)


def _set_image_cell(ws, row, column, source_key):
    """Write a compact, criteria-based object or symbol preview."""

    _ws_call(
        "SetWSCellFormulaN", ws,
        row, column, row, column, _image_formula(source_key))
    _ws_call("SetWSImgType", ws, row, column, row, column, 1)
    _ws_call("SetWSImgUseObjectImg", ws, row, column, row, column, True)
    _ws_call("SetWSImgUseLayScale", ws, row, column, row, column, False)
    _ws_call("SetWSImgView", ws, row, column, row, column, 2)
    # Explicit dimensions plus a margin keep even very large symbols as a
    # small thumbnail. These APIs do not alter the source object or symbol.
    _ws_call("SetWSImgSize", ws, row, column, row, column, 24, 32)
    _ws_call("SetWSImgMarginSize", ws, row, column, row, column, 3)


def _set_bold(ws, row, last_column):
    font_index = _ws_call("GetFontID", "Arial")
    if font_index is None:
        font_index = 0
    _ws_call("SetWSCellTextFormat", ws, row, 1, row, last_column,
             int(font_index), 10, 1)


def _unique_worksheet_name(prefix="PD Massenermittlung"):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H-%M")
    base = "%s %s" % (prefix, stamp)
    candidate = base
    counter = 2
    while _ws_call("GetObject", candidate):
        candidate = "%s (%d)" % (base, counter)
        counter += 1
    return candidate


def worksheet_resource_name(worksheet):
    """Return the persistent Vectorworks resource name for a worksheet."""

    return str(_ws_call("GetName", worksheet) or "")


def read_catalog_from_worksheet(worksheet_name):
    """Read manually edited reusable class fields from a prior report.

    The generated quantity table stores ordinary text cells.  Reading their
    displayed strings keeps product values editable in Vectorworks while the
    saved worksheet resource name lets the next run recover those edits.
    """

    name = str(worksheet_name or "").strip()
    if not name:
        return {}
    worksheet = _ws_call("GetObject", name)
    if not worksheet:
        return {}
    row_count, column_count = _ws_call("GetWSRowColumnCount", worksheet)
    if int(row_count) < 2 or int(column_count) < 1:
        return {}

    headers = [
        str(_ws_call("GetWSCellStringN", worksheet, 1, column) or "").strip()
        for column in range(1, int(column_count) + 1)
    ]
    try:
        class_column = headers.index("Klasse") + 1
    except ValueError:
        validate_editable_columns(headers)
        return {}
    field_columns = dict(
        (field, headers.index(header) + 1)
        for field, header in CATALOG_HEADERS
        if header in headers)
    if not field_columns:
        return {}

    values_by_class = {}
    main_column_count = min(int(column_count), len(HEADERS))
    for row in range(2, int(row_count) + 1):
        visible = [
            str(_ws_call(
                "GetWSCellStringN", worksheet, row, column) or "").strip()
            for column in range(1, main_column_count + 1)
        ]
        # The generated blank separator marks the end of the quantity table;
        # rows below it belong to the audit section and must not be read as
        # reusable catalog assignments.
        if not any(visible):
            break
        class_name = str(_ws_call(
            "GetWSCellStringN", worksheet, row, class_column) or "").strip()
        if not class_name:
            continue
        class_values = values_by_class.setdefault(class_name, {})
        for field, column in field_columns.items():
            value = str(_ws_call(
                "GetWSCellStringN", worksheet, row, column) or "").strip()
            class_values.setdefault(field, set()).add(value)

    catalog = {}
    conflicts = []
    header_by_field = dict(CATALOG_HEADERS)
    for class_name, fields in sorted(values_by_class.items()):
        catalog[class_name] = {}
        for field, values in fields.items():
            non_empty = sorted(value for value in values if value)
            if len(non_empty) > 1:
                conflicts.append(
                    "%s / %s: %s" % (
                        class_name, header_by_field[field],
                        " / ".join(non_empty)))
                continue
            catalog[class_name][field] = non_empty[0] if non_empty else ""
    if conflicts:
        raise ValueError(
            "Für dieselbe Klasse stehen unterschiedliche Zusatzwerte im "
            "letzten Arbeitsblatt. Bitte dort vereinheitlichen:\n- "
            + "\n- ".join(conflicts)
        )
    return catalog


def read_products_from_worksheet(worksheet_name):
    """Backward-compatible product-only view used by older integrations."""

    return dict(
        (class_name, values.get("product", ""))
        for class_name, values in
        read_catalog_from_worksheet(worksheet_name).items()
        if "product" in values)


def _delete_incomplete_worksheet(ws, original_error):
    """Delete a worksheet created by a failed report operation.

    ``DelObject`` is the documented Vectorworks API for deleting the
    referenced worksheet resource. A failed rollback is surfaced explicitly;
    silently leaving a half-built worksheet would be worse than the original
    report error.
    """

    try:
        _ws_call("DelObject", ws)
    except Exception as cleanup_error:
        raise RuntimeError(
            "Unvollständiges Vectorworks-Arbeitsblatt konnte nicht gelöscht "
            "werden. Erstellungsfehler: %s; Löschfehler: %s"
            % (original_error, cleanup_error)
        ) from cleanup_error


def show_vectorworks_worksheet(worksheet):
    """Open a completed worksheet only when no modal chooser is active."""

    if not worksheet:
        raise RuntimeError("Vectorworks-Arbeitsblatt ist nicht verfügbar.")
    _ws_call("ShowWS", worksheet, True)


def _set_worksheet_name(worksheet, name):
    """Assign and verify an exact Vectorworks resource name."""

    _ws_call("SetName", worksheet, name)
    actual = str(_ws_call("GetName", worksheet) or "")
    if actual != name or not _ws_call("GetObject", name):
        raise RuntimeError(
            "Vectorworks hat den Arbeitsblattnamen „%s“ nicht übernommen."
            % name)


def _delete_worksheet(worksheet, name):
    _ws_call("DelObject", worksheet)
    if _ws_call("GetObject", name):
        raise RuntimeError(
            "Das bisherige Arbeitsblatt „%s“ konnte nicht entfernt werden."
            % name)


def _resize_and_clear_worksheet(worksheet, row_count, column_count):
    """Resize an existing worksheet while retaining its resource handle."""

    current_rows, current_columns = _ws_call(
        "GetWSRowColumnCount", worksheet)
    current_rows = int(current_rows)
    current_columns = int(current_columns)
    row_count = max(1, int(row_count))
    column_count = max(1, int(column_count))

    if current_rows < row_count:
        _ws_call(
            "InsertWSRows", worksheet, current_rows,
            row_count - current_rows)
    elif current_rows > row_count:
        _ws_call(
            "DeleteWSRows", worksheet, row_count + 1,
            current_rows - row_count)

    if current_columns < column_count:
        _ws_call(
            "InsertWSColumns", worksheet, current_columns,
            column_count - current_columns)
    elif current_columns > column_count:
        _ws_call(
            "DeleteWSColumns", worksheet, column_count + 1,
            current_columns - column_count)

    resized_rows, resized_columns = _ws_call(
        "GetWSRowColumnCount", worksheet)
    if (int(resized_rows), int(resized_columns)) != (
            row_count, column_count):
        raise RuntimeError(
            "Vectorworks hat die Massentabelle nicht auf %d Zeilen und %d "
            "Spalten angepasst." % (row_count, column_count))
    _ws_call(
        "ClearWSCell", worksheet, 1, 1, row_count, column_count)


def _refresh_worksheet_image(worksheet):
    """Redraw an already placed worksheet image after an in-place update."""

    image = _ws_call("GetWSImage", worksheet, default=None)
    if image:
        # SetWSImgShowDBHeader has an explicit ``redrawImage`` argument in
        # the Vectorworks 2026 API. Reapplying the current value with redraw
        # enabled refreshes the placed worksheet even when it is on a layer
        # other than the active one. ResetObject remains as the documented
        # general object reset directly afterwards.
        show_database_headers = bool(_ws_call(
            "GetWSImgShowDBHeader", image, default=False))
        _ws_call(
            "SetWSImgShowDBHeader", image,
            show_database_headers, True, default=None)
        _ws_call("ResetObject", image, default=None)
    _ws_call("RedrawAll", default=None)


def replace_vectorworks_worksheet(
        worksheet_name, rows, group_titles, analysis, catalog=None,
        show=True, visible_columns=None, show_audit=True):
    """Validate new content, then update the persistent worksheet in place.

    A worksheet image placed on the drawing is linked to the worksheet handle,
    not merely to its resource name. Replacing the resource therefore leaves
    that image stale. Keeping ``previous`` and only replacing its cells also
    keeps the placed table's position, scale and object link intact.
    """

    target_name = str(worksheet_name or "").strip()
    if not target_name:
        return create_vectorworks_worksheet(
            rows, group_titles, analysis, catalog, show=show,
            visible_columns=visible_columns, show_audit=show_audit)

    previous = _ws_call("GetObject", target_name)
    replacement = create_vectorworks_worksheet(
        rows, group_titles, analysis, catalog, show=False,
        visible_columns=visible_columns, show_audit=show_audit)
    replacement_name = str(_ws_call("GetName", replacement) or "")

    if not previous:
        try:
            _set_worksheet_name(replacement, target_name)
        except Exception as error:
            _delete_incomplete_worksheet(replacement, error)
            raise
        if show:
            show_vectorworks_worksheet(replacement)
        return replacement

    previous_visible = bool(_ws_call(
        "IsWSVisible", previous, default=False))
    try:
        _populate_vectorworks_worksheet(
            previous, rows, group_titles, analysis, catalog,
            visible_columns=visible_columns, show_audit=show_audit)
        if str(_ws_call("GetName", previous) or "") != target_name:
            raise RuntimeError(
                "Der Name der bestehenden Massentabelle wurde unerwartet "
                "verändert.")
        _refresh_worksheet_image(previous)
    except Exception as error:
        recovery_name = _unique_worksheet_name(
            target_name + " – Wiederherstellung")
        try:
            _set_worksheet_name(replacement, recovery_name)
        except Exception:
            recovery_name = replacement_name
        raise RuntimeError(
            "Die platzierte Massentabelle konnte nicht vollständig "
            "aktualisiert werden: %s. Eine vollständige "
            "Wiederherstellungstabelle wurde unter „%s“ behalten."
            % (error, recovery_name)) from error

    _delete_worksheet(replacement, replacement_name)

    if show:
        show_vectorworks_worksheet(previous)
    elif previous_visible:
        # Do not close a worksheet window that was already open before an
        # update requested without opening a new one.
        show_vectorworks_worksheet(previous)
    return previous


def create_vectorworks_worksheet(
        rows, group_titles, analysis, catalog=None, show=True,
        visible_columns=None, show_audit=True):
    visible_columns = normalize_visible_columns(visible_columns)
    records = report_records(rows, group_titles, catalog)
    audit_values = _audit_values(analysis) if show_audit else ()
    total_column_count = (
        max(len(visible_columns), len(AUDIT_HEADERS))
        if show_audit else len(visible_columns))
    total_rows = (
        4 + len(records) + len(audit_values)
        if show_audit else 1 + len(records))
    ws = _ws_call(
        "CreateWS", _unique_worksheet_name(), total_rows,
        total_column_count)
    if not ws:
        raise RuntimeError("Vectorworks-Arbeitsblatt konnte nicht erzeugt werden.")
    try:
        _populate_vectorworks_worksheet(
            ws, rows, group_titles, analysis, catalog,
            visible_columns=visible_columns, show_audit=show_audit)
        if show:
            show_vectorworks_worksheet(ws)
        return ws
    except Exception as error:
        _delete_incomplete_worksheet(ws, error)
        raise


def _populate_vectorworks_worksheet(
        ws, rows, group_titles, analysis, catalog=None,
        visible_columns=None, show_audit=True):
    """Populate a new or existing worksheet without changing its handle."""

    visible_columns = normalize_visible_columns(visible_columns)
    visible_indices = visible_column_indices(visible_columns)
    main_column_count = len(visible_columns)
    total_column_count = (
        max(main_column_count, len(AUDIT_HEADERS))
        if show_audit else main_column_count)
    records = report_records(rows, group_titles, catalog)
    audit_values = _audit_values(analysis) if show_audit else ()
    # Main header + report records + blank separator + audit title + audit
    # header + at least one audit information row.
    total_rows = (
        4 + len(records) + len(audit_values)
        if show_audit else 1 + len(records))
    have_original_recalc = False
    restore_state = True
    try:
        original_recalc = _ws_call("GetWSAutoRecalcState", ws)
        restore_state = (
            bool(original_recalc) if original_recalc is not None else True)
        have_original_recalc = True
        try:
            _ws_call("SetWSAutoRecalcState", ws, False)
            _resize_and_clear_worksheet(
                ws, total_rows, total_column_count)
            for column, value in enumerate(visible_columns, 1):
                _set_cell(ws, 1, column, value)
            _set_bold(ws, 1, main_column_count)
            _ws_call(
                "SetWSCellAlignment", ws, 1, 1, 1,
                main_column_count, 2)
            _ws_call("SetWSRowHeight", ws, 1, 1, 24, False, False)

            row_number = 2
            for record in records:
                if record["kind"] == "group":
                    group_column = (
                        visible_columns.index("Gruppe") + 1
                        if "Gruppe" in visible_columns else 1)
                    _set_cell(ws, row_number, group_column, record["title"])
                    _set_bold(ws, row_number, main_column_count)
                elif record["kind"] == "row":
                    quantity_row = record["row"]
                    for column, source_index in enumerate(
                            visible_indices, 1):
                        if source_index == 0:
                            _set_image_cell(
                                ws, row_number, column,
                                quantity_row.source_key)
                        else:
                            _set_cell(
                                ws, row_number, column,
                                record["values"][source_index])
                    _ws_call(
                        "SetWSRowHeight", ws,
                        row_number, row_number, 30, False, False)
                else:
                    totals = record["totals"]
                    values = (
                        "", "SUMME " + record["title"], "", "", "", "", "", "", "", "",
                        totals["raw_area"], totals["net_area"],
                        totals["raw_length"], totals["net_length"],
                        totals["raw_pieces"], totals["net_pieces"],
                        totals["groups"], totals["symbols"], "",
                    )
                    projected = list(project_values(
                        values, visible_columns))
                    if "Gruppe" not in visible_columns:
                        projected[0] = "SUMME " + record["title"]
                    for column, value in enumerate(projected, 1):
                        _set_cell(ws, row_number, column, value)
                    _set_bold(ws, row_number, main_column_count)
                row_number += 1

            if show_audit:
                # Leave row_number empty as a visual separator, then append
                # the duplicate-analysis audit only when explicitly enabled.
                audit_title_row = row_number + 1
                audit_header_row = row_number + 2
                _set_cell(
                    ws, audit_title_row, 1,
                    "PRÜFPROTOKOLL – KÜRZUNGEN UND WARNUNGEN",
                )
                _set_bold(ws, audit_title_row, len(AUDIT_HEADERS))
                _ws_call(
                    "SetWSRowHeight", ws,
                    audit_title_row, audit_title_row, 22, False, False)
                for column, value in enumerate(AUDIT_HEADERS, 1):
                    _set_cell(ws, audit_header_row, column, value)
                _set_bold(ws, audit_header_row, len(AUDIT_HEADERS))
                _ws_call(
                    "SetWSCellAlignment", ws,
                    audit_header_row, 1,
                    audit_header_row, len(AUDIT_HEADERS), 2,
                )

                for offset, values in enumerate(audit_values, 1):
                    audit_row = audit_header_row + offset
                    for column, value in enumerate(values, 1):
                        _set_cell(ws, audit_row, column, value)
                    if values[0] == "WARNUNG":
                        _set_bold(ws, audit_row, len(AUDIT_HEADERS))

            widths = list(project_widths(
                WORKSHEET_WIDTHS, visible_columns))
            if show_audit:
                audit_widths = (120, 220, 170, 260, 105, 105, 85, 260)
                while len(widths) < total_column_count:
                    widths.append(audit_widths[len(widths)])
            for column, width in enumerate(widths, 1):
                _ws_call("SetWSColumnWidth", ws, column, column, width)
            _ws_call(
                "SetWSCellWrapTextFlag", ws,
                1, 1, total_rows, total_column_count, True,
            )
        finally:
            # Restore before recalculation and before exposing the worksheet.
            _ws_call("SetWSAutoRecalcState", ws, restore_state)

        _ws_call("RecalculateWS", ws)
        return ws
    except Exception as error:
        # A second best-effort restoration covers failures raised by the first
        # restoration call itself. Never leave AutoRecalc intentionally off.
        restore_error = None
        if have_original_recalc:
            try:
                _ws_call("SetWSAutoRecalcState", ws, restore_state)
            except Exception as retry_error:
                restore_error = retry_error
        if restore_error is not None:
            raise RuntimeError(
                "Vectorworks-Autoberechnung konnte nach einem Fehler nicht "
                "wiederhergestellt werden: %s" % restore_error
            ) from error
        raise
