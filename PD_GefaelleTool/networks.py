"""Read-only network/level inventory; numbering remains document-wide."""
from . import core


def key(name):
    if not isinstance(name, str) or not name.strip():
        raise core.SlopeError("Bitte einen Namen für das neue Gefällenetz eingeben.")
    suffix = name.strip()[4:] if name.strip().casefold().startswith("gef-") else name.strip()
    if not suffix.strip() or any(ord(char) < 32 for char in name):
        raise core.SlopeError("Bitte einen gültigen, einzeiligen Namen für das Gefällenetz eingeben.")
    return core.level_layer_name(name).casefold()


def inventory(chains, independent_points):
    found = {}

    def row(name):
        identity = key(name)
        if identity not in found:
            found[identity] = dict(name=name.strip(), numbers=set(), chains=set())
        return found[identity]

    for chain in chains:
        value = row(chain["level"])
        value["numbers"].update(p["number"] for p in chain["points"])
        value["chains"].add(chain["chain_id"])
    for level, point in independent_points:
        row(level)["numbers"].add(point["number"])
    return tuple(dict(name=r["name"], point_count=len(r["numbers"]), chain_count=len(r["chains"]))
                 for r in sorted(found.values(), key=lambda r: r["name"].casefold()))


def new_name(value, rows):
    identity = key(value)
    if any(key(row["name"]) == identity for row in rows):
        raise core.SlopeError("Dieses Gefällenetz existiert bereits. Bitte den vorhandenen Listeneintrag auswählen.")
    return value.strip()
