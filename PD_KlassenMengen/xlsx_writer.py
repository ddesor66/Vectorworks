# -*- coding: utf-8 -*-
"""Small dependency-free XLSX writer used by the Vectorworks plug-in.

The Vectorworks Python runtime deliberately receives no third-party package
dependency.  The writer implements the small OOXML subset needed for the
quantity report: values, formulas, styles, widths, frozen headers and filters.
"""

from __future__ import absolute_import

import datetime
import math
import os
import re
import tempfile
import zipfile
from xml.sax.saxutils import escape


STYLE_NORMAL = 0
STYLE_HEADER = 1
STYLE_GROUP = 2
STYLE_TOTAL = 3
STYLE_NUMBER = 4
STYLE_WARNING = 5
STYLE_INTEGER = 6
STYLE_TOTAL_INTEGER = 7


def styled(value, style=STYLE_NORMAL):
    """Return a cell value with an explicit style index."""
    return value, int(style)


def formula(expression, cached_value=0.0, style=STYLE_NUMBER):
    """Return a formula cell. ``expression`` may include or omit ``=``."""
    return {
        "formula": str(expression).lstrip("="),
        "value": cached_value,
        "style": int(style),
    }


def _column_name(index):
    result = ""
    number = int(index)
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _safe_sheet_name(name, used):
    text = re.sub(r"[\\/*?:\[\]]", "_", str(name or "Tabelle")).strip()
    text = (text or "Tabelle")[:31]
    candidate = text
    counter = 2
    while candidate.casefold() in used:
        suffix = " (%d)" % counter
        candidate = text[:31 - len(suffix)] + suffix
        counter += 1
    used.add(candidate.casefold())
    return candidate


def _cell_xml(row_index, column_index, item):
    style = STYLE_NORMAL
    value = item
    if isinstance(item, dict) and "formula" in item:
        style = int(item.get("style", STYLE_NUMBER))
        cached = item.get("value", 0.0)
        reference = "%s%d" % (_column_name(column_index), row_index)
        return (
            '<c r="%s" s="%d"><f>%s</f><v>%s</v></c>' % (
                reference,
                style,
                escape(str(item["formula"])),
                escape(str(cached)),
            )
        )
    if isinstance(item, tuple) and len(item) == 2:
        value, style = item
        style = int(style)
    reference = "%s%d" % (_column_name(column_index), row_index)
    if value is None:
        return '<c r="%s" s="%d"/>' % (reference, style)
    if isinstance(value, bool):
        return '<c r="%s" s="%d" t="b"><v>%d</v></c>' % (
            reference, style, 1 if value else 0)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            value = ""
        else:
            return '<c r="%s" s="%d"><v>%s</v></c>' % (
                reference, style, repr(value))
    text = str(value)
    preserve = ' xml:space="preserve"' if text != text.strip() else ""
    return '<c r="%s" s="%d" t="inlineStr"><is><t%s>%s</t></is></c>' % (
        reference, style, preserve, escape(text))


def _sheet_xml(rows, widths=None, freeze_rows=1, auto_filter=True):
    maximum_columns = max([len(row) for row in rows] or [1])
    maximum_rows = max(len(rows), 1)
    dimension = "A1:%s%d" % (_column_name(maximum_columns), maximum_rows)
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        '<dimension ref="%s"/>' % dimension,
    ]
    if freeze_rows:
        parts.append(
            '<sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="%d" topLeftCell="A%d" activePane="bottomLeft" state="frozen"/>'
            '</sheetView></sheetViews>' % (freeze_rows, freeze_rows + 1)
        )
    else:
        parts.append('<sheetViews><sheetView workbookViewId="0"/></sheetViews>')
    parts.append('<sheetFormatPr defaultRowHeight="15"/>')
    if widths:
        parts.append('<cols>')
        for index, width in enumerate(widths, 1):
            width_value = max(3.0, min(float(width), 80.0))
            parts.append(
                '<col min="%d" max="%d" width="%.2f" customWidth="1"/>' %
                (index, index, width_value)
            )
        parts.append('</cols>')
    parts.append('<sheetData>')
    for row_index, row in enumerate(rows, 1):
        parts.append('<row r="%d">' % row_index)
        for column_index, item in enumerate(row, 1):
            parts.append(_cell_xml(row_index, column_index, item))
        parts.append('</row>')
    parts.append('</sheetData>')
    if auto_filter and rows and maximum_columns:
        parts.append('<autoFilter ref="A1:%s%d"/>' % (
            _column_name(maximum_columns), maximum_rows))
    parts.append('<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.2" footer="0.2"/>')
    parts.append('</worksheet>')
    return "".join(parts)


def _styles_xml():
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
 <fonts count="4">
  <font><sz val="10"/><name val="Arial"/><family val="2"/></font>
  <font><b/><color rgb="FFFFFFFF"/><sz val="10"/><name val="Arial"/><family val="2"/></font>
  <font><b/><sz val="10"/><name val="Arial"/><family val="2"/></font>
  <font><color rgb="FF9C0006"/><sz val="10"/><name val="Arial"/><family val="2"/></font>
 </fonts>
 <fills count="5">
  <fill><patternFill patternType="none"/></fill>
  <fill><patternFill patternType="gray125"/></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FF3D4A57"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FFD9EAD3"/><bgColor indexed="64"/></patternFill></fill>
  <fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/><bgColor indexed="64"/></patternFill></fill>
 </fills>
 <borders count="2">
  <border><left/><right/><top/><bottom/><diagonal/></border>
  <border><left style="thin"><color rgb="FFB7B7B7"/></left><right style="thin"><color rgb="FFB7B7B7"/></right><top style="thin"><color rgb="FFB7B7B7"/></top><bottom style="thin"><color rgb="FFB7B7B7"/></bottom><diagonal/></border>
 </borders>
 <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
 <cellXfs count="8">
  <xf numFmtId="0" fontId="0" fillId="0" borderId="1" xfId="0" applyBorder="1"/>
  <xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
  <xf numFmtId="0" fontId="2" fillId="3" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
  <xf numFmtId="0" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1"/>
  <xf numFmtId="4" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
  <xf numFmtId="0" fontId="3" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1"/>
  <xf numFmtId="1" fontId="0" fillId="0" borderId="1" xfId="0" applyNumberFormat="1" applyBorder="1"/>
  <xf numFmtId="1" fontId="2" fillId="0" borderId="1" xfId="0" applyFont="1" applyNumberFormat="1" applyBorder="1"/>
 </cellXfs>
 <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def write_xlsx(path, sheets, creator="plan ° D Ingenieure"):
    """Write an XLSX file atomically.

    ``sheets`` is an iterable of dictionaries with ``name``, ``rows`` and
    optional ``widths``, ``freeze_rows`` and ``auto_filter`` values.
    """
    sheet_specs = list(sheets)
    if not sheet_specs:
        raise ValueError("Mindestens ein Tabellenblatt ist erforderlich.")
    destination = os.path.abspath(path)
    target_directory = os.path.dirname(destination)
    if target_directory and not os.path.isdir(target_directory):
        os.makedirs(target_directory)
    used = set()
    names = [_safe_sheet_name(spec.get("name"), used) for spec in sheet_specs]
    timestamp = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    workbook_sheets = []
    workbook_rels = []
    content_overrides = []
    for index, name in enumerate(names, 1):
        workbook_sheets.append(
            '<sheet name="%s" sheetId="%d" r:id="rId%d"/>' %
            (escape(name), index, index)
        )
        workbook_rels.append(
            '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet%d.xml"/>' %
            (index, index)
        )
        content_overrides.append(
            '<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % index
        )
    workbook_rels.append(
        '<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>' %
        (len(names) + 1)
    )
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="xml" ContentType="application/xml"/>
 <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
 <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
 <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
 <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
 %s
</Types>""" % "".join(content_overrides)
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
 <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
 <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""
    workbook = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>%s</sheets></workbook>""" % "".join(workbook_sheets)
    workbook_relationships = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>""" % "".join(workbook_rels)
    core = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:creator>%s</dc:creator><cp:lastModifiedBy>%s</cp:lastModifiedBy><dcterms:created xsi:type="dcterms:W3CDTF">%s</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">%s</dcterms:modified></cp:coreProperties>""" % (
        escape(creator), escape(creator), timestamp, timestamp)
    app = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"><Application>PD Klassen- und Mengentools</Application></Properties>"""

    file_descriptor, temporary = tempfile.mkstemp(
        prefix="pd_km_", suffix=".xlsx", dir=target_directory or None)
    os.close(file_descriptor)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
            def put(name, text):
                archive.writestr(name, text.encode("utf-8"))

            put("[Content_Types].xml", content_types)
            put("_rels/.rels", root_rels)
            put("docProps/core.xml", core)
            put("docProps/app.xml", app)
            put("xl/workbook.xml", workbook)
            put("xl/_rels/workbook.xml.rels", workbook_relationships)
            put("xl/styles.xml", _styles_xml())
            for index, spec in enumerate(sheet_specs, 1):
                put(
                    "xl/worksheets/sheet%d.xml" % index,
                    _sheet_xml(
                        list(spec.get("rows") or []),
                        spec.get("widths"),
                        int(spec.get("freeze_rows", 1)),
                        bool(spec.get("auto_filter", True)),
                    ),
                )
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return destination
