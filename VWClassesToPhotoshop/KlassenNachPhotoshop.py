# -*- coding: utf-8 -*-
"""Vectorworks 2026: Klassen eines Ansichtsbereichs an Photoshop uebergeben."""

from __future__ import print_function

import codecs
import datetime
import glob
import json
import os
import re
import subprocess

try:
    import vs
except ImportError:  # Erlaubt Logiktests ausserhalb von Vectorworks.
    vs = None


PLUGIN_VERSION = "1.3.7"
MANUFACTURER = "manufactured by Dirk D."

SETTINGS_SCHEMA_VERSION = 2
SETTINGS_FILE_NAME = "PD_Klassen_nach_Photoshop.json"

DEFAULT_IMAGE_FORMAT = "PNG"
DEFAULT_DPI = 150
DEFAULT_KEEP_IMAGES = True

CANVAS_SIZE_TOLERANCE_PIXELS = 8

TYPE_VIEWPORT = 122
TYPE_GROUP = 11
TYPE_SYMBOL_INSTANCE = 15
TYPE_SYMBOL_DEFINITION = 16

LAYER_TYPE = 154
LAYER_PRINT_DPI = 155
LAYER_REPAGINATE = 156
LAYER_SHEET_WIDTH = 165
LAYER_SHEET_HEIGHT = 166
LAYER_PAGE_WIDTH = 167
LAYER_PAGE_HEIGHT = 168
SHEET_LAYER_TYPE = 2

VP_NEEDS_UPDATE = 1004

VP_CLASS_VISIBLE = 0
VP_CLASS_HIDDEN = -1

SETUP_EVENT = 12255
DIALOG_OK = 1


def _dialog_title(title):
    return "%s | v%s | %s" % (str(title), PLUGIN_VERSION, MANUFACTURER)

WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


class ExportError(RuntimeError):
    pass


def safe_filename_component(value, fallback="Klasse", max_length=90):
    """Return a Windows-safe, stable file-name component."""
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value))
    text = re.sub(r"\s+", " ", text).strip(" .")
    if not text:
        text = fallback
    if text.upper() in WINDOWS_RESERVED_NAMES:
        text = "_" + text
    return text[:max_length].rstrip(" .") or fallback


def unique_numbered_stems(names):
    """Create deterministic file stems; the numeric prefix also preserves order."""
    used = set()
    result = []
    width = max(3, len(str(max(1, len(names)))))
    for index, name in enumerate(names, 1):
        base = safe_filename_component(name)
        candidate = ("{0:0%dd}_{1}" % width).format(index, base)
        suffix = 2
        while candidate.casefold() in used:
            candidate = ("{0:0%dd}_{1}_{2}" % width).format(index, base, suffix)
            suffix += 1
        used.add(candidate.casefold())
        result.append(candidate)
    return result


def class_names(api):
    result = []
    for index in range(1, int(api.ClassNum()) + 1):
        name = api.ClassList(index)
        if name:
            result.append(name)
    return result


def find_none_class(names):
    """Find the localized default container class (None/Keine)."""
    by_folded = {name.casefold(): name for name in names}
    for candidate in ("keine", "none"):
        if candidate in by_folded:
            return by_folded[candidate]
    return names[0] if names else None


def visible_class_names(api, viewport, names):
    return [name for name, _state in displayed_class_states(api, viewport, names)]


def displayed_class_states(api, viewport, names):
    """Return displayed classes and preserve normal/gray viewport visibility."""
    result = []
    for name in names:
        ok, visibility = api.GetVPClassVisibility(viewport, name)
        if ok and visibility != VP_CLASS_HIDDEN:
            result.append((name, int(visibility)))
    return result


def occupied_drawing_class_names(api):
    """Return classes used by placed drawing objects and their live contents.

    Vectorworks' class list also contains empty classes and classes that occur
    only in unused symbol definitions.  Those must not create empty Photoshop
    layers.  Traversing ``ALL`` with ``INOBJECT``/``INVIEWPORT`` collects
    placed geometry, plug-in contents and viewport annotations.  Symbol
    definitions are followed only from symbol instances that are actually
    placed, so an unused library symbol cannot mark a class as occupied.
    """
    occupied = set()
    visited_handles = set()
    visited_symbol_definitions = set()

    def marker(handle):
        try:
            return int(handle)
        except (TypeError, ValueError):
            return str(handle)

    def visit_symbol_definition(definition):
        if not definition:
            return
        definition_marker = marker(definition)
        if definition_marker in visited_symbol_definitions:
            return
        visited_symbol_definitions.add(definition_marker)
        child = api.FInSymDef(definition)
        while child:
            visit(child)
            child = api.NextObj(child)

    def visit(handle):
        if not handle:
            return
        handle_marker = marker(handle)
        if handle_marker in visited_handles:
            return
        visited_handles.add(handle_marker)

        class_name = str(api.GetClass(handle) or "").strip()
        if class_name:
            occupied.add(class_name)

        object_type = int(api.GetTypeN(handle) or 0)
        if object_type == TYPE_GROUP:
            child = api.FInGroup(handle)
            while child:
                visit(child)
                child = api.NextObj(child)
        elif object_type == TYPE_SYMBOL_INSTANCE:
            symbol_name = str(api.GetSymName(handle) or "").strip()
            definition = api.GetObject(symbol_name) if symbol_name else None
            if (definition and
                    int(api.GetTypeN(definition) or 0) == TYPE_SYMBOL_DEFINITION):
                visit_symbol_definition(definition)

    api.ForEachObject(visit, "(ALL & INOBJECT & INVIEWPORT)")
    return occupied


def occupied_displayed_class_states(api, viewport, names):
    """Filter displayed viewport classes before any export files are made."""
    displayed = displayed_class_states(api, viewport, names)
    occupied = occupied_drawing_class_names(api)
    return [item for item in displayed if item[0] in occupied]


def unique_temp_layer_name(api):
    """Return an unused, human-recognizable temporary sheet-layer name."""
    base = "_VW Photoshop Export"
    candidate = base
    suffix = 2
    while api.GetLayerByName(candidate):
        candidate = "{0} {1}".format(base, suffix)
        suffix += 1
    return candidate


def bounds_size(bounds):
    left, top, right, bottom = bounds
    return right - left, bottom - top


def centering_offset(bounds):
    """Return the offset that moves a box center to the sheet origin."""
    left, top, right, bottom = bounds
    return -((left + right) / 2.0), -((top + bottom) / 2.0)


def viewport_page_size_inches(api, bounds):
    """Convert viewport dimensions from document units to page inches."""
    units = api.GetUnits()
    if not isinstance(units, (tuple, list)) or len(units) < 4:
        raise ExportError("Vectorworks hat keine gueltigen Dokumenteinheiten geliefert.")
    units_per_inch = float(units[3])
    if units_per_inch <= 0:
        raise ExportError("Die Dokumenteinheit kann nicht in Zoll umgerechnet werden.")
    width, height = bounds_size(bounds)
    return width / units_per_inch, height / units_per_inch


def create_export_sheet(api, dpi, page_size_inches):
    """Create a single-page sheet matching the selected viewport exactly."""
    previous_layer = api.ActLayer()
    previous_name = api.GetLName(previous_layer) if previous_layer else ""
    name = unique_temp_layer_name(api)
    layer = api.CreateLayer(name, SHEET_LAYER_TYPE)
    if not layer:
        raise ExportError("Die temporaere Export-Layoutebene konnte nicht angelegt werden.")

    try:
        api.SetObjectVariableInt(layer, LAYER_PRINT_DPI, int(dpi))
        actual_dpi = int(api.GetObjectVariableInt(layer, LAYER_PRINT_DPI))
        if actual_dpi != int(dpi):
            raise ExportError(
                "Vectorworks hat die angeforderte Aufloesung nicht uebernommen "
                "({0} statt {1} dpi).".format(actual_dpi, dpi)
            )
        width, height = page_size_inches
        if width <= 0 or height <= 0:
            raise ExportError("Der Ansichtsbereich hat keine gueltige Seitengroesse.")
        # SetDrawingRect is the documented page-setup command and operates on
        # the active layer.  Merely writing the layer object variables before
        # activating the new sheet leaves the current printer page (often A4)
        # in place in Vectorworks 2026.
        api.Layer(name)
        api.SetDrawingRect(float(width), float(height))
        requested = {
            LAYER_SHEET_WIDTH: float(width),
            LAYER_SHEET_HEIGHT: float(height),
            LAYER_PAGE_WIDTH: float(width),
            LAYER_PAGE_HEIGHT: float(height),
        }
        for selector, value in requested.items():
            api.SetObjectVariableReal(layer, selector, value)
        api.SetObjectVariableBoolean(layer, LAYER_REPAGINATE, True)
        actual_width, actual_height = api.TBB_GetPageArea(layer)
        actual_width = float(actual_width)
        actual_height = float(actual_height)
        tolerance = 0.01  # PDF pages are ultimately quantized to points.
        if (abs(actual_width - width) > tolerance or
                abs(actual_height - height) > tolerance):
            raise ExportError(
                "Vectorworks hat die Ansichtsbereichsgroesse nicht als "
                "PDF-Seitengroesse uebernommen: {0:.4f} x {1:.4f} Zoll "
                "statt {2:.4f} x {3:.4f} Zoll.".format(
                    actual_width, actual_height, width, height
                )
            )
        return {
            "layer": layer,
            "name": name,
            "previous_layer": previous_layer,
            "previous_name": previous_name,
            "dpi": actual_dpi,
        }
    except Exception:
        if previous_name:
            api.Layer(previous_name)
        api.DelObject(layer)
        raise


def viewport_export_bounds(api, viewport):
    """Return a normalized, non-empty screen-plane box for the viewport."""
    p1, p2 = api.GetBBox(viewport)
    left = min(float(p1[0]), float(p2[0]))
    right = max(float(p1[0]), float(p2[0]))
    top = min(float(p1[1]), float(p2[1]))
    bottom = max(float(p1[1]), float(p2[1]))
    if right - left <= 0 or bottom - top <= 0:
        raise ExportError("Der ausgewaehlte Ansichtsbereich hat keine gueltige Begrenzung.")
    return left, top, right, bottom


def cleanup_export_sheet(api, context, source_viewport):
    """Restore the drawing state and remove the isolated export sheet layer."""
    api.DSelectAll()
    previous_name = context.get("previous_name", "") if context else ""
    if previous_name:
        api.Layer(previous_name)
    layer = context.get("layer") if context else None
    if layer:
        api.DelObject(layer)
    if is_handle(api, source_viewport):
        api.SetSelect(source_viewport)
    api.ReDrawAll()


def apply_class_visibility(api, viewport, names, target, target_state=VP_CLASS_VISIBLE):
    """Make only the target class visible, preserving its normal/gray state."""
    failures = []
    for name in names:
        state = target_state if name == target else VP_CLASS_HIDDEN
        if not api.SetVPClassVisibility(viewport, name, state):
            failures.append(name)
    return failures


def is_handle(api, handle):
    if not handle:
        return False
    try:
        return int(api.GetTypeN(handle)) != 0
    except Exception:
        return False


def pdf_document_name(output_path):
    """Return the extension-free name expected by OpenPDFDocument."""
    absolute_path = os.path.abspath(output_path)
    run_name = safe_filename_component(
        os.path.basename(os.path.dirname(absolute_path)), "VWPS", 60
    )
    file_name = os.path.basename(absolute_path)
    stem = file_name[:-4] if file_name.casefold().endswith(".pdf") else file_name
    return safe_filename_component(run_name + "_" + stem, "VWPS", 150)


def collect_pdf_output(output_path, document_name, pdf_export_directory):
    """Move Vectorworks' folder-based PDF output into the run directory."""
    destination = os.path.abspath(output_path)
    search_directories = [os.path.dirname(destination), pdf_export_directory]
    seen = set()
    candidates = []
    for directory in search_directories:
        if not directory:
            continue
        directory = os.path.abspath(directory)
        folded = os.path.normcase(directory)
        if folded in seen:
            continue
        seen.add(folded)
        candidates.extend([
            os.path.join(directory, document_name + ".pdf"),
            os.path.join(directory, document_name),
        ])

    source = next((path for path in candidates if os.path.isfile(path)), None)
    if source is None:
        raise ExportError(
            "Vectorworks hat das temporaere PDF nicht unter dem erwarteten Namen "
            "'{0}.pdf' angelegt. PDF-Zielordner: {1}".format(
                document_name, pdf_export_directory or "unbekannt"
            )
        )
    if os.path.normcase(source) != os.path.normcase(destination):
        os.replace(source, destination)
    if not os.path.isfile(destination) or os.path.getsize(destination) <= 0:
        raise ExportError("Das temporaere PDF ist leer oder nicht lesbar.")


def selected_viewports(api):
    found = []

    def remember(handle):
        found.append(handle)

    api.ForEachObject(remember, "((SEL=TRUE) & (T=VIEWPORT))")
    return found


def export_class_pdf(api, source_viewport, export_layer, all_classes,
                     target_class, target_state, source_bounds, output_path,
                     pdf_export_directory):
    """Center one isolated viewport on its exactly matching PDF page."""
    duplicate = api.CreateDuplicateObject(source_viewport, export_layer)
    pdf_open = False
    if not duplicate:
        raise ExportError("Der Ansichtsbereich konnte nicht dupliziert werden.")

    try:
        failures = apply_class_visibility(
            api, duplicate, all_classes, target_class, target_state
        )
        if failures:
            raise ExportError(
                "Klassensichtbarkeit konnte nicht gesetzt werden: " + ", ".join(failures[:5])
            )

        api.SetObjectVariableBoolean(duplicate, VP_NEEDS_UPDATE, True)
        api.ReDrawAll()
        offset_x, offset_y = centering_offset(source_bounds)
        api.HMove(duplicate, offset_x, offset_y)
        api.ReDrawAll()

        api.DSelectAll()
        api.SetSelect(duplicate)
        document_name = pdf_document_name(output_path)
        if not api.OpenPDFDocument(document_name):
            raise ExportError("Vectorworks konnte das temporaere PDF nicht oeffnen.")
        pdf_open = True
        api.ExportPDFPages(api.GetLName(export_layer) or "")
        api.ClosePDFDocument()
        pdf_open = False
        collect_pdf_output(output_path, document_name, pdf_export_directory)
        return None
    finally:
        if pdf_open:
            api.ClosePDFDocument()
        if duplicate != source_viewport and is_handle(api, duplicate):
            api.DelObject(duplicate)
        api.DSelectAll()
        api.ReDrawAll()


def jsx_file_literal(path):
    return os.path.abspath(path).replace("\\", "/")


def build_photoshop_jsx(manifest):
    """Build an ASCII-only ExtendScript for Photoshop 2018+ and 2023+."""
    payload = json.dumps(manifest, ensure_ascii=True, separators=(",", ":"))
    return r'''#target photoshop
app.bringToFront();
app.displayDialogs = DialogModes.NO;

(function () {
    var manifest = __MANIFEST__;
    var master = null;
    var firstWidth = null;
    var firstHeight = null;

    function removeIfPresent(path) {
        var file = new File(path);
        if (file.exists) { file.remove(); }
    }

    function pixelSize(document) {
        return {
            width: Math.round(document.width.as("px")),
            height: Math.round(document.height.as("px"))
        };
    }

    function normalizeCanvas(document, width, height, tolerance, className) {
        var size = pixelSize(document);
        var differenceX = Math.abs(size.width - width);
        var differenceY = Math.abs(size.height - height);
        if (differenceX > tolerance || differenceY > tolerance) {
            throw new Error(
                "Die PDF-Seitengroesse unterscheidet sich bei Klasse " + className +
                " zu stark: " + size.width + " x " + size.height +
                " Pixel statt " + width + " x " + height + " Pixel."
            );
        }
        if (size.width !== width || size.height !== height) {
            document.resizeCanvas(
                UnitValue(width, "px"), UnitValue(height, "px"),
                AnchorPosition.TOPLEFT
            );
        }
    }

    try {
        for (var i = 0; i < manifest.entries.length; i++) {
            var entry = manifest.entries[i];
            var sourceFile = new File(entry.pdf);
            if (!sourceFile.exists) {
                throw new Error("Quelldatei fehlt: " + entry.pdf);
            }

            var pdfOptions = new PDFOpenOptions();
            pdfOptions.antiAlias = true;
            pdfOptions.bitsPerChannel = BitsPerChannelType.EIGHT;
            pdfOptions.cropPage = CropToType.MEDIABOX;
            pdfOptions.mode = OpenDocumentMode.RGB;
            pdfOptions.page = 1;
            pdfOptions.resolution = manifest.dpi;
            pdfOptions.suppressWarnings = true;
            pdfOptions.usePageNumber = true;
            var source = app.open(sourceFile, pdfOptions);

            var sourceSize = pixelSize(source);
            if (firstWidth === null) {
                firstWidth = sourceSize.width;
                firstHeight = sourceSize.height;
            } else {
                normalizeCanvas(
                    source, firstWidth, firstHeight,
                    Number(manifest.canvasTolerancePixels || 0), entry.name
                );
            }

            if (manifest.format === "JPG") {
                var jpegOptions = new JPEGSaveOptions();
                jpegOptions.quality = 12;
                jpegOptions.embedColorProfile = true;
                source.saveAs(new File(entry.jpg), jpegOptions, true, Extension.LOWERCASE);
                source.close(SaveOptions.DONOTSAVECHANGES);
                source = app.open(new File(entry.jpg));
                source.resizeImage(undefined, undefined, manifest.dpi, ResampleMethod.NONE);
            } else if (manifest.keepImages) {
                var pngOptions = new PNGSaveOptions();
                source.saveAs(new File(entry.png), pngOptions, true, Extension.LOWERCASE);
            }

            if (master === null) {
                master = source;
                master.activeLayer.name = entry.name;
            } else {
                app.activeDocument = source;
                var sourceBounds = source.activeLayer.bounds;
                var sourceLeft = sourceBounds[0].as("px");
                var sourceTop = sourceBounds[1].as("px");
                source.selection.selectAll();
                source.selection.copy();
                app.activeDocument = master;
                var placed = master.paste();
                var placedBounds = placed.bounds;
                placed.translate(
                    UnitValue(sourceLeft - placedBounds[0].as("px"), "px"),
                    UnitValue(sourceTop - placedBounds[1].as("px"), "px")
                );
                placed.name = entry.name;
                if (manifest.format === "JPG") {
                    placed.blendMode = BlendMode.MULTIPLY;
                }
                app.activeDocument = source;
                source.close(SaveOptions.DONOTSAVECHANGES);
                app.activeDocument = master;
            }
        }

        if (master === null) { throw new Error("Keine Bilder zur Uebergabe vorhanden."); }
        var psdOptions = new PhotoshopSaveOptions();
        psdOptions.layers = true;
        psdOptions.embedColorProfile = true;
        app.activeDocument = master;
        master.saveAs(new File(manifest.psd), psdOptions, false, Extension.LOWERCASE);

        for (var j = 0; j < manifest.entries.length; j++) {
            removeIfPresent(manifest.entries[j].pdf);
            if (!manifest.keepImages) {
                removeIfPresent(manifest.entries[j].png);
                removeIfPresent(manifest.entries[j].jpg);
            }
        }
        if (!manifest.quiet) {
            alert("Photoshop-Uebergabe abgeschlossen.\n" + manifest.psd);
        }
    } catch (error) {
        alert("Photoshop-Uebergabe fehlgeschlagen:\n" + error.message);
        throw error;
    } finally {
        app.displayDialogs = DialogModes.ALL;
    }
}());
'''.replace("__MANIFEST__", payload)


def write_utf8(path, text):
    with codecs.open(path, "w", "utf-8") as stream:
        stream.write(text)


def photoshop_candidates():
    candidates = []
    try:
        import winreg
        roots = (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE)
        keys = (
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\Photoshop.exe",
        )
        for root in roots:
            for key_name in keys:
                try:
                    with winreg.OpenKey(root, key_name) as key:
                        candidates.append(winreg.QueryValueEx(key, None)[0])
                except OSError:
                    pass
    except (ImportError, AttributeError):
        pass

    for env_name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if base:
            pattern = os.path.join(base, "Adobe", "Adobe Photoshop *", "Photoshop.exe")
            candidates.extend(glob.glob(pattern))

    unique = []
    seen = set()
    for path in candidates:
        normalized = os.path.normcase(os.path.abspath(str(path).strip('"')))
        if normalized not in seen and os.path.isfile(normalized):
            seen.add(normalized)
            unique.append(normalized)
    return unique


def photoshop_version_score(path):
    # Never interpret "Program Files (x86)" as Photoshop version 2086.
    parts = re.split(r"[\\/]", str(path))
    product = " ".join(part for part in parts
                       if "photoshop" in part.casefold() and not part.lower().endswith(".exe"))
    numbers = [int(value) for value in re.findall(r"(?<!\d)(20\d{2}|\d{2})(?!\d)", product)]
    version = max(numbers) if numbers else 0
    if 0 < version < 100:
        version += 2000
    try:
        modified = int(os.path.getmtime(path))
    except OSError:
        modified = 0
    return version, modified


def find_photoshop():
    candidates = photoshop_candidates()
    return max(candidates, key=photoshop_version_score) if candidates else None


def build_manifest(class_list, pdf_paths, output_directory, image_format, dpi,
                   keep_images, quiet=False):
    entries = []
    for class_name, pdf_path in zip(class_list, pdf_paths):
        stem = os.path.splitext(pdf_path)[0]
        entries.append({
            "name": class_name[:255],
            "pdf": jsx_file_literal(pdf_path),
            "png": jsx_file_literal(stem + ".png"),
            "jpg": jsx_file_literal(stem + ".jpg"),
        })
    return {
        "version": PLUGIN_VERSION,
        "format": image_format,
        "dpi": int(dpi),
        "canvasTolerancePixels": CANVAS_SIZE_TOLERANCE_PIXELS,
        "keepImages": bool(keep_images),
        "quiet": bool(quiet),
        "psd": jsx_file_literal(os.path.join(output_directory, "Klassen_komplett.psd")),
        "entries": entries,
    }


def settings_file_path(environ=None):
    """Return the user-specific settings path outside the installed plug-in."""
    environment = os.environ if environ is None else environ
    appdata = environment.get("APPDATA", "")
    if not appdata:
        return ""
    return os.path.join(
        appdata, "Nemetschek", "Vectorworks", "2026", "Settings",
        SETTINGS_FILE_NAME,
    )


def default_settings():
    return {
        "last_output_directory": "",
        "format": DEFAULT_IMAGE_FORMAT,
        "dpi": DEFAULT_DPI,
        "keep_images": DEFAULT_KEEP_IMAGES,
        "one_click_ready": False,
        "pdf_configured": False,
    }


def load_settings(environ=None):
    """Load and validate user settings; schema 1 is migrated safely."""
    result = default_settings()
    path = settings_file_path(environ)
    if not path:
        return result
    try:
        with codecs.open(path, "r", "utf-8") as stream:
            data = json.load(stream)
        schema = int(data.get("schema", 0))
        if schema not in (1, SETTINGS_SCHEMA_VERSION):
            return result

        directory = data.get("lastOutputDirectory", "")
        if isinstance(directory, str) and os.path.isdir(directory):
            result["last_output_directory"] = os.path.abspath(directory)

        if schema == SETTINGS_SCHEMA_VERSION:
            image_format = str(data.get("imageFormat", "")).upper()
            if image_format in ("PNG", "JPG"):
                result["format"] = image_format
            try:
                dpi = int(data.get("dpi", DEFAULT_DPI))
            except (TypeError, ValueError):
                dpi = DEFAULT_DPI
            if dpi in (72, 150, 300, 600):
                result["dpi"] = dpi
            result["keep_images"] = bool(
                data.get("keepImages", DEFAULT_KEEP_IMAGES))
            result["one_click_ready"] = bool(data.get("oneClickReady", False))
            result["pdf_configured"] = bool(data.get("pdfConfigured", False))

        if not result["last_output_directory"]:
            result["one_click_ready"] = False
            result["pdf_configured"] = False
    except (IOError, OSError, TypeError, ValueError):
        return default_settings()
    return result


def load_last_output_directory(environ=None):
    """Compatibility wrapper used by older tests and integrations."""
    return load_settings(environ)["last_output_directory"]


def save_settings(directory, settings, pdf_configured, environ=None):
    """Persist complete one-click settings atomically outside the plug-in."""
    path = settings_file_path(environ)
    if not path or not os.path.isdir(directory):
        return False
    image_format = str(settings.get("format", DEFAULT_IMAGE_FORMAT)).upper()
    if image_format not in ("PNG", "JPG"):
        return False
    try:
        dpi = int(settings.get("dpi", DEFAULT_DPI))
    except (TypeError, ValueError):
        return False
    if dpi not in (72, 150, 300, 600):
        return False

    settings_directory = os.path.dirname(path)
    temporary = path + ".tmp"
    try:
        if not os.path.isdir(settings_directory):
            os.makedirs(settings_directory)
        payload = {
            "schema": SETTINGS_SCHEMA_VERSION,
            "lastOutputDirectory": os.path.abspath(directory),
            "imageFormat": image_format,
            "dpi": dpi,
            "keepImages": bool(settings.get("keep_images", True)),
            "oneClickReady": True,
            "pdfConfigured": bool(pdf_configured),
        }
        with codecs.open(temporary, "w", "utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
        return True
    except (IOError, OSError, TypeError, ValueError):
        try:
            if os.path.isfile(temporary):
                os.remove(temporary)
        except OSError:
            pass
        return False


def save_last_output_directory(directory, environ=None):
    """Compatibility wrapper preserving the legacy setup state."""
    return save_settings(
        directory, default_settings(), False, environ=environ)


def shift_requests_setup(api):
    """Holding Shift while invoking the command reopens setup."""
    try:
        _option, _command, shift = api.GetModifierFlags()
        return bool(shift)
    except (AttributeError, TypeError, ValueError):
        return False


def can_run_one_click(settings, force_setup=False):
    return bool(
        not force_setup
        and settings.get("one_click_ready")
        and settings.get("pdf_configured")
        and settings.get("last_output_directory")
        and os.path.isdir(settings.get("last_output_directory", ""))
    )


def resolve_output_directory(api, choose_new, last_directory):
    """Reuse a valid remembered folder unless the user requests another one."""
    if not choose_new and last_directory and os.path.isdir(last_directory):
        return os.path.abspath(last_directory)
    _folder_status, directory = api.GetFolder(
        "Zielordner fuer Photoshop-Uebergabe waehlen"
    )
    if not directory:
        return ""
    return os.path.abspath(directory)


def compact_directory_label(directory, max_length=88):
    if not directory:
        return "Letzter Zielordner: noch nicht festgelegt"
    prefix = "Letzter Zielordner: "
    available = max(12, max_length - len(prefix))
    text = directory
    if len(text) > available:
        text = "..." + text[-(available - 3):]
    return prefix + text


def settings_dialog(api, visible_count, last_directory="", saved_settings=None):
    ids = {
        "format_label": 4, "format": 5,
        "resolution_label": 6, "resolution": 7,
        "keep": 8, "note": 9,
        "directory": 10, "choose_directory": 11, "pdf_note": 12,
        "one_click_note": 13,
        "title": 14, "source_note": 15, "output_title": 16,
    }
    dialog = api.CreateLayout(
        _dialog_title("PD Photoshop-Übergabe"), False,
        "Exportieren", "Abbrechen"
    )
    api.CreateStyledStatic(
        dialog, ids["title"],
        "PHOTOSHOP-ÜBERGABE  |  Sichtbare Klassen als Ebenen", -1, 213)
    api.CreateStaticText(
        dialog, ids["source_note"],
        "1. Vor dem Start genau einen Ansichtsbereich auswählen. "
        "2. Format und Auflösung festlegen. 3. Exportieren. Berücksichtigt "
        "werden nur sichtbare Klassen mit Zeichnungselementen.", 72)
    api.CreateStyledStatic(
        dialog, ids["output_title"], "AUSGABE", -1, 211)
    api.CreateStaticText(
        dialog, ids["format_label"], "Bildformat:", 24)
    api.CreatePullDownMenu(dialog, ids["format"], 24)

    api.CreateStaticText(
        dialog, ids["resolution_label"], "Auflösung:", 24)
    api.CreatePullDownMenu(dialog, ids["resolution"], 28)

    api.CreateCheckBox(dialog, ids["keep"], "Einzelbilder behalten")
    api.CreateStaticText(
        dialog, ids["note"],
        "Quelle erkannt: Der ausgewählte Ansichtsbereich enthält {0} "
        "sichtbare, belegte Klasse(n)."
        .format(visible_count),
        62,
    )
    api.CreateStaticText(
        dialog, ids["directory"], compact_directory_label(last_directory), 70)
    api.CreateCheckBox(
        dialog, ids["choose_directory"], "Anderen Zielordner auswählen")
    api.CreateStaticText(
        dialog, ids["pdf_note"],
        "Danach die Vectorworks-PDF-Einstellungen bestätigen und im "
        "PDF-Ordnerdialog denselben Zielordner verwenden.",
        70,
    )
    api.CreateStaticText(
        dialog, ids["one_click_note"],
        "Anschließend ist der Ein-Klick-Modus aktiv. Zum Ändern dieser "
        "Einstellungen beim Aufruf die Umschalttaste gedrückt halten.",
        70,
    )

    api.SetFirstLayoutItem(dialog, ids["title"])
    api.SetBelowItem(dialog, ids["title"], ids["source_note"], 0, 8)
    api.SetBelowItem(dialog, ids["source_note"], ids["output_title"], 0, 10)
    api.SetBelowItem(dialog, ids["output_title"], ids["format_label"], 0, 4)
    api.SetRightItem(dialog, ids["format_label"], ids["format"], 0, 0)
    api.SetBelowItem(dialog, ids["format_label"], ids["resolution_label"], 0, 8)
    api.SetRightItem(dialog, ids["resolution_label"], ids["resolution"], 0, 0)
    api.SetBelowItem(dialog, ids["resolution_label"], ids["keep"], 0, 10)
    api.SetBelowItem(dialog, ids["keep"], ids["note"], 0, 10)
    api.SetBelowItem(dialog, ids["note"], ids["directory"], 0, 8)
    api.SetBelowItem(dialog, ids["directory"], ids["choose_directory"], 0, 4)
    api.SetBelowItem(dialog, ids["choose_directory"], ids["pdf_note"], 0, 10)
    api.SetBelowItem(dialog, ids["pdf_note"], ids["one_click_note"], 0, 6)

    saved = default_settings() if saved_settings is None else saved_settings
    saved_format = str(saved.get("format", DEFAULT_IMAGE_FORMAT)).upper()
    saved_dpi = int(saved.get("dpi", DEFAULT_DPI))
    dpi_values = (72, 150, 300, 600)
    values = {
        "format": 1 if saved_format == "JPG" else 0,
        "resolution": dpi_values.index(saved_dpi) if saved_dpi in dpi_values else 1,
        "keep": bool(saved.get("keep_images", DEFAULT_KEEP_IMAGES)),
        "choose_directory": not bool(last_directory),
    }

    def handler(item, data):
        del data
        if item == SETUP_EVENT:
            # Vectorworks initialisiert Pull-down-Menüs erst mit dem Setup-
            # Ereignis zuverlässig. Vorher eingefügte Einträge erscheinen
            # in VW 2026 als leere, nicht bedienbare Auswahllisten.
            api.AddChoice(dialog, ids["format"], "PNG (empfohlen)", 0)
            api.AddChoice(dialog, ids["format"], "JPG (Qualitaet 12)", 1)
            api.AddChoice(dialog, ids["resolution"], "Entwurf - 72 dpi", 0)
            api.AddChoice(dialog, ids["resolution"], "Normal - 150 dpi", 1)
            api.AddChoice(dialog, ids["resolution"], "Hoch - 300 dpi", 2)
            api.AddChoice(
                dialog, ids["resolution"], "Sehr hoch - 600 dpi", 3)
            api.SelectChoice(dialog, ids["format"], values["format"], True)
            api.SelectChoice(dialog, ids["resolution"], values["resolution"], True)
            api.SetBooleanItem(dialog, ids["keep"], values["keep"])
            api.SetBooleanItem(
                dialog, ids["choose_directory"], values["choose_directory"])
        elif item == DIALOG_OK:
            values["format"] = api.GetSelectedChoiceIndex(dialog, ids["format"], 0)
            values["resolution"] = api.GetSelectedChoiceIndex(
                dialog, ids["resolution"], 0
            )
            values["keep"] = api.GetBooleanItem(dialog, ids["keep"])
            values["choose_directory"] = api.GetBooleanItem(
                dialog, ids["choose_directory"])

    if api.RunLayoutDialog(dialog, handler) != DIALOG_OK:
        return None
    return {
        "format": "JPG" if values["format"] == 1 else "PNG",
        "dpi": dpi_values[values["resolution"]],
        "keep_images": bool(values["keep"]),
        "choose_directory": bool(values["choose_directory"]),
    }


def make_run_directory(base_directory, document_name):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    document = safe_filename_component(document_name, "Vectorworks")
    path = os.path.join(base_directory, "VW_Klassen_{0}_{1}".format(document, timestamp))
    os.makedirs(path)
    return path


def write_report(path, source_name, image_format, dpi, exported, warnings, error=None):
    lines = [
        "VWClassesToPhotoshop {0}".format(PLUGIN_VERSION),
        "Quelle: {0}".format(source_name),
        "Bildformat: {0}".format(image_format),
        "Aufloesung: {0} dpi".format(dpi),
        "Exportierte Klassen: {0}".format(len(exported)),
    ]
    lines.extend("OK: " + name for name in exported)
    lines.extend("WARNUNG: " + warning for warning in warnings)
    if error:
        lines.append("FEHLER: " + error)
    write_utf8(path, "\n".join(lines) + "\n")


def main(api):
    viewports = selected_viewports(api)
    if len(viewports) != 1:
        api.AlrtDialog(
            "Bitte genau einen Ansichtsbereich auf einer Layoutebene auswaehlen."
        )
        return
    source = viewports[0]

    source_layer = api.GetLayer(source)
    if not source_layer or int(api.GetObjectVariableInt(source_layer, LAYER_TYPE)) != SHEET_LAYER_TYPE:
        api.AlrtDialog(
            "Bitte einen Ansichtsbereich auf einer Layoutebene auswaehlen."
        )
        return

    names = class_names(api)
    if not names:
        api.AlrtDialog("Das Dokument enthaelt keine Klassen.")
        return
    displayed_classes = displayed_class_states(api, source, names)
    if not displayed_classes:
        api.AlrtDialog("Im ausgewaehlten Ansichtsbereich sind keine Klassen sichtbar.")
        return
    displayed_classes = occupied_displayed_class_states(api, source, names)
    if not displayed_classes:
        api.AlrtDialog(
            "Die sichtbaren Klassen des ausgewaehlten Ansichtsbereichs "
            "enthalten keine Zeichnungselemente. Es wurde nichts exportiert."
        )
        return
    export_classes = [name for name, _state in displayed_classes]
    class_states = dict(displayed_classes)

    user_settings = load_settings()
    force_setup = shift_requests_setup(api)
    one_click = can_run_one_click(user_settings, force_setup)
    last_directory = user_settings["last_output_directory"]

    if one_click:
        settings = {
            "format": user_settings["format"],
            "dpi": user_settings["dpi"],
            "keep_images": user_settings["keep_images"],
            "choose_directory": False,
        }
        base_directory = last_directory
    else:
        settings = settings_dialog(
            api, len(export_classes), last_directory, user_settings)
        if settings is None:
            return
        base_directory = resolve_output_directory(
            api, settings["choose_directory"], last_directory
        )
        if not base_directory:
            return
        if not api.AcquireExportPDFSettingsAndLocation(True):
            return
        save_settings(base_directory, settings, True)

    source_name = api.GetFName() or "Vectorworks"
    run_directory = make_run_directory(
        base_directory, os.path.splitext(os.path.basename(source_name))[0]
    )
    stems = unique_numbered_stems(export_classes)
    pdf_paths = [os.path.join(run_directory, stem + ".pdf") for stem in stems]
    exported = []
    warnings = []
    export_context = None

    try:
        source_bounds = viewport_export_bounds(api, source)
        export_context = create_export_sheet(
            api, settings["dpi"],
            viewport_page_size_inches(api, source_bounds)
        )
        for index, (class_name, pdf_path) in enumerate(zip(export_classes, pdf_paths), 1):
            api.Message(
                "Photoshop-Uebergabe: {0}/{1} - {2}".format(
                    index, len(export_classes), class_name
                )
            )
            warning = export_class_pdf(
                api, source, export_context["layer"], names, class_name,
                class_states[class_name], source_bounds, pdf_path, base_directory
            )
            exported.append(class_name)
            if warning:
                warnings.append("{0}: {1}".format(class_name, warning))
    except Exception as error:
        error_text = "{0}: {1}".format(
            export_classes[len(exported)] if len(exported) < len(export_classes) else "Export",
            str(error),
        )
        if one_click:
            save_settings(base_directory, settings, False)
            error_text += (
                "\n\nDer Ein-Klick-Modus wurde vorsorglich zurueckgesetzt. "
                "Beim naechsten Aufruf werden die PDF-Einstellungen erneut abgefragt."
            )
        write_report(
            os.path.join(run_directory, "Exportbericht.txt"),
            source_name, settings["format"], settings["dpi"],
            exported, warnings, error_text,
        )
        api.AlrtDialog(
            "Die Uebergabe wurde abgebrochen.\n\n{0}\n\nBericht:\n{1}".format(
                error_text, os.path.join(run_directory, "Exportbericht.txt")
            )
        )
        return
    finally:
        if export_context is not None:
            cleanup_export_sheet(api, export_context, source)

    manifest = build_manifest(
        export_classes, pdf_paths, run_directory,
        settings["format"], settings["dpi"], settings["keep_images"],
        quiet=one_click,
    )
    manifest_path = os.path.join(run_directory, "Exportmanifest.json")
    jsx_path = os.path.join(run_directory, "Photoshop_Uebergabe.jsx")
    write_utf8(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    write_utf8(jsx_path, build_photoshop_jsx(manifest))
    write_report(
        os.path.join(run_directory, "Exportbericht.txt"),
        source_name, settings["format"], settings["dpi"], exported, warnings,
    )

    photoshop = find_photoshop()
    if photoshop:
        try:
            subprocess.Popen([photoshop, "-r", jsx_path])
            if one_click:
                api.Message(
                    "Photoshop-Uebergabe gestartet: {0} Klassen - {1}".format(
                        len(exported), run_directory
                    )
                )
            else:
                api.AlrtDialog(
                    "{0} Klassen wurden exportiert. Photoshop wurde gestartet.\n\n"
                    "Der Ein-Klick-Modus ist jetzt aktiv. Einstellungen spaeter "
                    "mit gedrueckter Umschalttaste beim Aufruf aendern.\n\n{1}".format(
                        len(exported), run_directory
                    )
                )
        except Exception as error:
            api.AlrtDialog(
                "Die Bilder wurden exportiert, Photoshop konnte aber nicht gestartet werden.\n\n"
                "Bitte 'Photoshop_Uebergabe.jsx' in Photoshop ueber Datei > Skripten > "
                "Durchsuchen ausfuehren.\n\n{0}".format(str(error))
            )
    else:
        api.AlrtDialog(
            "Die Bilder wurden exportiert, Photoshop.exe wurde aber nicht gefunden.\n\n"
            "Bitte 'Photoshop_Uebergabe.jsx' in Photoshop ueber Datei > Skripten > "
            "Durchsuchen ausfuehren.\n\n{0}".format(run_directory)
        )


if vs is not None:
    main(vs)
