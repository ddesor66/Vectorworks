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

from PD_KanalLeitungMengen import app, core, reporting, ui
from PD_KanalTool import object_events as canal_object_events
from PD_KanalTool import settings as canal_settings
from PD_LeitungsTool import object_events as utility_object_events


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

    def test_equal_display_names_do_not_merge_independent_holdings(self):
        shafts = (_shaft("s1", "RW.001", 0.0, 100.0),
                  _shaft("s2", "RW.002", 10.0, 99.0),
                  _shaft("s3", "RW.003", 20.0, 100.0),
                  _shaft("s4", "RW.004", 30.0, 99.0))
        pipes = (_pipe("p1", "H-RW.002", "s1", "s2", 100.0, 99.0, 10.0),
                 _pipe("p2", "H-RW.002", "s3", "s4", 100.0, 99.0, 10.0))
        rows = core.analyze(pipes, shafts, ())["pipe_summary"]
        self.assertEqual(2, rows[0]["holding_count"])

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

    def test_user_can_select_summary_or_complete_individual_masses(self):
        report = _report()
        summary = reporting.xlsx_sheets(report, "summary")
        details = reporting.xlsx_sheets(report, "details")
        complete = reporting.xlsx_sheets(report, "all")
        self.assertEqual(["00_Summen"], [row["name"] for row in summary])
        self.assertNotIn("00_Summen", [row["name"] for row in details])
        self.assertIn("01_Kanalhaltungen", [row["name"] for row in details])
        self.assertIn("06_Stutzen", [row["name"] for row in details])
        self.assertIn("08_Einzelmassen_Summen", [row["name"] for row in details])
        self.assertEqual(1 + len(details), len(complete))

    def test_individual_mass_tables_contain_item_and_overall_totals(self):
        sheets = {row["name"]: row for row in reporting.detail_sheets(_report())}
        for name in ("01_Kanalhaltungen", "02_Schaechte", "03_Rigolen",
                     "04_Leitungen", "05_Erdmassen", "06_Stutzen"):
            self.assertIn("SUMME", repr(sheets[name]["rows"]))
        overall = repr(sheets["08_Einzelmassen_Summen"]["rows"])
        self.assertIn("Aushub gesamt", overall)
        self.assertIn("Oberbau gesamt", overall)
        self.assertIn("Wiederverfüllung gesamt", overall)
        self.assertIn("Verbau gesamt", overall)


class ExcelExportTests(unittest.TestCase):
    def test_excel_export_is_a_parseable_ooxml_workbook(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "mengen.xlsx")
            self.assertEqual(target, reporting.export_xlsx(target, _report()))
            with zipfile.ZipFile(target) as archive:
                self.assertIsNone(archive.testzip())
                names = set(archive.namelist())
                self.assertIn("xl/workbook.xml", names)
                self.assertEqual(9, len([
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

    def test_locked_existing_excel_target_gets_a_new_sibling_name(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "mengen.xlsx")
            with open(target, "wb") as stream:
                stream.write(b"already open")
            calls = []

            def writer(path, _sheets, creator=None):
                calls.append((path, creator))
                if len(calls) == 1:
                    raise PermissionError(13, "Zugriff verweigert", path)
                return path

            with mock.patch.object(reporting, "write_xlsx", side_effect=writer):
                result = reporting.export_xlsx(target, _report(), "details")
            self.assertEqual(target, calls[0][0])
            self.assertNotEqual(target, result)
            self.assertIn("mengen_neu_", os.path.basename(result))
            self.assertEqual(result, calls[1][0])

    def test_quantity_dialog_returns_saved_pavement_choice(self):
        class DialogAPI(object):
            def __init__(self):
                self.boolean = {}
                self.enabled = {}
                self.choices = []
                self.edit_real_creations = []
                self.edit_real_reads = []

            def __getattr__(self, name):
                if name.startswith(("Create", "SetFirst", "SetBelow", "SetRight")):
                    return lambda *args: 1
                raise AttributeError(name)

            def SetBooleanItem(self, _dialog, item, value):
                self.boolean[item] = bool(value)

            def GetBooleanItem(self, _dialog, item):
                return self.boolean.get(item, False)

            def EnableItem(self, _dialog, item, value):
                self.enabled[item] = bool(value)

            def AddChoice(self, _dialog, item, label, index):
                self.choices.append((item, label, index))

            def CreateEditReal(self, _dialog, item, value_type, value, width):
                self.edit_real_creations.append(
                    (item, value_type, value, width))

            def SelectChoice(self, *_args):
                return None

            def GetSelectedChoiceIndex(self, *_args):
                return 0

            def GetEditReal(self, _dialog, item, value_type):
                self.edit_real_reads.append((item, value_type))
                return True, 0.20

            def VerifyLayout(self, _dialog):
                return True

            def RunLayoutDialog(self, _dialog, handler):
                handler(ui.INIT, 0)
                return 1 if handler(1, 0) == 1 else 0

        api = DialogAPI()
        with mock.patch.object(ui, "vs", api):
            result = ui.action_dialog(
                False, 0, {"earthwork_include_pavement": True,
                           "earthwork_pavement_thickness_m": 0.20})
        self.assertEqual("worksheet", result["action"])
        self.assertEqual("summary", result["report_mode"])
        self.assertTrue(result["include_pavement"])
        self.assertEqual(0.20, result["pavement_thickness_m"])
        self.assertIn((20, "Alle Einzelmassen mit Summenzeilen", 1), api.choices)
        self.assertEqual([(18, 1, 0.20, 10)], api.edit_real_creations)
        self.assertEqual([(18, 1)], api.edit_real_reads)
        self.assertTrue(api.enabled[18])

    def test_legacy_centimetre_setting_is_migrated_to_metres(self):
        migrated = canal_settings.validate({
            "earthwork_include_pavement": True,
            "earthwork_pavement_thickness_cm": 20.0,
        })
        self.assertAlmostEqual(0.20, migrated["earthwork_pavement_thickness_m"])
        self.assertNotIn("earthwork_pavement_thickness_cm", migrated)


class RefreshBatchTests(unittest.TestCase):
    def setUp(self):
        reporting._REFRESHING = False
        reporting._LAST_REFRESH = None
        reporting._SUSPEND_DEPTH = 0
        reporting._PENDING_REFRESH = False
        reporting._REPORT_DIRTY = False

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

    def test_completed_drawing_only_marks_existing_report_dirty(self):
        fake_vs = types.SimpleNamespace(GetObject=lambda _name: object())
        with mock.patch.object(reporting, "vs", fake_vs), mock.patch.object(
                reporting, "update_worksheet") as update:
            reporting.begin_changes()
            self.assertTrue(reporting.end_changes(
                refresh=False, mark_dirty=True))
        update.assert_not_called()
        self.assertTrue(reporting._REPORT_DIRTY)

    def test_delete_observer_is_attached_to_canal_and_utility_objects_once(self):
        associations = []
        api = types.SimpleNamespace(
            AddAssociation=lambda owner, kind, target: (
                associations.append((owner, kind, target)) or True),
            RemoveAssociation=lambda _owner, _kind, _target: False,
            CreateCustomObjectN=lambda *_args: object(),
            GetObject=lambda _name: None)
        with mock.patch.object(reporting, "vs", api), mock.patch.object(
                reporting.canal_objects, "objects", return_value=(
                    ("PIPE", {"role": "sewer_pipe"}),
                    ("LABEL", {"role": "sewer_label"}))), mock.patch.object(
                reporting.utility_objects, "objects", return_value=(
                    ("ROUTE", {"role": "utility_route"}),)), mock.patch.object(
                reporting, "_delete_observer", return_value="OBSERVER"):
            self.assertEqual("OBSERVER", reporting.synchronize_delete_observer())
        self.assertEqual(
            [("PIPE", 5, "OBSERVER"), ("ROUTE", 5, "OBSERVER")],
            associations)

    def test_delete_observer_reset_only_marks_quantity_report_dirty(self):
        api = types.SimpleNamespace(
            vsoGetEventInfo=lambda: (3, 0),
            GetCustomObjectInfo=lambda: (True, "PD KAN Objekt", "OBSERVER", None, None))
        with mock.patch.object(canal_object_events, "vs", api), mock.patch.object(
                canal_object_events.live, "reset", return_value=None), mock.patch.object(
                canal_object_events.live_objects, "data_of", return_value={
                    "schema": 2,
                    "role": canal_object_events.live_objects.QUANTITY_OBSERVER_ROLE,
                }), mock.patch.object(reporting, "mark_existing_dirty", return_value=True) as dirty, mock.patch.object(
                reporting, "refresh_existing") as refresh:
            canal_object_events.run()
        dirty.assert_called_once_with()
        refresh.assert_not_called()

    def test_utility_reset_only_marks_quantity_report_dirty(self):
        api = types.SimpleNamespace(
            vsoGetEventInfo=lambda: (3, 0),
            GetCustomObjectInfo=lambda: (
                True, "PD Leitung Objekt", "ROUTE", None, None))
        with mock.patch.object(utility_object_events, "vs", api), mock.patch.object(
                utility_object_events.live, "reset", return_value=None), mock.patch.object(
                utility_object_events.live_objects, "data_of", return_value={
                    "role": utility_object_events.live_objects.ROLE,
                }), mock.patch.object(
                reporting, "mark_existing_dirty", return_value=True) as dirty, mock.patch.object(
                reporting, "refresh_existing") as refresh:
            utility_object_events.run()
        dirty.assert_called_once_with()
        refresh.assert_not_called()

    def test_live_report_drops_a_normally_deleted_holding(self):
        shafts = (
            ("S1", _shaft("s1", "RW.001", 0.0, 100.0)),
            ("S2", _shaft("s2", "RW.002", 10.0, 99.9)),
        )
        inventory = [("P1", _pipe(
            "p1", "H-RW.002", "s1", "s2", 100.0, 99.9, 10.0))]
        api = types.SimpleNamespace(
            GetFName=lambda: "Löschtest.vwx", GetFPathName=lambda: "")
        preferences = {
            "earthwork_include_pavement": False,
            "earthwork_pavement_thickness_m": 0.0,
        }
        with mock.patch.object(reporting, "vs", api), mock.patch.object(
                reporting.canal_live, "shaft_records", return_value=shafts), mock.patch.object(
                reporting.canal_live, "pipe_records", side_effect=lambda: tuple(inventory)), mock.patch.object(
                reporting.canal_live, "rigole_records", return_value=()), mock.patch.object(
                reporting.utility_objects, "objects", return_value=()), mock.patch.object(
                reporting.utility_objects, "object_errors", return_value=()):
            before = reporting.collect_live(preferences)
            inventory[:] = []  # Native Delete removed the PIO from the document.
            after = reporting.collect_live(preferences)
        self.assertEqual(1, len(before["canals"]))
        self.assertEqual(10.0, before["totals"]["canal_length_2d_m"])
        self.assertEqual(0, len(after["canals"]))
        self.assertEqual(0.0, after["totals"]["canal_length_2d_m"])


class WorksheetTransactionTests(unittest.TestCase):
    class Resource(object):
        def __init__(self, name):
            self.name = name
            self.deleted = False

    def test_detail_selection_creates_and_shows_only_detail_worksheet(self):
        resources = []
        shown = []

        def get_object(name):
            return next((row for row in resources
                         if not row.deleted and row.name == name), None)

        def create_ws(name, _rows, _columns):
            row = self.Resource(name)
            resources.append(row)
            return row

        api = types.SimpleNamespace(
            CreateWS=create_ws, GetObject=get_object,
            SetName=lambda handle, name: setattr(handle, "name", name),
            GetName=lambda handle: handle.name,
            DelObject=lambda handle: setattr(handle, "deleted", True),
            GetWSImage=lambda _handle: None,
            ShowWS=lambda handle, _show: shown.append(handle.name))
        rows = ({"kind": "normal", "values": ("x",)},)
        with mock.patch.object(reporting, "vs", api), mock.patch.object(
                reporting, "worksheet_rows", return_value=rows), mock.patch.object(
                reporting, "_populate", return_value=None):
            result = reporting.update_worksheet(
                {"prepared": True}, show=True, report_mode="details")
        self.assertEqual(reporting.WORKSHEET_NAME, result.name)
        self.assertEqual([reporting.WORKSHEET_NAME], shown)
        self.assertIsNone(get_object(reporting.SUMMARY_WORKSHEET_NAME))

    def test_second_install_failure_restores_both_old_worksheets(self):
        old_detail = self.Resource(reporting.WORKSHEET_NAME)
        old_summary = self.Resource(reporting.SUMMARY_WORKSHEET_NAME)
        resources = [old_detail, old_summary]

        def get_object(name):
            return next((row for row in resources
                         if not row.deleted and row.name == name), None)

        def create_ws(name, _rows, _columns):
            row = self.Resource(name)
            resources.append(row)
            return row

        install_count = {"value": 0}

        def set_name(handle, name):
            if name in (reporting.WORKSHEET_NAME, reporting.SUMMARY_WORKSHEET_NAME):
                install_count["value"] += 1
                if install_count["value"] == 2:
                    raise RuntimeError("injected second install failure")
            handle.name = name

        api = types.SimpleNamespace(
            CreateWS=create_ws, GetObject=get_object, SetName=set_name,
            GetName=lambda handle: handle.name,
            DelObject=lambda handle: setattr(handle, "deleted", True),
            GetWSImage=lambda _handle: None,
            ShowWS=lambda _handle, _show: None)
        rows = ({"kind": "normal", "values": ("x",)},)
        with mock.patch.object(reporting, "vs", api), mock.patch.object(
                reporting, "worksheet_rows", return_value=rows), mock.patch.object(
                reporting, "_populate", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "injected"):
                reporting.update_worksheet({"prepared": True}, show=False)
        self.assertIs(old_detail, get_object(reporting.WORKSHEET_NAME))
        self.assertIs(old_summary, get_object(reporting.SUMMARY_WORKSHEET_NAME))


if __name__ == "__main__":
    unittest.main()
