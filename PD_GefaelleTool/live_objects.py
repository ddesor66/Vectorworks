"""Native, reset-on-move PIOs with persistent, named point references.

ResetObject is deferred by Vectorworks. Readers therefore resolve point
parameters directly, never rely on a peer having already regenerated.
"""
import copy
import json
import math
import uuid

import vs
from pd_plan_frame import PlanFrame

from . import core, grade_compat, live_labels, live_model, point_geometry, point_output, settings
from . import vw_adapter as adapter


PLUGIN = live_model.PLUGIN


def data_of(handle):
    if not handle or vs.GetTypeN(handle) != 86:
        return None
    raw = vs.GetRField(handle, PLUGIN, "Daten")
    if not raw:
        return None
    try:
        data = json.loads(raw)
        if data.get("schema") != live_model.SCHEMA or data.get("role") not in (
                "point", "chain", "label"):
            raise ValueError("Unknown live-object schema")
        return data
    except (ValueError, TypeError, AttributeError) as error:
        raise core.SlopeError("Beschädigte Daten in einem verknüpften Gefälleobjekt.") from error


def write_data(handle, data):
    value = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    vs.SetRField(handle, PLUGIN, "Daten", value)
    if vs.GetRField(handle, PLUGIN, "Daten") != value:
        raise core.SlopeError("Verknüpfungsdaten konnten nicht vollständig gespeichert werden.")


def objects(role=None):
    result, errors = [], []

    def collect(handle):
        try:
            data = data_of(handle)
            if data and (role is None or data["role"] == role):
                result.append((handle, data))
        except Exception as error:
            errors.append(error)
    vs.ForEachObject(collect, "((PON='PD GEF Objekt'))")
    if errors:
        raise errors[0]
    return tuple(result)


def read_point(handle, data=None):
    data = data or data_of(handle)
    if not data or data["role"] != "point":
        raise core.SlopeError("Ein verknüpfter Höhenpunkt fehlt. Bitte Löschen rückgängig machen.")
    if vs.GetName(handle) != live_model.POINT_PREFIX + data["id"]:
        raise core.SlopeError("Punktidentität wurde geändert oder kopiert. Bitte den Höhenpunkt neu aufbauen.")
    factor = adapter.units_to_meters()
    xy = tuple(v*factor for v in vs.GetSymLoc(handle))
    # Number is immutable in the OIP. Heights accept German decimal commas.
    height = str(vs.GetRField(handle, PLUGIN, "Hoehe_m")).strip().replace(",", ".")
    return live_model.point_value(data["point"]["number"], xy, height, data["id"])


def read_chain(handle, data=None):
    data = data or data_of(handle)
    if not data or data["role"] != "chain":
        return None
    if vs.GetName(handle) != live_model.CHAIN_PREFIX + data["chain"]["chain_id"]:
        raise core.SlopeError("Diese Gefälledarstellung wurde kopiert oder umbenannt. Für unabhängige Gefälle bitte neue Punkte zeichnen.")
    points = [read_point(vs.GetObject(name)) for name in data["points"]]
    return live_model.resolve_chain(data["chain"], points)


def point_numbers():
    return live_model.unique_point_numbers(read_point(h, d) for h, d in objects("point"))


def connected(name):
    return tuple((h, d) for h, d in objects("chain") if name in d["points"])


def selected_records(handles):
    result = {}
    for handle in handles:
        data = data_of(handle)
        if data and data["role"] == "label":
            handle = vs.GetObject(data["owner"])
            data = data_of(handle)
        if data and data["role"] == "point":
            candidates = connected(vs.GetName(handle))
        elif data and data["role"] == "chain":
            candidates = ((handle, data),)
        else:
            chain = adapter.read_chain(handle)
            if chain:
                result[chain["chain_id"]] = (handle, chain)
            continue
        for peer, peer_data in candidates:
            chain = read_chain(peer, peer_data)
            result[chain["chain_id"]] = (peer, chain)
    return tuple(result.values())


def _display(chain, preferences):
    preferences = settings.validate(preferences)
    angle = PlanFrame.current(vs).angle if preferences.get("align_text_to_plan") else 0.
    output = point_output.for_line_class(chain.get("point_output", preferences.get("point_output")),
                                         preferences["classes"]["line"]["name"])
    adapter.ensure_classes(preferences)
    color = preferences["classes"]["height"]["color"]
    adapter.ensure_class(output["point_class"], color)
    modes = ("2d", "3d") if output["mode"] == "3d" else ("2d",)
    if output["mode"] == "3d":
        adapter.ensure_class(point_output.class_3d(output["point_class"]), color)
        adapter.ensure_class(output["line_class"], preferences["classes"]["line"]["color"])
    symbols = {mode: point_geometry.ensure_symbol(point_output.marker_options(output, mode),
                                                 adapter.units_to_meters(), color) for mode in modes}
    factor = adapter.units_to_meters()
    point_geometry.validate_symbols(symbols, output, factor,
                                    adapter.layer_elevation_units(vs.ActLayer(), factor))
    return dict(preferences=preferences, output=output, symbols=symbols, text_angle=angle)


def _new_object(xy, data, name, created):
    handle = vs.CreateCustomObjectN(PLUGIN, xy, 0., False)
    if not handle or vs.GetTypeN(handle) != 86:
        raise core.SlopeError("Das parametrische Plug-in 'PD GEF Objekt.vso' fehlt. Gesamtinstallation durchführen und Vectorworks neu starten.")
    created.append(handle)
    vs.SetName(handle, name)
    if vs.GetName(handle) != name:
        raise core.SlopeError("Objektidentität konnte nicht reserviert werden.")
    vs.SetClass(handle, vs.ClassList(1))
    write_data(handle, data)
    return handle


def _set_point_fields(handle, point):
    vs.SetRField(handle, PLUGIN, "Nummer", str(point["number"]))
    vs.SetRField(handle, PLUGIN, "Hoehe_m", "%.12g" % point["height_m"])


def _find_points():
    values = {}
    for handle, data in objects("point"):
        point = read_point(handle, data)
        if point["number"] in values:
            raise core.SlopeError("Punktnummer P:%d ist mehrfach vergeben." % point["number"])
        values[point["number"]] = (handle, data, point)
    return values


def create_point(xy_m, height_m, number, level, preferences):
    """Create one standalone point through the transactional batch path."""
    return create_points(((xy_m, height_m, number),), level, preferences)[0]


def create_points(rows, level, preferences):
    """Create several independent points atomically on one network level."""
    rows = tuple(rows)
    if not rows:
        raise core.SlopeError("Es wurden keine Höhenpunkte zum Erstellen übergeben.")
    registry = _find_points()
    occupied = set(registry) | {p["number"] for _, c in adapter.chain_records() for p in c["points"]}
    points = tuple(live_model.point_value(number, xy, height, str(uuid.uuid4()))
                   for xy, height, number in rows)
    numbers = [point["number"] for point in points]
    duplicate = next((number for number in numbers
                      if numbers.count(number) > 1 or number in occupied), None)
    if duplicate is not None:
        raise core.SlopeError("Punktnummer P:%d ist bereits vergeben." % duplicate)
    display = _display({}, preferences)
    previous = str(vs.GetLName(vs.ActLayer()))
    created = []
    point_handles = []
    try:
        if not adapter._activate_layer(core.level_layer_name(level)):
            raise core.SlopeError("Gefällebene konnte nicht aktiviert werden.")
        factor = adapter.units_to_meters()
        for point in points:
            data = dict(display, schema=1, role="point", id=point["point_id"],
                        point=point, level=level)
            handle = _new_object((point["x_m"]/factor, point["y_m"]/factor), data,
                                 live_model.POINT_PREFIX+point["point_id"], created)
            _set_point_fields(handle, point)
            read_point(handle)
            grade_compat.ensure(handle, data, point, created)
            live_labels.ensure(handle, data, created)
            point_handles.append(handle)
        for item in created:
            vs.ResetObject(item)
    except Exception:
        for handle in reversed(created):
            vs.DelObject(handle)
        raise
    finally:
        vs.Layer(previous)
    vs.DSelectAll()
    for handle in point_handles:
        vs.SetSelect(handle)
    vs.ReDrawAll()
    return tuple(point_handles)


def create(chain, preferences):
    core.validate_chain(chain)
    records = tuple(adapter.chain_records())
    registry = _find_points()
    chain = copy.deepcopy(chain)
    for index, point in enumerate(chain["points"]):
        existing = registry.get(point["number"])
        if existing:
            actual = existing[2]
            explicit = point.get("point_id") == actual["point_id"]
            if not explicit and not (index == 0 and chain.get("parent") and not point.get("point_id")):
                raise core.SlopeError("Punktnummer P:%d ist bereits vergeben." % point["number"])
            if any(abs(actual[k]-point[k]) > 1e-6 for k in ("x_m", "y_m", "height_m")):
                raise core.SlopeError("Gemeinsamer Anschlusspunkt besitzt widersprüchliche Koordinaten.")
            point["point_id"] = actual["point_id"]
        else:
            if point.get("point_id") or index == 0 and chain.get("parent"):
                raise core.SlopeError("Der eigenständige Anschlusspunkt fehlt. Bitte die Auswahl erneut prüfen.")
            point["point_id"] = str(uuid.uuid4())
    chain["schema"] = core.SCHEMA_VERSION
    core.validate_document_numbering(tuple(c for _, c in records)+(chain,))
    display = _display(chain, preferences)
    chain["point_output"] = display["output"]
    previous = str(vs.GetLName(vs.ActLayer()))
    created, changed = [], []
    try:
        if not adapter._activate_layer(chain["layer_name"]):
            raise core.SlopeError("Gefällebene konnte nicht aktiviert werden.")
        factor = adapter.units_to_meters()
        references = []
        for index, point in enumerate(chain["points"]):
            existing = registry.get(point["number"])
            if existing:
                handle, data, actual = existing
                # A 3D branch needs its shared, single junction also in 3D.
                if display["output"]["mode"] == "3d" and data["output"]["mode"] != "3d":
                    changed.append((handle, copy.deepcopy(data)))
                    own_display = _display(dict(point_output=dict(data["output"], mode="3d")), data["preferences"])
                    data = dict(data, **own_display)
                    write_data(handle, data)
            else:
                identity = point["point_id"]
                data = dict(display, schema=1, role="point", id=identity, point=point, level=chain["level"])
                handle = _new_object((point["x_m"]/factor, point["y_m"]/factor), data,
                                     live_model.POINT_PREFIX+identity, created)
                _set_point_fields(handle, point)
            grade_compat.ensure(handle, data, point, created)
            references.append(vs.GetName(handle))
        data = dict(display, schema=1, role="chain", chain=chain, points=references)
        connector = _new_object((0., 0.), data, live_model.CHAIN_PREFIX+chain["chain_id"], created)
        adapter.write_chain(connector, chain)
        for name in references:
            point_handle = vs.GetObject(name)
            if not vs.AddAssociation(point_handle, 5, connector):
                raise core.SlopeError("Löschverknüpfung konnte nicht angelegt werden.")
            vs.HMoveForward(point_handle, True)
        for handle in tuple(created):
            live_labels.ensure(handle, data_of(handle), created)
        for handle in created + [h for h, _ in changed]:
            vs.ResetObject(handle)
        read_chain(connector)
    except Exception:
        for handle in reversed(created):
            vs.DelObject(handle)
        for handle, old_data in changed:
            write_data(handle, old_data)
            vs.ResetObject(handle)
        raise
    finally:
        vs.Layer(previous)
    vs.DSelectAll()
    vs.SetSelect(connector)
    vs.ReDrawAll()
    return connector


def replace(replacements, preferences):
    """Preflight the whole graph, then update stable PIO identities in place."""
    replacements = tuple((h, copy.deepcopy(c)) for h, c in replacements)
    if any(not data_of(h) for h, _ in replacements):
        raise core.SlopeError("Diese Zeichnung enthält noch alte Gefällegruppen. Die automatische Umstellung ist noch nicht freigegeben; Originale bleiben unverändert.")
    records = tuple(adapter.chain_records())
    updates = {c["chain_id"]: c for _, c in replacements}
    expected = [updates.get(c["chain_id"], c) for _, c in records]
    core.validate_document_numbering(expected)
    registry = _find_points()
    prepared = [(h, c, _display(c, preferences if preferences is not None else data_of(h)["preferences"]))
                for h, c in replacements]
    snapshots, created, reset, obsolete_labels = {}, [], [], []
    previous = str(vs.GetLName(vs.ActLayer()))

    def remember(handle):
        key = str(handle)
        if key not in snapshots:
            snapshots[key] = (handle, copy.deepcopy(data_of(handle)),
                              vs.GetRField(handle, PLUGIN, "Hoehe_m"))
        reset.append(handle)
    try:
        for handle, chain, display in prepared:
            remember(handle)
            data = data_of(handle)
            refs = []
            if not adapter._activate_layer(chain["layer_name"]):
                raise core.SlopeError("Gefällebene konnte nicht aktiviert werden.")
            factor = adapter.units_to_meters()
            for index, point in enumerate(chain["points"]):
                existing = registry.get(point["number"])
                if existing:
                    peer, old_data, actual = existing
                    if point.get("point_id") and point["point_id"] != actual["point_id"]:
                        raise core.SlopeError("Punktnummer und Punktidentität widersprechen sich.")
                    point["point_id"] = actual["point_id"]
                    if math.hypot(actual["x_m"]-point["x_m"], actual["y_m"]-point["y_m"]) > 1e-6:
                        raise core.SlopeError("Punktlage bitte direkt am Höhenpunkt ändern.")
                    remember(peer)
                    point_data = dict(old_data, point=point)
                    # Shared start inherits its owning chain's appearance.
                    if preferences is not None and (index != 0 or not chain.get("parent")):
                        point_data.update(display)
                    write_data(peer, point_data)
                    _set_point_fields(peer, point)
                    grade_compat.ensure(peer, point_data, point, created)
                    obsolete_labels.extend(live_labels.ensure(peer, point_data, created))
                    registry[point["number"]] = (peer, point_data, point)
                else:
                    identity = str(uuid.uuid4())
                    if point.get("point_id"):
                        raise core.SlopeError("Ein referenzierter Höhenpunkt fehlt.")
                    point["point_id"] = identity
                    point_data = dict(display, schema=1, role="point", id=identity, point=point, level=chain["level"])
                    peer = _new_object((point["x_m"]/factor, point["y_m"]/factor), point_data,
                                       live_model.POINT_PREFIX+identity, created)
                    _set_point_fields(peer, point)
                    grade_compat.ensure(peer, point_data, point, created)
                    registry[point["number"]] = (peer, point_data, point)
                    if not vs.AddAssociation(peer, 5, handle):
                        raise core.SlopeError("Löschverknüpfung konnte nicht angelegt werden.")
                    live_labels.ensure(peer, point_data, created)
                refs.append(vs.GetName(peer))
            new_chain = dict(chain, point_output=display["output"])
            data.update(display, chain=new_chain, points=refs)
            write_data(handle, data)
            adapter.write_chain(handle, new_chain)
            obsolete_labels.extend(live_labels.ensure(handle, data, created))
        for handle in reset+created:
            vs.ResetObject(handle)
    except Exception:
        for handle in reversed(created):
            vs.DelObject(handle)
        for handle, data, height in snapshots.values():
            write_data(handle, data)
            vs.SetRField(handle, PLUGIN, "Hoehe_m", height)
            if data["role"] == "chain":
                adapter.write_chain(handle, data["chain"])
            vs.ResetObject(handle)
        raise
    finally:
        vs.Layer(previous)
    live_labels.delete_obsolete(obsolete_labels)
    vs.ReDrawAll()
    return tuple(h for h, _ in replacements)


def replace_point_display(handle, output):
    """Change only a selected point's presentation, retaining graph identity."""
    old = data_of(handle)
    read_point(handle, old)
    display = _display(dict(point_output=output), old["preferences"])
    data = dict(old, **display)
    try:
        write_data(handle, data)
        vs.ResetObject(handle)
    except Exception:
        write_data(handle, old)
        vs.ResetObject(handle)
        raise
    vs.ReDrawAll()


def reset():
    """Called by the network-licensed VSO entry, never by a background poller."""
    from . import live_render
    ok, plugin, handle, record, wall = vs.GetCustomObjectInfo()
    if not ok or plugin != PLUGIN:
        return
    data = data_of(handle)
    if not data:
        # CreateCustomObjectN performs an initial synchronous reset before
        # _new_object can persist its role and identity. This is a normal,
        # short-lived construction state; a modal alert here re-enters once
        # for every point/label and blocks the drawing workflow.
        return
    vs.SetParameterVisibility(handle, "Daten", False)
    vs.EnableParameter(handle, "Nummer", False)
    vs.EnableParameter(handle, "Hoehe_m", data["role"] == "point")
    try:
        if data["role"] == "label":
            live_labels.draw(handle, data)
            return
        if data["role"] == "chain":
            chain = read_chain(handle, data)
            live_render.draw_chain(handle, data, chain)
            live_labels.reset_for(data)
            return
        expected_name = live_model.POINT_PREFIX + data["id"]
        if vs.GetName(handle) != expected_name:
            # The native duplicate command empties the name of the copy.
            if not vs.GetObject(expected_name):
                vs.SetName(handle, expected_name)
            else:
                occupied = [d["point"]["number"] for h, d in objects("point") if h != handle]
                occupied.extend(p["number"] for h, c in adapter.chain_records() for p in c["points"])
                data["id"] = str(uuid.uuid4())
                data["point"]["number"] = max(occupied or [0])+1
                vs.SetName(handle, live_model.POINT_PREFIX+data["id"])
                write_data(handle, data)
                if data.get("separate_labels"):
                    created_labels = []
                    try:
                        live_labels.ensure(handle, data, created_labels)
                        for label in created_labels:
                            vs.ResetObject(label)
                    except Exception:
                        for label in reversed(created_labels):
                            vs.DelObject(label)
                        raise
        peers = connected(vs.GetName(handle))
        old_point = data["point"]
        try:
            point = read_point(handle, data)
            for peer, peer_data in peers:
                read_chain(peer, peer_data)
        except (core.SlopeError, ValueError, TypeError) as error:
            x, y = vs.GetSymLoc(handle)
            factor = adapter.units_to_meters()
            vs.HMove(handle, old_point["x_m"]/factor-x, old_point["y_m"]/factor-y)
            _set_point_fields(handle, old_point)
            point = old_point
            adapter.alert("Punktänderung nicht übernommen: " + str(error))
        _set_point_fields(handle, point)
        data["point"] = point
        grade_compat.ensure(handle, data, point)
        write_data(handle, data)
        live_render.draw_point(handle, data, point)
        live_labels.reset_for(data)
        # One direction only: chain regeneration never resets points.
        for peer, _ in peers:
            vs.ResetObject(peer)
    except Exception as error:
        # A missing point must not leave a stale numeric slope on screen.
        vs.TextOrigin((0., 0.))
        vs.CreateText("GEFÄLLE PRÜFEN: " + str(error))
        adapter.alert("Gefälleobjekt konnte nicht neu aufgebaut werden: " + str(error))
