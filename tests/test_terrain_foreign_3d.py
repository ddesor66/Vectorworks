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

    def GetTypeN(self, handle): return self.types[handle]
    def GetObjectUuid(self, handle): return handle
    def GetName(self, handle): return ""
    def GetClass(self, handle): return "Import"
    def GetLayer(self, handle): return None
    def GetLName(self, handle): return ""
    def Get3DCntr(self, handle): return self.points[handle][0]
    def GetTextOrigin(self, handle): return self.points[handle][0][:2]
    def GetVertNum(self, handle): return len(self.points[handle])
    def GetPolyPt3D(self, handle, index): return self.points[handle][index]
    def GetMeshVertsCnt(self, handle): return len(self.points[handle])
    def GetMeshVertex(self, handle, index): return self.points[handle][index]
    def FInGroup(self, handle): return self.children.get(handle, [None])[0]
    def NextObj(self, handle):
        for values in self.children.values():
            if handle in values:
                index = values.index(handle) + 1
                return values[index] if index < len(values) else None
        return None


def load_adapter(fake):
    sys.modules["vs"] = fake
    name = "PD_GelaendeBaugruben.vw_adapter"
    sys.modules.pop(name, None)
    return importlib.import_module(name)


class Foreign3DTests(unittest.TestCase):
    def test_text_uses_actual_3d_location(self):
        fake = FakeVS()
        fake.types["text"] = 10
        fake.points["text"] = ((12.0, 34.0, 5.5),)
        adapter = load_adapter(fake)
        element = adapter._source_element("text", 1.0, 0.1)
        self.assertEqual(((12.0, 34.0, 5.5),), element["points"])

    def test_nurbs_keeps_individual_vertex_heights(self):
        fake = FakeVS()
        fake.types["curve"] = 111
        fake.points["curve"] = ((0.0, 0.0, 1.0), (2.0, 0.0, 3.0))
        adapter = load_adapter(fake)
        elements = adapter._source_elements("curve", 1.0, 0.1)
        self.assertEqual(((0.0, 0.0, 1.0), (2.0, 0.0, 3.0)), elements[0]["points"])

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


class ForeignGeometryRecoveryTests(unittest.TestCase):
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
