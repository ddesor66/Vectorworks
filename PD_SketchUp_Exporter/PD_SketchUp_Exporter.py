# -*- coding: utf-8 -*-
"""PD SketchUp Exporter 1.2.2 für Vectorworks 2026 unter Windows."""

import codecs
import json
import os
import subprocess
import tempfile
import uuid

try:
    import vs
except ImportError:  # Pure Logiktests außerhalb von Vectorworks erlauben.
    vs = None


VERSION = "1.2.2"
MANUFACTURER = "manufactured by Dirk D."
PROGRAM_FOLDER = "PD_SketchUp_Exporter"
CONVERTER_NAME = "PD_SketchUp_Converter.exe"
SKETCHUP_YEAR = "2026"

SETTINGS_SCHEMA_VERSION = 1
SETTINGS_FILE_NAME = "PD_SketchUp_Export.json"

SCOPE_SELECTED = "selected"
SCOPE_CURRENT_VISIBLE = "current_visible"
SCOPE_ALL_VISIBLE = "all_visible"

DIALOG_SETUP = 12255
ITEM_SCOPE_SELECTED = 4
ITEM_SCOPE_CURRENT = 5
ITEM_SCOPE_ALL = 6
ITEM_NOTE = 7
ITEM_ONE_CLICK_NOTE = 8
ITEM_TITLE = 9
ITEM_SELECTION_STATUS = 10


def _dialog_title(title):
    return "%s | v%s | %s" % (str(title), VERSION, MANUFACTURER)


def _safe_text(value, fallback=""):
    try:
        text = str(value or "").strip()
    except Exception:
        text = ""
    return text or fallback


def _default_settings():
    return {
        "scope": SCOPE_SELECTED,
        "output_path": "",
        "one_click_ready": False,
    }


def _settings_file_path(environ=None):
    environment = os.environ if environ is None else environ
    appdata = _safe_text(environment.get("APPDATA", ""))
    if not appdata:
        return ""
    return os.path.join(
        appdata, "Nemetschek", "Vectorworks", "2026", "Settings",
        SETTINGS_FILE_NAME,
    )


def _normalize_skp_path(path):
    normalized = os.path.abspath(_safe_text(path)) if _safe_text(path) else ""
    if normalized and os.path.splitext(normalized)[1].lower() != ".skp":
        normalized += ".skp"
    return normalized


def _load_settings(environ=None):
    result = _default_settings()
    path = _settings_file_path(environ)
    if not path:
        return result
    try:
        with codecs.open(path, "r", "utf-8") as stream:
            data = json.load(stream)
        if int(data.get("schema", 0)) != SETTINGS_SCHEMA_VERSION:
            return result
        scope = data.get("scope", "")
        if scope in (SCOPE_SELECTED, SCOPE_CURRENT_VISIBLE, SCOPE_ALL_VISIBLE):
            result["scope"] = scope
        output_path = _normalize_skp_path(data.get("outputPath", ""))
        if output_path and os.path.isdir(os.path.dirname(output_path)):
            result["output_path"] = output_path
        result["one_click_ready"] = bool(
            data.get("oneClickReady", False) and result["output_path"])
    except (IOError, OSError, TypeError, ValueError):
        return _default_settings()
    return result


def _save_settings(scope, output_path, environ=None):
    if scope not in (SCOPE_SELECTED, SCOPE_CURRENT_VISIBLE, SCOPE_ALL_VISIBLE):
        return False
    output_path = _normalize_skp_path(output_path)
    if not output_path or not os.path.isdir(os.path.dirname(output_path)):
        return False
    path = _settings_file_path(environ)
    if not path:
        return False
    temporary = path + ".tmp"
    try:
        directory = os.path.dirname(path)
        if not os.path.isdir(directory):
            os.makedirs(directory)
        payload = {
            "schema": SETTINGS_SCHEMA_VERSION,
            "scope": scope,
            "outputPath": output_path,
            "oneClickReady": True,
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


def _shift_requests_setup(api):
    try:
        _option, _command, shift = api.GetModifierFlags()
        return bool(shift)
    except (AttributeError, TypeError, ValueError):
        return False


def _can_run_one_click(settings, force_setup=False):
    output_path = settings.get("output_path", "")
    return bool(
        not force_setup
        and settings.get("one_click_ready")
        and output_path
        and os.path.isdir(os.path.dirname(output_path))
    )


def _temporary_output_path(output_path):
    directory = os.path.dirname(output_path)
    stem = os.path.splitext(os.path.basename(output_path))[0]
    return os.path.join(
        directory,
        ".{0}.PD_SKP_{1}.skp".format(stem, uuid.uuid4().hex),
    )


def _object_type(handle):
    try:
        return int(vs.GetTypeN(handle))
    except Exception:
        return 0


def _object_name(handle, number):
    try:
        name = _safe_text(vs.GetName(handle))
    except Exception:
        name = ""
    if not name and _object_type(handle) == 15:
        try:
            name = _safe_text(vs.GetSymName(handle))
        except Exception:
            name = ""
    return name or "Objekt {} (Typ {})".format(number, _object_type(handle))


def _layer_name(handle):
    try:
        layer_handle = vs.GetLayer(handle)
        if layer_handle:
            return _safe_text(vs.GetLName(layer_handle), "Konstruktionsebene")
    except Exception:
        pass
    return "Konstruktionsebene"


def _class_name(handle):
    try:
        return _safe_text(vs.GetClass(handle), "Keine Klasse")
    except Exception:
        return "Keine Klasse"


def _fill_color(handle):
    try:
        raw = vs.GetFillFore(handle)
        values = list(raw) if isinstance(raw, (tuple, list)) else []
        if len(values) >= 3:
            rgb = [max(0, int(values[i])) for i in range(3)]
            if max(rgb) > 255:
                rgb = [min(255, int(round(value / 257.0))) for value in rgb]
            return rgb
    except Exception:
        pass
    return [180, 180, 180]


def _walk_container(container):
    try:
        child = vs.FInGroup(container)
    except Exception:
        child = None
    while child:
        yield child
        if _object_type(child) == 11:
            for descendant in _walk_container(child):
                yield descendant
        try:
            child = vs.NextObj(child)
        except Exception:
            child = None


def _read_3d_polygon(handle):
    if _object_type(handle) != 25:
        return None
    try:
        count = int(vs.GetVertNum(handle))
    except Exception:
        return None
    if count < 3:
        return None

    points = []
    for index in range(count):
        try:
            point = vs.GetPolyPt3D(handle, index)
            if not isinstance(point, (tuple, list)) or len(point) < 3:
                return None
            points.append([float(point[0]), float(point[1]), float(point[2])])
        except Exception:
            return None
    return points


def _faces_from_conversion(converted):
    faces = []
    direct = _read_3d_polygon(converted)
    if direct:
        faces.append(direct)
    if _object_type(converted) == 11:
        for candidate in _walk_container(converted):
            face = _read_3d_polygon(candidate)
            if face:
                faces.append(face)
    return faces


def _convert_object_to_faces(source):
    duplicate = None
    converted = None
    try:
        duplicate = vs.HDuplicate(source, 0.0, 0.0)
        if not duplicate:
            return []
        if _object_type(duplicate) == 40:
            converted = vs.MeshToGroup(duplicate)
        else:
            converted = vs.ConvertTo3DPolys(duplicate)
        if not converted:
            return []
        return _faces_from_conversion(converted)
    except Exception:
        return []
    finally:
        try:
            if converted:
                vs.DelObject(converted)
            elif duplicate:
                vs.DelObject(duplicate)
        except Exception:
            pass


def _collect_handles(scope):
    handles = []

    def remember(handle):
        handles.append(handle)
        return False

    if scope == SCOPE_SELECTED:
        vs.ForEachObjectInLayer(remember, 2, 0, 1)
    elif scope == SCOPE_CURRENT_VISIBLE:
        vs.ForEachObjectInLayer(remember, 1, 0, 0)
    else:
        vs.ForEachObjectInLayer(remember, 1, 0, 2)
    return handles


def _document_units_per_inch():
    try:
        units = vs.GetUnits()
        if isinstance(units, (tuple, list)) and len(units) >= 4:
            value = float(units[3])
            if value > 0.0:
                return value
    except Exception:
        pass
    raise RuntimeError("Die Dokumenteinheit konnte nicht zuverlässig ermittelt werden.")


def _build_exchange(handles):
    objects = []
    skipped = []
    for number, handle in enumerate(handles, 1):
        name = _object_name(handle, number)
        faces = _convert_object_to_faces(handle)
        if not faces:
            skipped.append(name)
            continue
        objects.append(
            {
                "name": name,
                "layer": _layer_name(handle),
                "vw_class": _class_name(handle),
                "color": _fill_color(handle),
                "faces": faces,
            }
        )
    return {
        "schema_version": 1,
        "units_per_inch": _document_units_per_inch(),
        "objects": objects,
    }, skipped


def _candidate_program_folders():
    seen = set()
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        path = os.path.join(
            appdata,
            "Nemetschek",
            "Vectorworks",
            "2026",
            "Plug-Ins",
            PROGRAM_FOLDER,
        )
        seen.add(os.path.normcase(os.path.abspath(path)))
        yield path

    for folder_id in (-2, 1, 12, 0):
        try:
            base = vs.GetFolderPath(folder_id)
            if isinstance(base, (tuple, list)):
                base = base[0]
            if not base:
                continue
        except Exception:
            continue
        for path in (
            os.path.join(str(base), PROGRAM_FOLDER),
            os.path.join(str(base), "Plug-Ins", PROGRAM_FOLDER),
        ):
            normalized = os.path.normcase(os.path.abspath(path))
            if normalized not in seen:
                seen.add(normalized)
                yield path


def _find_converter():
    for folder in _candidate_program_folders():
        candidate = os.path.join(folder, CONVERTER_NAME)
        if os.path.isfile(candidate):
            return candidate
    return None


def _find_sketchup_api_folder():
    candidates = []
    for variable in ("ProgramFiles", "ProgramW6432"):
        base = os.environ.get(variable, "")
        if base:
            candidates.append(
                os.path.join(base, "SketchUp", "SketchUp {}".format(SKETCHUP_YEAR), "SketchUp")
            )
    candidates.append(r"C:\Program Files\SketchUp\SketchUp 2026\SketchUp")
    for folder in candidates:
        if os.path.isfile(os.path.join(folder, "SketchUpAPI.dll")):
            return folder
    return None


def _default_output_name():
    try:
        document_path = _safe_text(vs.GetFPathName())
    except Exception:
        document_path = ""
    if document_path:
        base = os.path.splitext(os.path.basename(document_path))[0]
        if base:
            return base + ".skp"
    return "Vectorworks-Export.skp"


def _choose_scope(default_scope=SCOPE_SELECTED):
    selected_count = len(_collect_handles(SCOPE_SELECTED))
    dialog = vs.CreateLayout(
        _dialog_title("PD SketchUp-Export"), False,
        "Exportieren", "Abbrechen")
    vs.CreateStyledStatic(
        dialog, ITEM_TITLE,
        "SKETCHUP-EXPORT  |  Quelle festlegen", -1, 213)
    vs.CreateStaticText(
        dialog, ITEM_NOTE,
        "Welche Zeichnungselemente sollen nach SketchUp 2026 exportiert werden?",
        68)
    if selected_count:
        selection_status = (
            "Zeichnungsauswahl erkannt: %d Objekt(e). "
            "„Ausgewählte Objekte“ kann direkt verwendet werden."
            % selected_count)
    else:
        selection_status = (
            "Für „Ausgewählte Objekte“ zuerst Abbrechen, die gewünschten "
            "Objekte mit dem Auswahlwerkzeug markieren und den Befehl erneut öffnen.")
    vs.CreateStaticText(
        dialog, ITEM_SELECTION_STATUS, selection_status, 68)
    vs.CreateRadioButton(dialog, ITEM_SCOPE_SELECTED, "Ausgewählte Objekte")
    vs.CreateRadioButton(dialog, ITEM_SCOPE_CURRENT, "Sichtbare Objekte der aktiven Konstruktionsebene")
    vs.CreateRadioButton(dialog, ITEM_SCOPE_ALL, "Sichtbare Objekte aller sichtbaren Konstruktionsebenen")
    vs.CreateStaticText(
        dialog, ITEM_ONE_CLICK_NOTE,
        "Nach dem ersten erfolgreichen Export ist der Ein-Klick-Modus aktiv. "
        "Zum Ändern später beim Aufruf die Umschalttaste gedrückt halten.",
        68,
    )
    vs.SetFirstLayoutItem(dialog, ITEM_TITLE)
    vs.SetBelowItem(dialog, ITEM_TITLE, ITEM_NOTE, 0, 8)
    vs.SetBelowItem(dialog, ITEM_NOTE, ITEM_SELECTION_STATUS, 0, 4)
    vs.SetBelowItem(dialog, ITEM_SELECTION_STATUS, ITEM_SCOPE_SELECTED, 0, 8)
    vs.SetBelowItem(dialog, ITEM_SCOPE_SELECTED, ITEM_SCOPE_CURRENT, 0, 0)
    vs.SetBelowItem(dialog, ITEM_SCOPE_CURRENT, ITEM_SCOPE_ALL, 0, 0)
    vs.SetBelowItem(dialog, ITEM_SCOPE_ALL, ITEM_ONE_CLICK_NOTE, 0, 8)

    def handler(item, data):
        del data
        if item == DIALOG_SETUP:
            selected_item = {
                SCOPE_CURRENT_VISIBLE: ITEM_SCOPE_CURRENT,
                SCOPE_ALL_VISIBLE: ITEM_SCOPE_ALL,
            }.get(default_scope, ITEM_SCOPE_SELECTED)
            vs.SetBooleanItem(dialog, selected_item, True)
        elif item == 1:
            if (vs.GetBooleanItem(dialog, ITEM_SCOPE_SELECTED) and
                    selected_count == 0):
                vs.AlertInform(
                    "Keine Objekte ausgewählt.",
                    "Bitte den Dialog abbrechen, die gewünschten Objekte "
                    "markieren und den SketchUp-Export erneut öffnen.", False)
                return -1
        return item

    if vs.RunLayoutDialog(dialog, handler) != 1:
        return None
    if vs.GetBooleanItem(dialog, ITEM_SCOPE_CURRENT):
        return SCOPE_CURRENT_VISIBLE
    if vs.GetBooleanItem(dialog, ITEM_SCOPE_ALL):
        return SCOPE_ALL_VISIBLE
    return SCOPE_SELECTED


def _write_exchange_file(exchange):
    descriptor, path = tempfile.mkstemp(prefix="PD_SKP_", suffix=".json")
    os.close(descriptor)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(exchange, stream, ensure_ascii=False, separators=(",", ":"))
    return path


def _run_converter(converter, exchange_path, output_path, api_folder):
    creation_flags = 0x08000000 if os.name == "nt" else 0
    result = subprocess.run(
        [converter, exchange_path, output_path, api_folder],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
        check=False,
        timeout=600,
    )
    if result.returncode != 0:
        detail = _safe_text(result.stderr, _safe_text(result.stdout, "Unbekannter Konverterfehler"))
        raise RuntimeError(detail)
    return _safe_text(result.stdout)


def run_export():
    settings = _load_settings()
    force_setup = _shift_requests_setup(vs)
    one_click = _can_run_one_click(settings, force_setup)

    if one_click:
        scope = settings["scope"]
        output_path = settings["output_path"]
    else:
        scope = _choose_scope(settings["scope"])
        if scope is None:
            return
        selected_path = _safe_text(
            vs.PutFile("SketchUp-2026-Datei speichern", _default_output_name())
        )
        if not selected_path:
            return
        output_path = _normalize_skp_path(selected_path)

    handles = _collect_handles(scope)
    if not handles:
        vs.AlrtDialog("Es wurden keine Objekte für den Export gefunden.")
        return

    converter = _find_converter()
    if not converter:
        vs.AlrtDialog(
            "Der SketchUp-Konverter fehlt. Bitte den PD SketchUp Exporter erneut installieren."
        )
        return
    api_folder = _find_sketchup_api_folder()
    if not api_folder:
        vs.AlrtDialog(
            "SketchUp 2026 oder dessen SketchUpAPI.dll wurde nicht gefunden. "
            "Bitte SketchUp 2026 installieren bzw. reparieren."
        )
        return

    try:
        vs.Close(output_path)
    except Exception as error:
        vs.AlrtDialog("Die gewählte Zieldatei konnte nicht geschlossen werden:\n\n{}".format(_safe_text(error)))
        return

    exchange_path = None
    temporary_output = None
    try:
        exchange, skipped = _build_exchange(handles)
        if not exchange["objects"]:
            vs.AlrtDialog(
                "Die gewählten Objekte konnten nicht in 3D-Flächen umgewandelt werden. "
                "Bitte echte 3D-Objekte auswählen und erneut exportieren."
            )
            return
        exchange_path = _write_exchange_file(exchange)
        temporary_output = _temporary_output_path(output_path)
        _run_converter(converter, exchange_path, temporary_output, api_folder)
        if not os.path.isfile(temporary_output) or os.path.getsize(temporary_output) <= 0:
            raise RuntimeError("Der Konverter hat keine lesbare SketchUp-Datei erzeugt.")
        os.replace(temporary_output, output_path)
        temporary_output = None
        if not one_click:
            _save_settings(scope, output_path)
        message = "SketchUp-Export abgeschlossen.\n\n{}\n\n{} Objekt(e) exportiert.".format(
            output_path, len(exchange["objects"])
        )
        if skipped:
            message += "\n{} Objekt(e) ohne auswertbare 3D-Flächen wurden übersprungen.".format(
                len(skipped)
            )
        if one_click:
            vs.Message(message.replace("\n\n", " - ").replace("\n", " "))
        else:
            message += (
                "\n\nDer Ein-Klick-Modus ist jetzt aktiv. Einstellungen später "
                "mit gedrückter Umschalttaste beim Aufruf ändern."
            )
            vs.AlrtDialog(message)
    except Exception as error:
        vs.AlrtDialog("SketchUp-Export fehlgeschlagen:\n\n{}".format(_safe_text(error)))
    finally:
        if temporary_output and os.path.isfile(temporary_output):
            try:
                os.remove(temporary_output)
            except Exception:
                pass
        if exchange_path and os.path.isfile(exchange_path):
            try:
                os.remove(exchange_path)
            except Exception:
                pass


if vs is not None:
    run_export()
