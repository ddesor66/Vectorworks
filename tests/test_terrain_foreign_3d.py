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

    def GetTypeN(self, handle): return self.types[handle]
    def GetObjectUuid(self, handle): return handle
    def GetName(self, handle): return ""
    def GetClass(self, handle): return "Import"
    def GetLayer(self, handle): return self.layers.get(handle)
    def GetLName(self, handle): return ""
    def Get3DCntr(self, handle): return self.points[handle][0]
    def GetTextOrigin(self, handle): return self.points[handle][0][:2]
    def GetLocPt(self, handle): return self.points[handle][0][:2]
    def GetSegPt1(self, handle): return self.points[handle][0][:2]
    def GetSegPt2(self, handle): return self.points[handle][1][:2]
    def GetVertNum(self, handle): return len(self.points[handle])
    def GetPolyPt(self, handle, index): return self.points[handle][index - 1]
    def GetPolyPt3D(self, handle, index): return self.points[handle][index]
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

    def test_complete_active_layer_is_independent_of_partial_selection(self):
        fake = FakeVS()
        fake.selection = tuple("object-%d" % index for index in range(95))
        fake.active_layer_objects = tuple("object-%d" % index for index in range(6059))
        adapter = load_adapter(fake)
        handles = adapter.active_layer_handles()
        self.assertEqual(6059, len(handles))
        self.assertFalse(hasattr(fake, "layer_search_options"))

    def test_full_layers_of_truncated_selection_recover_deep_leaf_objects(self):
        fake = FakeVS()
        fake.types.update(selected=2, group=11, line=2, text=10, other=2)
        fake.layers.update({"selected": "import", "group": "import",
                            "line": "import", "text": "import",
                            "other": "other-layer"})
        fake.layer_objects["import"] = ("selected", "group", "line", "text")
        adapter = load_adapter(fake)
        handles = adapter.object_layer_handles(("selected",))
        self.assertEqual(("selected", "group", "line", "text"), handles)

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
