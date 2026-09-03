import importlib
import sys
import types
import unittest


class FakeVS(types.ModuleType):
    def __init__(self):
        super().__init__("vs")
        self.types = {}
        self.points = {}
        self.children = {}
        self.layers = {}
        self.layer_objects = {}
        self.layer_order = []
        self.duplicate_objects = []
        self.classes = {}
        self.pen_colors = {}
        self.fill_colors = {}
        self.line_weights = {}
        self.selected_members = set()
        self.deselected_handles = []
        self.entity_matrices = {}
        self.names = {}
        self.layer_names = {}
        self.class_objects = {}
        self.active_class = "Import"
        self.menu_calls = []
        self.shown_classes = []
        self.shown_layers = []
        self.redraw_count = 0
        self.moves = []

    def GetTypeN(self, handle): return self.types[handle]
    def GetUnits(self): return (None, None, None, 0.0254)
    def GetObjectUuid(self, handle): return handle
    def GetObject(self, name):
        for handle, object_name in self.names.items():
            if object_name == name:
                return handle
        return self.class_objects.get(name)
    def GetName(self, handle): return self.names.get(handle, "")
    def SetName(self, handle, name): self.names[handle] = name
    def GetClass(self, handle): return self.classes.get(handle, "Import")
    def GetLayer(self, handle): return self.layers.get(handle)
    def GetLName(self, handle): return self.layer_names.get(handle, "")
    def ActiveClass(self): return self.active_class
    def NameClass(self, name):
        self.active_class = name
        self.class_objects.setdefault(name, name)
    def ShowClass(self, name): self.shown_classes.append(name)
    def Layer(self, name): self.active_layer_name = name
    def ShowLayer(self): self.shown_layers.append(getattr(self, "active_layer_name", ""))
    def Get3DCntr(self, handle): return self.points[handle][0]
    def GetEntityMatrix(self, handle):
        return self.entity_matrices.get(handle, (False, (0.0, 0.0, 0.0), 0, 0, 0))
    def GetTextOrigin(self, handle): return self.points[handle][0][:2]
    def HCenter(self, handle): return self.points[handle][0][:2]
    def GetLocPt(self, handle): return self.points[handle][0][:2]
    def GetSegPt1(self, handle): return self.points[handle][0][:2]
    def GetSegPt2(self, handle): return self.points[handle][1][:2]
    def GetVertNum(self, handle): return len(self.points[handle])
    def GetPolyPt(self, handle, index): return self.points[handle][index - 1]
    def GetPolyPt3D(self, handle, index): return self.points[handle][index]
    def GetLocus3D(self, handle): return self.points[handle][0]
    def GetLayerElevation(self, _layer): return (0.0, 0.0)
    def GetOriginInDocUnits(self):
        return getattr(self, "document_origin", (0.0, 0.0))
    def IsPolyClosed(self, handle): return handle in getattr(self, "closed", ())
    def GetMeshVertsCnt(self, handle): return len(self.points[handle])
    def GetMeshVertex(self, handle, index): return self.points[handle][index]
    def FInGroup(self, handle): return self.children.get(handle, [None])[0]
    def NextObj(self, handle):
        lists = list(self.children.values()) + list(self.layer_objects.values())
        active = getattr(self, "active_layer_objects", ())
        if active:
            lists.append(active)
        for values in lists:
            if handle in values:
                index = values.index(handle) + 1
                return values[index] if index < len(values) else None
        return None

    def FLayer(self):
        return self.layer_order[0] if self.layer_order else None

    def NextLayer(self, layer):
        if layer not in self.layer_order:
            return None
        index = self.layer_order.index(layer) + 1
        return self.layer_order[index] if index < len(self.layer_order) else None

    def FInLayer(self, layer):
        values = self.layer_objects.get(layer, ())
        return values[0] if values else None

    def FActLayer(self):
        values = getattr(self, "active_layer_objects", ())
        return values[0] if values else None

    def HDuplicate(self, handle, _dx, _dy):
        return getattr(self, "duplicates", {}).get(handle)

    def HMove(self, handle, dx, dy):
        self.moves.append((handle, dx, dy))

    def CreateDuplicateObject(self, handle, container):
        duplicate = handle + "-control"
        self.types[duplicate] = self.types[handle]
        self.layers[duplicate] = container
        self.duplicate_objects.append((handle, container, None, duplicate))
        return duplicate

    def CreateDuplicateObjN(self, handle, container, maintain_relative_height):
        duplicate = handle + "-control"
        self.types[duplicate] = self.types[handle]
        self.layers[duplicate] = container
        self.duplicate_objects.append(
            (handle, container, maintain_relative_height, duplicate))
        return duplicate

    def SetClass(self, handle, class_name): self.classes[handle] = class_name
    def SetPenFore(self, handle, color): self.pen_colors[handle] = color
    def SetFillFore(self, handle, color): self.fill_colors[handle] = color
    def SetLW(self, handle, weight): self.line_weights[handle] = weight
    def SetDSelect(self, handle):
        self.deselected_handles.append(handle)
        self.selected_members.discard(handle)
    def SetSelect(self, handle): self.selected_members.add(handle)

    def DTM6_IsDTM6Object(self, handle):
        return handle in getattr(self, "site_model_handles", ())

    def DTM6_IsObjectReady(self, handle):
        return handle in getattr(self, "ready_site_models", self.site_model_handles)

    def ResetObject(self, handle):
        self.reset_objects = getattr(self, "reset_objects", []) + [handle]

    def DoMenuTextByName(self, name, chunk_index):
        self.menu_calls.append((name, chunk_index))
        if name == "DTM6 Menu" and getattr(self, "created_site_model", None):
            handle = self.created_site_model
            self.site_model_handles.add(handle)
            self.selection = tuple(getattr(self, "selection", ())) + (handle,)

    def ReDrawAll(self): self.redraw_count += 1

    def ConvertTo3DPolys(self, handle):
        return getattr(self, "conversions", {}).get(handle)

    def DelObject(self, handle):
        self.deleted = getattr(self, "deleted", []) + [handle]

    def ForEachObject(self, callback, criteria):
        self.criteria = criteria
        for handle in getattr(self, "selection", ()):
            callback(handle)

    def Count(self, criteria):
        self.count_criteria = criteria
        return getattr(self, "selection_count", len(getattr(self, "selection", ())))

    def NumSelectedObjects(self):
        self.num_selected_called = True
        return getattr(self, "selection_count", len(getattr(self, "selection", ())))

    def Selected(self, handle):
        return handle in getattr(self, "selected_members", ())

    def ForEachObjectInLayer(self, callback, obj_options, traversal_options, layer_options):
        self.layer_search_options = (obj_options, traversal_options, layer_options)
        values = (getattr(self, "active_layer_objects", ())
                  if (obj_options, traversal_options, layer_options) == (0, 2, 0)
                  else getattr(self, "all_document_objects", ())
                  if (obj_options, traversal_options, layer_options) == (0, 2, 1)
                  else getattr(self, "all_layer_selection", ()))
        for handle in values:
            callback(handle)

    def FSActLayer(self):
        return getattr(self, "active_selection", [None])[0]

    def NextSObj(self, handle):
        values = getattr(self, "active_selection", ())
        if handle not in values:
            return None
        index = values.index(handle) + 1
        return values[index] if index < len(values) else None


def load_adapter(fake):
    sys.modules["vs"] = fake
    name = "PD_GelaendeBaugruben.vw_adapter"
    sys.modules.pop(name, None)
    return importlib.import_module(name)


class Foreign3DTests(unittest.TestCase):
    def test_selection_criterion_is_not_rejected_by_second_selection_check(self):
        fake = FakeVS()
        fake.selection = tuple("object-%d" % index for index in range(6059))
        adapter = load_adapter(fake)
        self.assertEqual(6059, len(adapter.selected_handles()))
        self.assertEqual("(SEL=TRUE)", fake.criteria)

    def test_active_layer_selection_completes_partial_criteria_result(self):
        fake = FakeVS()
        fake.selection = ("object-1", "object-2")
        fake.active_selection = tuple("object-%d" % index for index in range(1, 6060))
        adapter = load_adapter(fake)
        handles = adapter.selected_handles()
        self.assertEqual(6059, len(handles))
        self.assertEqual(6059, len(set(handles)))

    def test_deep_all_layer_selection_recovers_full_document_selection(self):
        fake = FakeVS()
        fake.selection = tuple("object-%d" % index for index in range(95))
        fake.active_selection = tuple("object-%d" % index for index in range(1024))
        fake.all_layer_selection = tuple("object-%d" % index for index in range(6059))
        adapter = load_adapter(fake)
        handles = adapter.selected_handles()
        self.assertEqual(6059, len(handles))
        self.assertEqual((0, 2, 1), fake.layer_search_options)

    def test_native_layer_fallback_never_adds_unselected_objects(self):
        fake = FakeVS()
        all_objects = tuple("object-%d" % index for index in range(1, 7))
        expected = ("object-1", "object-3", "object-5")
        fake.selection = ("object-1",)
        fake.active_selection = ("object-1", "object-3")
        fake.all_layer_selection = ("object-1", "object-3")
        fake.all_document_objects = all_objects
        fake.layer_order = ["import"]
        fake.layer_objects["import"] = all_objects
        fake.selected_members = set(expected)
        adapter = load_adapter(fake)

        self.assertEqual(expected, adapter.selected_handles())

    def test_individual_selection_flags_recover_selection_iterator_limit(self):
        fake = FakeVS()
        fake.selection = tuple("object-%d" % index for index in range(95))
        fake.active_selection = tuple("object-%d" % index for index in range(1024))
        fake.all_layer_selection = tuple("object-%d" % index for index in range(1024))
        fake.all_document_objects = tuple("object-%d" % index for index in range(7000))
        fake.selected_members = set("object-%d" % index for index in range(6059))
        adapter = load_adapter(fake)
        handles = adapter.selected_handles()
        self.assertEqual(6059, len(handles))
        self.assertEqual(6059, len(set(handles)))

    def test_native_layer_lists_recover_text_and_lines_omitted_by_callbacks(self):
        fake = FakeVS()
        all_objects = tuple("object-%d" % index for index in range(6059))
        fake.selection = all_objects[:95]
        fake.active_selection = all_objects[:1024]
        fake.all_layer_selection = all_objects[:1024]
        fake.all_document_objects = all_objects[:2928]
        fake.layer_order = ["import"]
        fake.layer_objects["import"] = all_objects
        fake.selected_members = set(all_objects)
        adapter = load_adapter(fake)
        handles = adapter.selected_handles()
        self.assertEqual(all_objects, handles)

    def test_vectorworks_selection_counter_is_available_for_recovery(self):
        fake = FakeVS()
        fake.selection_count = 6059
        adapter = load_adapter(fake)
        self.assertEqual(6059, adapter.selected_object_count())
        self.assertTrue(fake.num_selected_called)

    def test_layer_criterion_escapes_apostrophes(self):
        fake = FakeVS()
        adapter = load_adapter(fake)
        self.assertEqual("Import''DGM", adapter._criterion_literal("Import'DGM"))

    def test_repeated_source_runs_receive_unique_layer_names(self):
        fake = FakeVS()
        fake.names["source-layer-1"] = "PD-GB-Quelldaten"
        fake.names["source-layer-2"] = "PD-GB-Quelldaten-2"
        adapter = load_adapter(fake)

        self.assertEqual("PD-GB-Quelldaten-3",
                         adapter._unique_name("PD-GB-Quelldaten"))

    def test_imported_arc_uses_direct_geometry_fallback(self):
        fake = FakeVS()
        fake.types["arc"] = 6
        fake.points["arc"] = ((10.0, 0.0),)
        fake.HLength = lambda _handle: 0.0
        fake.HCenter = lambda _handle: (0.0, 0.0)
        fake.GetArc = lambda _handle: (0.0, 90.0)
        fake.GetSegPt1 = lambda _handle: (10.0, 0.0)
        adapter = load_adapter(fake)
        element = adapter._source_element("arc", 1.0, 2.0)
        self.assertIsNotNone(element)
        self.assertAlmostEqual(0.0, element["points"][-1][0], places=6)
        self.assertAlmostEqual(10.0, element["points"][-1][1], places=6)

    def test_imported_line_without_3d_center_uses_layer_height_fallback(self):
        fake = FakeVS()
        fake.types["line"] = 2
        fake.points["line"] = ((1.0, 2.0), (3.0, 4.0))
        adapter = load_adapter(fake)
        element = adapter._source_element("line", 1.0, 0.1)
        self.assertEqual(((1.0, 2.0, 0.0), (3.0, 4.0, 0.0)), element["points"])

    def test_imported_line_prefers_native_temporary_3d_conversion(self):
        fake = FakeVS()
        fake.types.update(line=2, converted_line=25)
        fake.points["line"] = ((999999.0, 999999.0), (1000000.0, 1000000.0))
        fake.points["converted_line"] = (
            (3463348.0, 5547900.0, 100.5),
            (3463358.0, 5547900.0, 100.7))
        fake.duplicates = {"line": "line-copy"}
        fake.conversions = {"line-copy": "converted_line"}
        adapter = load_adapter(fake)
        elements = adapter._source_elements("line", 1.0, 0.1)
        self.assertEqual((fake.points["converted_line"],),
                         tuple(value["points"] for value in elements))
        self.assertEqual(("Linie",),
                         tuple(value["source_type_name"] for value in elements))
        self.assertEqual(["converted_line"], fake.deleted)

    def test_2d_locus_is_available_at_layer_height(self):
        fake = FakeVS()
        fake.types["locus"] = 17
        fake.points["locus"] = ((7.0, 8.0),)
        adapter = load_adapter(fake)
        element = adapter._source_element("locus", 1.0, 0.1)
        self.assertEqual(((7.0, 8.0, 0.0),), element["points"])

    def test_text_uses_actual_3d_location(self):
        fake = FakeVS()
        fake.types["text"] = 10
        fake.points["text"] = ((12.0, 34.0, 5.5),)
        fake.entity_matrices["text"] = (
            True, (12.0, 34.0, 5.5), 0.0, 0.0, 0.0)
        fake.GetTextOrigin = lambda _handle: (0.0, 0.0)
        adapter = load_adapter(fake)
        element = adapter._source_element("text", 1.0, 0.1)
        self.assertEqual(((12.0, 34.0, 5.5),), element["points"])

    def test_numeric_text_at_layer_base_uses_text_as_elevation(self):
        fake = FakeVS()
        fake.types["text"] = 10
        fake.points["text"] = ((12.0, 34.0, 0.0),)
        fake.GetText = lambda _handle: "102,65"
        adapter = load_adapter(fake)
        element = adapter._source_element("text", 1.0, 0.1)
        self.assertEqual(((12.0, 34.0, 102.65),), element["points"])
        self.assertEqual("text_content", element["height_source"])

    def test_text_entity_matrix_z_precedes_center_and_numeric_content(self):
        fake = FakeVS()
        fake.types["text"] = 10
        fake.points["text"] = ((12.0, 34.0, 0.0),)
        fake.entity_matrices["text"] = (True, (12.0, 34.0, 102.65), 0.0, 0.0, 0.0)
        fake.GetText = lambda _handle: "999.99"
        adapter = load_adapter(fake)
        element = adapter._source_element("text", 1.0, 0.1)
        self.assertEqual(((12.0, 34.0, 102.65),), element["points"])
        self.assertEqual("object_matrix", element["height_source"])

    def test_imported_line_keeps_document_xy_and_evaluates_tilted_plane_z(self):
        fake = FakeVS()
        fake.types["line"] = 2
        fake.points["line"] = ((0.0, 0.0), (2.0, 0.0))
        fake.entity_matrices["line"] = (
            True, (0.0, 0.0, 10.0), 0.0, -45.0, 0.0)
        adapter = load_adapter(fake)
        element = adapter._source_element("line", 1.0, 0.1)
        self.assertAlmostEqual(0.0, element["points"][0][0])
        self.assertAlmostEqual(0.0, element["points"][0][1])
        self.assertAlmostEqual(10.0, element["points"][0][2])
        self.assertAlmostEqual(2.0, element["points"][1][0])
        self.assertAlmostEqual(0.0, element["points"][1][1])
        self.assertAlmostEqual(12.0, element["points"][1][2])

    def test_imported_polyline_entity_matrix_transforms_every_vertex(self):
        fake = FakeVS()
        fake.types["polyline"] = 21
        fake.points["polyline"] = ((10.0, 20.0), (12.0, 20.0), (12.0, 23.0))
        fake.entity_matrices["polyline"] = (
            True, (10.0, 20.0, 5.0), 0.0, 0.0, 0.0)
        adapter = load_adapter(fake)
        element = adapter._source_element("polyline", 1.0, 0.1)
        self.assertEqual(((10.0, 20.0, 5.0), (12.0, 20.0, 5.0),
                          (12.0, 23.0, 5.0)), element["points"])

    def test_extracted_text_and_line_keep_native_type_provenance(self):
        fake = FakeVS()
        fake.GetUnits = lambda: (None, None, None, 0.0254)
        fake.types.update(text=10, line=2)
        fake.points["text"] = ((12.0, 34.0, 5.5),)
        fake.points["line"] = ((1.0, 2.0, 4.0), (3.0, 4.0, 4.0))
        adapter = load_adapter(fake)
        sources, unsupported = adapter.extract_sources(("text", "line"))
        self.assertFalse(unsupported)
        self.assertEqual(("Text", "Linie"),
                         tuple(value["source_type_name"] for value in sources))
        self.assertEqual(("text", "line"),
                         tuple(value["source_handle"] for value in sources))

    def test_visual_control_layer_copies_each_text_and_line_source_once(self):
        fake = FakeVS()
        fake.types.update(text=10, line=2, point=9)
        adapter = load_adapter(fake)
        review = {"usable": (
            {"source_type": 10, "source_handle": "text"},
            {"source_type": 10, "source_handle": "text"},
            {"source_type": 2, "source_handle": "line"},
            {"source_type": 9, "source_handle": "point"},
        )}
        created, counts = adapter._create_control_copies(review, "control-layer")
        self.assertEqual(("text-control", "line-control"), created)
        self.assertEqual({"texts": 1, "lines": 1}, counts)
        self.assertEqual([
            ("text", "control-layer", False, "text-control"),
            ("line", "control-layer", False, "line-control"),
        ], fake.duplicate_objects)
        self.assertEqual(adapter.CLASS_CONTROL_TEXT, fake.classes["text-control"])
        self.assertEqual(adapter.CLASS_CONTROL_LINE, fake.classes["line-control"])
        self.assertEqual(adapter.COLOR_CONTROL_TEXT, fake.pen_colors["text-control"])
        self.assertEqual(adapter.COLOR_CONTROL_LINE, fake.pen_colors["line-control"])
        self.assertEqual(40, fake.line_weights["line-control"])
        self.assertFalse(fake.Selected("text-control"))
        self.assertFalse(fake.Selected("line-control"))

    def test_document_wide_deselect_ignores_active_layer_restrictions(self):
        fake = FakeVS()
        fake.types.update(group=11, text=10, line=2, source=9, control=10)
        fake.layer_order = ["original-layer", "source-layer", "control-layer"]
        fake.layer_objects.update({
            "original-layer": ["group", "line"],
            "source-layer": ["source"],
            "control-layer": ["control"],
        })
        fake.children["group"] = ["text"]
        fake.selected_members.update({"group", "text", "line", "source", "control"})
        adapter = load_adapter(fake)
        count = adapter._deselect_all_document_objects()
        self.assertEqual(5, count)
        self.assertEqual(set(), fake.selected_members)
        self.assertEqual(
            {"group", "text", "line", "source", "control"},
            set(fake.deselected_handles))

    def test_native_site_model_is_detected_named_revealed_and_selected(self):
        fake = FakeVS()
        fake.site_model_handles = {"existing-model"}
        fake.ready_site_models = {"existing-model", "new-model"}
        fake.selection = ("existing-model",)
        fake.names["existing-model"] = "Vorhandenes DGM"
        fake.created_site_model = "new-model"
        fake.names["new-model"] = "Geländemodell-1"
        fake.types.update({"existing-model": 86, "new-model": 86})
        fake.layer_order = ["model-layer"]
        fake.layer_objects["model-layer"] = ["existing-model", "new-model"]
        fake.layers["existing-model"] = "model-layer"
        fake.layers["new-model"] = "model-layer"
        fake.layer_names["model-layer"] = "PD-GB-Quelldaten"
        adapter = load_adapter(fake)

        result = adapter.create_site_model_from_selected_sources(
            "DGM Bestand", "PD-GB-Gelaendemodell",
            (3463300.0, 5547900.0))

        self.assertEqual("new-model", result["handle"])
        self.assertEqual("DGM Bestand", result["name"])
        self.assertEqual("PD-GB-Gelaendemodell", result["class"])
        self.assertEqual("PD-GB-Quelldaten", result["layer"])
        self.assertTrue(result["ready"])
        self.assertTrue(result["selected"])
        self.assertEqual((3463300.0, 5547900.0), result["xy_anchor_m"])
        self.assertEqual(1, len(fake.moves))
        self.assertEqual("new-model", fake.moves[0][0])
        self.assertAlmostEqual(3463300.0, fake.moves[0][1])
        self.assertAlmostEqual(5547900.0, fake.moves[0][2])
        self.assertEqual("DGM Bestand", fake.names["new-model"])
        self.assertEqual("PD-GB-Gelaendemodell", fake.classes["new-model"])
        self.assertEqual(["PD-GB-Gelaendemodell"], fake.shown_classes)
        self.assertEqual(["PD-GB-Quelldaten"], fake.shown_layers)
        self.assertEqual({"new-model"}, fake.selected_members)
        self.assertEqual(
            [("DTM6 Menu", 1), ("Fit To Objects", 0)], fake.menu_calls)
        self.assertEqual(2, fake.redraw_count)

    def test_second_site_model_receives_an_independent_unique_name(self):
        fake = FakeVS()
        fake.site_model_handles = {"existing-model"}
        fake.ready_site_models = {"existing-model", "new-model"}
        fake.names["existing-model"] = "DGM Bestand"
        fake.created_site_model = "new-model"
        fake.names["new-model"] = "Geländemodell-1"
        fake.types.update({"existing-model": 86, "new-model": 86})
        fake.layer_order = ["model-layer"]
        fake.layer_objects["model-layer"] = ["existing-model", "new-model"]
        fake.layers["existing-model"] = "model-layer"
        fake.layers["new-model"] = "model-layer"
        fake.layer_names["model-layer"] = "PD-GB-Quelldaten-2"
        adapter = load_adapter(fake)

        result = adapter.create_site_model_from_selected_sources(
            "DGM Bestand", "PD-GB-Gelaendemodell", (10.0, 20.0))

        self.assertEqual("DGM Bestand-2", result["name"])
        self.assertEqual("DGM Bestand", fake.names["existing-model"])
        self.assertEqual("DGM Bestand-2", fake.names["new-model"])

    def test_native_site_model_query_metadata_is_written_to_control_layer(self):
        fake = FakeVS()
        fake.site_model_handles = set()
        fake.ready_site_models = {"new-model"}
        fake.created_site_model = "new-model"
        fake.names["new-model"] = "Geländemodell-1"
        fake.types["new-model"] = 86
        fake.layer_order = ["model-layer", "control-layer"]
        fake.layer_objects["model-layer"] = ["new-model"]
        fake.layers["new-model"] = "model-layer"
        fake.layer_names["model-layer"] = "PD-GB-Quelldaten"
        fake.layer_names["control-layer"] = "PD-GB-Quelldaten-Kontrolle"
        adapter = load_adapter(fake)
        adapter._normalized_source_samples = lambda *_args: (
            (0.0, 0.0, 100.0), (1.0, 0.0, 101.0), (0.0, 1.0, 102.0))
        adapter._validate_normalized_site_model = lambda *_args: {
            "checked": 3, "maximum_error_m": 0.0}
        writes = []
        adapter._write_record = lambda *args: writes.append(args)

        result = adapter.create_site_model_from_selected_sources(
            "DGM Bestand", "PD-GB-Gelaendemodell", (10.0, 20.0),
            ("source-1", "source-2", "source-3"),
            "PD-GB-Quelldaten-Kontrolle")

        self.assertEqual("new-model", result["handle"])
        self.assertEqual(1, len(writes))
        self.assertEqual("control-layer", writes[0][0])
        self.assertNotEqual("model-layer", writes[0][0])
        self.assertNotEqual("new-model", writes[0][0])
        self.assertEqual(adapter.QUERY_RECORD, writes[0][1])
        self.assertEqual("new-model", writes[0][3]["model_uuid"])
        self.assertEqual("DGM Bestand", writes[0][3]["model_name"])
        self.assertEqual("source_xy_placement",
                         writes[0][3]["coordinate_mode"])
        self.assertEqual([10.0, 20.0], writes[0][3]["placement_units"])

    def test_query_metadata_prefers_matching_control_layer_record(self):
        fake = FakeVS()
        fake.layers["model"] = "model-layer"
        fake.names["model"] = "DGM Bestand"
        fake.layer_order = ["model-layer", "control-layer"]
        fake.layer_names["model-layer"] = "PD-GB-Quelldaten"
        fake.layer_names["control-layer"] = "PD-GB-Quelldaten-Kontrolle"
        adapter = load_adapter(fake)
        calls = []
        layer_value = {
            "schema": adapter.QUERY_SCHEMA,
            "model_uuid": "model",
            "model_name": "DGM Bestand",
            "xy_anchor_m": [10.0, 20.0],
        }

        def read_record(handle, _name, _field):
            calls.append(handle)
            return layer_value if handle == "control-layer" else None

        adapter._read_record = read_record
        self.assertEqual(layer_value, adapter.model_query_metadata("model"))
        self.assertEqual(["control-layer"], calls)

    def test_cancelled_native_site_model_dialog_returns_no_result(self):
        fake = FakeVS()
        fake.site_model_handles = set()
        fake.selection = ()
        adapter = load_adapter(fake)

        self.assertIsNone(adapter.create_site_model_from_selected_sources(
            "DGM Bestand", "PD-GB-Gelaendemodell"))
        self.assertEqual([("DTM6 Menu", 1)], fake.menu_calls)

    def test_translated_site_model_validation_adds_source_placement(self):
        fake = FakeVS()
        adapter = load_adapter(fake)
        calls = []
        expected = {
            (3463379.4, 5547916.1): 100.7,
            (3463381.4, 5547918.1): 102.5,
            (3463383.4, 5547920.1): 104.2,
        }

        def elevation(_handle, point, tin_type):
            calls.append((point, tin_type))
            return expected[tuple(round(value, 1) for value in point)]

        adapter.site_model.elevation = elevation
        result = adapter._validate_normalized_site_model(
            "model", ((1.0, 2.0, 100.7), (3.0, 4.0, 102.5),
                      (5.0, 6.0, 104.2)),
            (3463378.4, 5547914.1), 1.0)

        self.assertEqual(3, result["checked"])
        self.assertAlmostEqual(0.0, result["maximum_error_m"])
        self.assertEqual([0, 0, 0], [tin_type for _point, tin_type in calls])

    def test_sampler_maps_world_xy_to_normalized_dgm_origin(self):
        fake = FakeVS()
        fake.document_origin = (-3463348.502, -5547900.413)
        adapter = load_adapter(fake)
        adapter._read_record = lambda *_args: {
            "schema": adapter.QUERY_SCHEMA,
            "coordinate_mode": "document_origin_plus_normalized",
            "xy_anchor_m": [3463378.392, 5547914.112],
        }
        calls = []

        def elevation(handle, point, tin_type):
            calls.append((handle, point, tin_type))
            return 102.65

        adapter.site_model.elevation = elevation
        value = adapter.sampler("model", 0)(3463379.392, 5547916.112)

        self.assertAlmostEqual(102.65, value)
        self.assertEqual("model", calls[0][0])
        self.assertEqual(0, calls[0][2])
        self.assertAlmostEqual(-3463347.502, calls[0][1][0])
        self.assertAlmostEqual(-5547898.413, calls[0][1][1])

    def test_sampler_uses_original_xy_for_translated_site_model(self):
        fake = FakeVS()
        adapter = load_adapter(fake)
        adapter._read_record = lambda *_args: {
            "schema": adapter.QUERY_SCHEMA,
            "coordinate_mode": "source_xy_placement",
            "xy_anchor_m": [3463378.392, 5547914.112],
        }
        calls = []

        def elevation(handle, point, tin_type):
            calls.append((handle, point, tin_type))
            return 102.65

        adapter.site_model.elevation = elevation
        value = adapter.sampler("model", 0)(3463379.392, 5547916.112)

        self.assertAlmostEqual(102.65, value)
        self.assertEqual(
            ("model", (3463379.392, 5547916.112), 0), calls[0])

    def test_nurbs_keeps_individual_vertex_heights(self):
        fake = FakeVS()
        fake.types["curve"] = 111
        fake.points["curve"] = ((0.0, 0.0, 1.0), (2.0, 0.0, 3.0))
        adapter = load_adapter(fake)
        elements = adapter._source_elements("curve", 1.0, 0.1)
        self.assertEqual(((0.0, 0.0, 1.0), (2.0, 0.0, 3.0)), elements[0]["points"])

    def test_3d_polygon_keeps_every_zero_based_vertex(self):
        fake = FakeVS()
        fake.types["poly3d"] = 25
        fake.points["poly3d"] = ((0.0, 0.0, 1.0), (2.0, 0.0, 2.0),
                                 (2.0, 3.0, 4.0))
        adapter = load_adapter(fake)
        element = adapter._source_element("poly3d", 1.0, 0.1)
        self.assertEqual(fake.points["poly3d"], element["points"])

    def test_2d_polyline_reads_every_one_based_vertex(self):
        fake = FakeVS()
        fake.types["polyline"] = 21
        fake.points["polyline"] = ((1.0, 2.0), (3.0, 4.0), (5.0, 6.0))
        adapter = load_adapter(fake)
        element = adapter._source_element("polyline", 1.0, 0.1)
        self.assertEqual(((1.0, 2.0, 0.0), (3.0, 4.0, 0.0),
                          (5.0, 6.0, 0.0)), element["points"])

    def test_group_expands_mesh_vertices_and_text(self):
        fake = FakeVS()
        fake.types.update(group=11, mesh=40, text=10)
        fake.children["group"] = ["mesh", "text"]
        fake.points["mesh"] = ((0.0, 0.0, 1.0), (1.0, 0.0, 2.0))
        fake.points["text"] = ((4.0, 5.0, 6.0),)
        adapter = load_adapter(fake)
        elements = adapter._source_elements("group", 1.0, 0.1)
        self.assertEqual(3, len(elements))
        self.assertEqual(["point", "point", "point"], [item["kind"] for item in elements])
        self.assertEqual(["Mesh", "Mesh", "Text"],
                         [item["source_type_name"] for item in elements])
        self.assertEqual(["mesh", "mesh", "text"],
                         [item["source_handle"] for item in elements])

    def test_symbol_is_expanded_to_complete_converted_3d_geometry(self):
        fake = FakeVS()
        fake.types.update(symbol=15, converted=11, face=25)
        fake.duplicates = {"symbol": "symbol-copy"}
        fake.conversions = {"symbol-copy": "converted"}
        fake.children["converted"] = ["face"]
        fake.points["face"] = ((0.0, 0.0, 1.0), (4.0, 0.0, 2.0),
                               (4.0, 3.0, 3.0))
        fake.closed = {"face"}
        adapter = load_adapter(fake)
        elements = adapter._source_elements("symbol", 1.0, 0.1)
        self.assertEqual(1, len(elements))
        self.assertEqual(fake.points["face"], elements[0]["points"])
        self.assertEqual(["converted"], fake.deleted)

    def test_unknown_spatial_object_becomes_support_point(self):
        fake = FakeVS()
        fake.types["foreign-solid"] = 84
        fake.points["foreign-solid"] = ((10.0, 20.0, 30.0),)
        adapter = load_adapter(fake)
        element = adapter._source_element("foreign-solid", 1.0, 0.1)
        self.assertEqual("point", element["kind"])
        self.assertEqual(((10.0, 20.0, 30.0),), element["points"])


class ForeignGeometryRecoveryTests(unittest.TestCase):
    def test_retain_all_keeps_duplicate_and_conflicting_spatial_sources(self):
        from PD_GelaendeBaugruben import core
        elements = (
            {"id": "first", "kind": "point", "points": ((1.0, 1.0, 2.0),),
             "source_handle": "native-first"},
            {"id": "duplicate", "kind": "point", "points": ((1.0, 1.0, 2.0),)},
            {"id": "other-height", "kind": "point", "points": ((1.0, 1.0, 5.0),)},
        )
        result = core.review_sources(
            elements, xy_tolerance_m=0.01, z_tolerance_m=0.01, retain_all=True)
        self.assertEqual(3, result["usable_count"])
        self.assertEqual(0, result["excluded_count"])
        self.assertEqual(1, result["problem_count"])
        self.assertEqual("native-first", result["usable"][0]["source_handle"])

    def test_boundary_crossing_is_skipped_without_blocking_valid_sources(self):
        from PD_GelaendeBaugruben import core
        elements = (
            {"id": "valid", "kind": "point", "points": ((1.0, 1.0, 2.0),)},
            {"id": "crossing", "kind": "breakline",
             "points": ((1.0, 1.0, 2.0), (20.0, 1.0, 2.0))},
        )
        result = core.review_sources(
            elements, boundary=((0.0, 0.0), (10.0, 0.0),
                                (10.0, 10.0), (0.0, 10.0)))
        self.assertEqual(1, result["usable_count"])
        self.assertEqual(1, result["problem_count"])
        self.assertEqual(0, result["blocking_count"])
        self.assertEqual("Modellbegrenzung wird gekreuzt", result["excluded"][0]["reason"])

    def test_conflicting_height_is_skipped_without_stopping_output(self):
        from PD_GelaendeBaugruben import core
        elements = (
            {"id": "first", "kind": "point", "points": ((1.0, 1.0, 2.0),)},
            {"id": "conflict", "kind": "point", "points": ((1.0, 1.0, 5.0),)},
        )
        result = core.review_sources(elements, xy_tolerance_m=0.01, z_tolerance_m=0.01)
        self.assertEqual(1, result["usable_count"])
        self.assertEqual(0, result["blocking_count"])
        self.assertEqual("Widersprüchliche Höhe", result["excluded"][0]["reason"])


if __name__ == "__main__":
    unittest.main()
