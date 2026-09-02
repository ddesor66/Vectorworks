"""Double-click editor for the unchanged wall/gabion calculation engine."""
import importlib.util
import json
from pathlib import Path
import sys
import uuid

import vs

from . import cached_object as cache


PLUGIN = "PD Mauer Objekt"
RECORD = "PD_MW_Steuerung"


def engine():
    name = "pd_wall_edit_engine"
    if name not in sys.modules:
        path = Path(__file__).resolve().parents[3] / "PD_Winkelstuetzmauer/PD_Winkelstuetzmauer.py"
        spec = importlib.util.spec_from_file_location(name, str(path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        sys.modules[name] = module
    return sys.modules[name]


def is_wall(handle):
    return bool(handle and vs.GetTypeN(handle) == 86 and vs.GetRField(handle, PLUGIN, cache.DATA))


def wall_data(handle):
    value = json.loads(vs.GetRField(handle, RECORD, "Daten") or "null")
    if not isinstance(value, dict) or not value.get("wall_id") or not value.get("uk_pts") or not value.get("ok_pts"):
        raise ValueError("Die Gruppe enthält keine vollständigen PD-Mauerdaten.")
    return value


def write_wall(handle, data):
    raw = json.dumps(data, ensure_ascii=True, allow_nan=False)
    vs.SetRecord(handle, RECORD)
    vs.SetRField(handle, RECORD, "Daten", raw)
    if vs.GetRField(handle, RECORD, "Daten") != raw:
        raise RuntimeError("Die ursprünglichen Mauereinstellungen konnten nicht gespeichert werden.")


def prepare(group):
    data = wall_data(group)
    return cache.prepare(group, PLUGIN, {"kind": "wall", "wall_id": data["wall_id"]})


def convert(group):
    replacement = prepare(group)
    try:
        return cache.commit(group, replacement)
    except Exception:
        vs.DelObject(replacement)
        raise


def replace_built(handle, group, data, commit=None):
    """Replace one profile atomically and retain the native object identity."""
    state = cache.read(handle, PLUGIN)
    if not state or "origin" not in state:
        raise RuntimeError("Die gespeicherte Lage des Mauerobjekts fehlt.")
    original = cache.profile(handle)
    old_data = wall_data(handle)
    parent = vs.GetParent(group)
    backup = vs.CreateDuplicateObject(original, parent)
    replacement = vs.CreateDuplicateObject(group, parent)
    if not backup or not replacement:
        for temporary in (backup, replacement):
            if temporary:
                vs.DelObject(temporary)
        raise RuntimeError("Geometriesicherung für die Bearbeitung fehlgeschlagen.")
    origin = state["origin"]
    vs.HMove(replacement, -origin[0], -origin[1])
    try:
        if not vs.SetCustomObjectProfileGroup(handle, replacement):
            raise RuntimeError("Die neue Mauergeometrie konnte nicht übernommen werden.")
        replacement = None  # Adopted by the native object.
        cache.align_profile(handle, vs.GetBBox(group), origin)
        write_wall(handle, data)
        if wall_data(handle) != data:
            raise RuntimeError("Die bearbeiteten Mauerdaten wurden nicht vollständig übernommen.")
        cache.profile(handle)
        if commit is not None:
            committed = commit()
            if committed is False:
                raise RuntimeError("Die Mauerverwaltung konnte nicht aktualisiert werden.")
        vs.ResetObject(handle)
    except Exception:
        if not vs.SetCustomObjectProfileGroup(handle, backup):
            raise RuntimeError("Geometrie-Rücknahme fehlgeschlagen; bitte sofort Rückgängig verwenden.")
        backup = None  # Adopted while restoring the original profile.
        write_wall(handle, old_data)
        vs.ResetObject(handle)
        raise
    else:
        if backup:
            vs.DelObject(backup)
        vs.DelObject(group)
    finally:
        if replacement:
            vs.DelObject(replacement)
    return handle


def edit(handle):
    module = engine()
    data = wall_data(handle)
    settings = dict(module.DEFAULTS)
    settings.update(data)
    settings["action"] = 1
    module.U.set(settings.get("unit", "m"))
    for prefix in (settings.get("prefix"), settings.get("winkel_prefix"), settings.get("gab_prefix")):
        module.register_prefix(prefix)
    module._kataloge.clear()
    for kind in (0, 1):
        module._kataloge[kind] = module.load_catalog(kind, settings)
    accepted, changed = module.show_dialog(settings)
    if not accepted:
        return False
    if int(changed.get("stein_typ", 0)) != module.bestands_mauertyp(data):
        raise ValueError("Der Wandtyp bleibt beim Bearbeiten erhalten. Für einen anderen Typ bitte eine neue Wand erstellen.")
    errors = module.validate_params(changed)
    if errors:
        raise ValueError("\n".join(errors))
    vs.NameUndoEvent("PD Mauer bearbeiten")
    original_data, original_name = data, vs.GetName(handle)
    # A duplicate receives its own identity only AFTER accepting the dialog.
    if original_name != data.get("gruppe"):
        data = dict(data, wall_id=("GAB-" if data.get("bauart") == "gabione" else "MW-") + uuid.uuid4().hex,
                    gruppe="PD-MW-GRP-" + uuid.uuid4().hex, tab_names=[], ws_names=[], bez_name="")
        vs.SetName(handle, data["gruppe"])
        write_wall(handle, data)
    try:
        ok, message = module.rebuild([handle], data, changed)
    except Exception:
        vs.SetName(handle, original_name)
        write_wall(handle, original_data)
        raise
    if not ok:
        vs.SetName(handle, original_name)
        write_wall(handle, original_data)
        raise RuntimeError(message)
    vs.SetSelect(handle)
    vs.ReDrawAll()
    return True


def run():
    cache.event(PLUGIN, edit)
