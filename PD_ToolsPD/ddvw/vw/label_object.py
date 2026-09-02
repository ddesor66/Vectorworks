"""Individually editable labels retaining native text and frame attributes."""
import vs

from . import cached_object as cache


PLUGIN = "PD Beschriftungsobjekt"


def text_in(group):
    texts = [h for h in cache.children(group) if vs.GetTypeN(h) == 10]
    if len(texts) != 1:
        raise ValueError("Eine Beschriftung muss genau ein Textfeld enthalten.")
    return texts[0]


def prepare(group, batch):
    text_in(group)
    return cache.prepare(group, PLUGIN, {"kind": "label", "batch": batch})


def convert(group, batch):
    """Replace one newly created label group with a verified native PIO."""
    replacement = prepare(group, batch)
    try:
        return cache.commit(group, replacement)
    except Exception:
        vs.DelObject(replacement)
        raise


def text_dialog(text):
    dialog = vs.CreateLayout("Beschriftung bearbeiten", False, "Übernehmen", "Abbrechen")
    vs.CreateEditTextBox(dialog, 10, text, 64, 10)
    vs.SetFirstLayoutItem(dialog, 10)
    result = []

    def handler(item, data):
        if item == 1:
            result.append(str(vs.GetItemText(dialog, 10)))
        return item

    return result[0] if vs.RunLayoutDialog(dialog, handler) == 1 and result else None


def edit(handle):
    group = cache.profile(handle)
    text = text_in(group)
    previous = vs.GetText(text)
    changed = text_dialog(previous)
    if changed is None or changed == previous:
        return False
    vs.NameUndoEvent("PD Beschriftung bearbeiten")
    try:
        vs.SetText(text, changed)
        if vs.GetText(text) != changed:
            raise RuntimeError("Der Beschriftungstext konnte nicht vollständig gespeichert werden.")
        vs.ResetObject(handle)
    except Exception:
        vs.SetText(text, previous)
        vs.ResetObject(handle)
        raise
    vs.ReDrawAll()
    return True


def batch_of(handle):
    if not handle or vs.GetTypeN(handle) != 86:
        return None
    data = cache.read(handle, PLUGIN)
    return data.get("batch") if data else None


def batch_members(batch):
    result = []

    def collect(handle):
        if batch_of(handle) == batch:
            result.append(handle)

    vs.ForEachObject(collect, "((PON='PD Beschriftungsobjekt'))")
    return result


def batch_parts(group):
    """Read-only preflight: known frame primitives followed by exactly one text."""
    parts, pending = [], []
    for child in cache.children(group):
        kind = vs.GetTypeN(child)
        if kind not in (3, 4, 5, 10):
            raise ValueError("Die Beschriftungsgruppe enthält manuell ergänzte Objekte. Keine automatische Umwandlung.")
        pending.append(child)
        if kind == 10:
            if len(pending) > 2:
                raise ValueError("Beschriftungsrahmen lassen sich nicht eindeutig zuordnen.")
            parts.append(pending)
            pending = []
    if pending or not parts:
        raise ValueError("Die Beschriftungsgruppe lässt sich nicht eindeutig aufteilen.")
    return parts


def convert_batch(group):
    parts = batch_parts(group)
    batch = vs.GetName(group)
    if not batch:
        raise ValueError("Der Beschriftungsstapel hat keinen eindeutigen Namen.")
    parent = vs.GetParent(group)
    replacements = []
    try:
        for index, objects in enumerate(parts):
            vs.BeginGroup()
            try:
                for obj in objects:
                    if not vs.CreateDuplicateObject(obj, None):
                        raise RuntimeError("Beschriftungsgeometrie konnte nicht gesichert werden.")
            finally:
                vs.EndGroup()
                temporary = vs.LNewObj()
            try:
                if vs.GetParent(temporary) != parent and not vs.SetParent(temporary, parent):
                    raise RuntimeError("Beschriftungsebene konnte nicht übernommen werden.")
                vs.SetClass(temporary, vs.GetClass(objects[-1]))
                cache.copy_records(group, temporary)
                native = prepare(temporary, batch)
                replacements.append(native)
                if index:
                    name = batch + "-L%05d" % index
                    if vs.GetObject(name):
                        raise RuntimeError("Ein Beschriftungsname ist bereits vergeben: " + name)
                    vs.SetName(native, name)
            finally:
                vs.DelObject(temporary)
        cache.commit(group, replacements[0])
    except Exception:
        for replacement in replacements:
            vs.DelObject(replacement)
        raise
    return replacements


def run():
    cache.event(PLUGIN, edit)
