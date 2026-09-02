# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import types
import unittest
import zipfile
import xml.etree.ElementTree as element_tree
from unittest import mock


sys.modules.setdefault("vs", types.ModuleType("vs"))

from PD_KanalLeitungMengen import app, core, reporting


def _shaft(identity, name, x_m, ks_m, visible=True, structure_type="round", stub=None):
    return {
        "id": identity, "name": name, "kind": "RW", "visible": visible,
        "structure_type": structure_type, "construction_material": "concrete",
        "diameter_m": 1.0 if visible else 0.0, "wall_thickness_m": 0.15,
        "x_m": x_m, "y_m": 0.0, "kd_m": ks_m + 2.0, "ks_m": ks_m,
        "stub": stub,
    }


def _pipe(identity, name, start_id, end_id, start_ks, end_ks, length,
          dn=300, material="STB"):
    return {
        "id": identity, "name": name, "network_id": "INTERNE-NETZ-ID",
        "start_id": start_id, "end_id": end_id, "kind": "RW", "dn_mm": dn,
        "outside_diameter_mm": dn, "outside_diameter_explicit": True,
        "wall_thickness_mm": 10.0, "hollow_3d": True, "material": material,
        "start_invert_m": start_ks, "end_invert_m": end_ks,
        "slope_percent": (start_ks - end_ks) / length * 100.0,
        "length_m": length,
    }


def _report():
    stub_data = {
        "alignment": "invert", "branch_dn_mm": 150,
        "main_pipe_ids": ["INTERNAL-P1", "INTERNAL-P2"],
    }
    shafts = (
        _shaft("INTERNAL-S1", "RW.001", 0.0, 100.0),
        _shaft("INTERNAL-STUB", "", 10.0, 99.8, False, "stub", stub_data),
        _shaft("INTERNAL-S2", "RW.002", 20.0, 99.6),
        _shaft("INTERNAL-S3", "RW.003", 10.0, 100.3),
    )
    pipes = (
        _pipe("INTERNAL-P1", "H-RW.002", "INTERNAL-S1", "INTERNAL-STUB", 100.0, 99.8, 10.0),
        _pipe("INTERNAL-P2", "H-RW.002", "INTERNAL-STUB", "INTERNAL-S2", 99.8, 99.6, 10.0),
        _pipe("INTERNAL-B1", "H-RW.002", "INTERNAL-S3", "INTERNAL-STUB", 100.3, 99.8,
              8.0, dn=150, material="PP"),
    )
    result = core.analyze(pipes, shafts, ())
    result["metadata"] = {
        "document": "Mengentest.vwx", "path": "", "created": "02.09.2026 12:00",
        "standard": "DIN EN 1610", "shoring": "Verbaute Gräben",
    }
    return result


class QuantitySummaryTests(unittest.TestCase):
    def test_equal_pipes_are_grouped_by_kind_dn_and_material(self):
        result = _report()
        rows = {(row["kind"], row["dn_mm"], row["material"]): row
                for row in result["pipe_summary"]}
        self.assertEqual(1, rows[("RW", 300, "STB")]["holding_count"])
        self.assertAlmostEqual(20.0, rows[("RW", 300, "STB")]["length_2d_m"])
        self.assertEqual(1, rows[("RW", 150, "PP")]["holding_count"])

    def test_stubs_and_shaft_groups_have_separate_summaries(self):
        result = _report()
        self.assertEqual(1, result["totals"]["stub_count"])
        self.assertEqual(1, len(result["stub_summary"]))
        self.assertEqual("PP", result["stub_summary"][0]["material"])
        self.assertEqual(150, result["stub_summary"][0]["dn_mm"])
        self.assertEqual(3, sum(row["shaft_count"] for row in result["shaft_summary"]))

    def test_visible_sheets_never_expose_internal_ids(self):
        sheets = reporting.xlsx_sheets(_report())
        self.assertEqual("00_Summen", sheets[0]["name"])
        text = repr(sheets)
        for internal in ("INTERNAL-P1", "INTERNAL-P2", "INTERNAL-B1",
                         "INTERNAL-S1", "INTERNE-NETZ-ID"):
            self.assertNotIn(internal, text)
        self.assertIn("H-RW.002", text)

    def test_summary_and_detail_worksheets_are_separate(self):
        report = _report()
        summary = reporting.worksheet_rows(report, summary=True)
        detail = reporting.worksheet_rows(report, summary=False)
        self.assertIn("00 Summen", repr(summary))
        self.assertNotIn("01 Kanalhaltungen", repr(summary))
        self.assertIn("01 Kanalhaltungen", repr(detail))
        self.assertNotIn("00 Summen", repr(detail))


class ExcelExportTests(unittest.TestCase):
    def test_excel_export_is_a_parseable_ooxml_workbook(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "mengen.xlsx")
            self.assertEqual(target, reporting.export_xlsx(target, _report()))
            with zipfile.ZipFile(target) as archive:
                self.assertIsNone(archive.testzip())
                names = set(archive.namelist())
                self.assertIn("xl/workbook.xml", names)
                self.assertEqual(6, len([
                    name for name in names if name.startswith("xl/worksheets/sheet")]))
                for name in names:
                    if name.endswith(".xml"):
                        element_tree.fromstring(archive.read(name))

    def test_save_dialog_adds_xlsx_extension(self):
        fake_vs = types.SimpleNamespace(
            PutFile=lambda _prompt, _default: r"C:\Temp\Kanal-Mengen",
            DidCancel=lambda: False,
        )
        with mock.patch.object(app, "vs", fake_vs):
            self.assertEqual(r"C:\Temp\Kanal-Mengen.xlsx", app._save_path("Vorgabe.xlsx"))


class RefreshBatchTests(unittest.TestCase):
    def setUp(self):
        reporting._REFRESHING = False
        reporting._LAST_REFRESH = None
        reporting._SUSPEND_DEPTH = 0
        reporting._PENDING_REFRESH = False

    def test_many_object_resets_cause_exactly_one_refresh(self):
        fake_vs = types.SimpleNamespace(GetObject=lambda _name: object())
        calls = []
        with mock.patch.object(reporting, "vs", fake_vs), mock.patch.object(
                reporting, "update_worksheet", side_effect=lambda show=False: calls.append(show)):
            reporting.begin_changes()
            self.assertFalse(reporting.refresh_existing())
            self.assertFalse(reporting.refresh_existing())
            self.assertTrue(reporting.end_changes(refresh=True))
        self.assertEqual([False], calls)


if __name__ == "__main__":
    unittest.main()
