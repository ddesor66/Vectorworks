import importlib
import sys
import types
import unittest
from unittest import mock


class TerrainSelectionScopeTests(unittest.TestCase):
    def test_preview_uses_only_selected_handles_even_with_legacy_layer_option(self):
        sys.modules.setdefault("vs", types.ModuleType("vs"))
        app = importlib.import_module("PD_GelaendeBaugruben.app")
        selected = ("selected-text", "selected-line")
        sources = (
            {"kind": "point", "points": ((1.0, 2.0, 100.0),)},
            {"kind": "breakline", "points": ((3.0, 4.0, 101.0),
                                                 (5.0, 6.0, 102.0))},
        )
        review = {
            "input_count": 2,
            "usable_count": 2,
            "excluded_count": 0,
            "problem_count": 0,
            "vertex_count": 3,
            "blocking_count": 0,
            "usable": sources,
            "excluded": (),
            "problems": (),
        }
        captured = {}

        def extract_sources(handles, _tolerance, _boundary):
            captured["handles"] = handles
            return sources, ()

        def confirm(question, advice):
            captured["question"] = question
            captured["advice"] = advice
            return False

        options = {
            "model_name": "DGM Auswahl",
            "model_class": "PD-GB-Gelaendemodell",
            "chord_tolerance_m": 0.1,
            "xy_tolerance_m": 0.001,
            "z_tolerance_m": 0.001,
            "excluded_classes": "",
            "excluded_layers": "",
            "use_selected_boundary": False,
            # A saved pre-1.0.26 value must not broaden the current selection.
            "all_active_layer": True,
        }
        with mock.patch.object(app.adapter, "selected_handles", return_value=selected), \
                mock.patch.object(app.adapter, "selected_object_count", return_value=6059), \
                mock.patch.object(app.adapter, "extract_sources", side_effect=extract_sources), \
                mock.patch.object(app.adapter, "source_handle_types", return_value=(
                    {"type_name": "Text"}, {"type_name": "Linie"})), \
                mock.patch.object(app.adapter, "confirm", side_effect=confirm), \
                mock.patch.object(app.core, "review_sources", return_value=review):
            app._preview_sources(options)

        self.assertEqual(selected, captured["handles"])
        self.assertIn("Erfassungsbereich: ausschließlich markierte Objekte",
                      captured["question"])
        self.assertIn("keine unmarkierten Ebenenobjekte ergänzt",
                      captured["question"])
        self.assertIn("eigene, eindeutige Quell- und Kontrollebenen",
                      captured["advice"])
        self.assertNotIn("gesamte aktive Ebene", captured["question"])
        self.assertNotIn("Ebenen mit Markierung", captured["question"])


if __name__ == "__main__":
    unittest.main()
