import importlib
import sys
import types
import unittest


class FakeDialogVS(types.ModuleType):
    """Model the Vectorworks rule that popup choices exist only after INIT."""

    def __init__(self):
        super().__init__("vs")
        self.choices = {}
        self.selections = {}
        self.in_init = False

    def CreateResizableLayout(self, *_args): return 100
    def CreatePushButton(self, *_args): return None
    def CreateStaticText(self, *_args): return None
    def CreatePullDownMenu(self, *_args): return None
    def CreateEditText(self, *_args): return None
    def CreateEditInteger(self, *_args): return None
    def CreateEditReal(self, *_args): return None
    def CreateCheckBox(self, *_args): return None
    def SetBooleanItem(self, *_args): return None
    def SetFirstLayoutItem(self, *_args): return None
    def SetRightItem(self, *_args): return None
    def SetBelowItem(self, *_args): return None
    def VerifyLayout(self, *_args): return True

    def AddChoice(self, _dialog, item, value, index):
        if self.in_init:
            self.choices.setdefault(item, []).insert(index, value)

    def SelectChoice(self, _dialog, item, index, state):
        if self.in_init and state:
            self.selections[item] = index

    def RunLayoutDialog(self, _dialog, handler):
        self.in_init = True
        try:
            handler(12255, 0)
        finally:
            self.in_init = False
        return 2


def load_ui(fake):
    sys.modules["vs"] = fake
    name = "PD_GelaendeBaugruben.ui"
    sys.modules.pop(name, None)
    return importlib.import_module(name)


class TerrainDialogTests(unittest.TestCase):
    def test_model_management_choices_are_added_during_init(self):
        fake = FakeDialogVS()
        ui = load_ui(fake)

        self.assertIsNone(ui.model_options(("DGM Bestand", "DGM Soll")))

        self.assertEqual([
            "Registrieren / Metadaten ändern",
            "Sollvariante duplizieren",
            "Verwaltete Sollvariante löschen",
        ], fake.choices[20])
        self.assertEqual(["DGM Bestand", "DGM Soll"], fake.choices[21])
        self.assertEqual(["Bestand", "Soll"], fake.choices[24])
        self.assertEqual(
            ["– keine –", "DGM Bestand", "DGM Soll"], fake.choices[25])
        self.assertEqual({20: 0, 21: 0, 24: 0, 25: 0}, fake.selections)

    def test_excavation_model_and_unit_choices_are_added_during_init(self):
        fake = FakeDialogVS()
        ui = load_ui(fake)

        self.assertIsNone(ui.excavation_options(("DGM Bestand",)))

        self.assertEqual(["DGM Bestand"], fake.choices[20])
        self.assertEqual(["1:n", "Prozent", "Grad"], fake.choices[25])
        self.assertEqual({20: 0, 25: 0}, fake.selections)

    def test_comparison_models_are_added_during_init(self):
        fake = FakeDialogVS()
        ui = load_ui(fake)

        self.assertIsNone(ui.comparison_options(("DGM Bestand", "DGM Soll")))

        self.assertEqual(["DGM Bestand", "DGM Soll"], fake.choices[20])
        self.assertEqual(["DGM Bestand", "DGM Soll"], fake.choices[21])
        self.assertEqual({20: 0, 21: 1}, fake.selections)


if __name__ == "__main__":
    unittest.main()
