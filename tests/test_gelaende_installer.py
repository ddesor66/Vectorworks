# -*- coding: utf-8 -*-
"""Prüfungen für die erzeugten Installer von pd_gelaende_quelldaten."""
import base64
import contextlib
import hashlib
import importlib.util
import io
import os
import shutil
import sys
import tempfile
import unittest

os.environ["PD_GELAENDE_QUELLDATEN_KEIN_AUTOSTART"] = "1"
os.environ["PD_GELAENDE_INSTALLER_KEIN_AUTOSTART"] = "1"

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, WURZEL)
sys.path.insert(0, os.path.join(WURZEL, "tests"))

import test_gelaende_quelldaten as werkzeugtest      # noqa: E402  (Fake-vs wiederverwenden)

from tools import build_gelaende_installer as bauer  # noqa: E402

QUELLE = os.path.join(WURZEL, "pd_gelaende_quelldaten.py")
INSTALLER_VW = os.path.join(WURZEL, "installer", "PD_Gelaende_Quelldaten_Installer.py")
INSTALLER_DESKTOP = os.path.join(WURZEL, "installer", "PD_Gelaende_Quelldaten_Setup.py")


def lesen(pfad):
    with open(pfad, "rb") as datei:
        return datei.read()


def modul_laden(name, pfad):
    spezifikation = importlib.util.spec_from_file_location(name, pfad)
    modul = importlib.util.module_from_spec(spezifikation)
    spezifikation.loader.exec_module(modul)
    return modul


class InstallerVS(werkzeugtest.FakeVS):
    """Fake-vs mit Benutzer-Plug-ins-Ordner."""

    def __init__(self, ordner):
        super().__init__()
        self.ordner = ordner

    def GetFolderPath(self, art):
        self.abgefragte_art = art
        return self.ordner

    def AlrtDialog(self, text):
        self.meldungen.append(text)


class BauTest(unittest.TestCase):
    def test_erzeugte_dateien_sind_aktuell(self):
        """Die eingecheckten Installer müssen zum Skriptstand passen."""
        vorher = {pfad: lesen(pfad) for pfad in (INSTALLER_VW, INSTALLER_DESKTOP)}
        ordner = tempfile.mkdtemp()
        try:
            erzeugt = bauer.bauen(ausgabe=ordner)
            for pfad in erzeugt:
                neu = lesen(pfad)
                alt = vorher[os.path.join(WURZEL, "installer", os.path.basename(pfad))]
                self.assertEqual(
                    neu, alt,
                    "Installer neu bauen: python3 tools/build_gelaende_installer.py")
        finally:
            shutil.rmtree(ordner, ignore_errors=True)

    def test_payload_entspricht_dem_skript(self):
        modul = modul_laden("installer_vw_payload", INSTALLER_VW)
        quelle = lesen(QUELLE)
        self.assertEqual(base64.b64decode(modul.PAYLOAD.encode("ascii")), quelle)
        self.assertEqual(modul.PRUEFSUMME, hashlib.sha256(quelle).hexdigest())

    def test_beide_installer_tragen_denselben_inhalt(self):
        vw = modul_laden("installer_vw_gleich", INSTALLER_VW)
        desktop = modul_laden("installer_desktop_gleich", INSTALLER_DESKTOP)
        self.assertEqual(vw.PAYLOAD, desktop.PAYLOAD)
        self.assertEqual(vw.PRUEFSUMME, desktop.PRUEFSUMME)
        self.assertEqual(vw.VERSION, desktop.VERSION)
        self.assertEqual(vw.LOADER, desktop.LOADER)


class InstallationTest(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.ordner, ignore_errors=True)
        self.vw = modul_laden("installer_vw_lauf", INSTALLER_VW)

    def test_installation_schreibt_skript_und_loader(self):
        api = InstallerVS(self.ordner)
        ergebnis = self.vw.ausfuehren(api)
        self.assertIsNotNone(ergebnis)
        self.assertEqual(api.abgefragte_art, -2)
        ziel = os.path.join(self.ordner, "pd_gelaende_quelldaten.py")
        self.assertTrue(os.path.isfile(ziel))
        self.assertEqual(lesen(ziel), lesen(QUELLE))
        self.assertTrue(os.path.isfile(
            os.path.join(self.ordner, self.vw.LOADER_DATEI)))
        self.assertIn("Neu installiert", api.meldungen[-1])

    def test_zweiter_lauf_meldet_aktualisierung(self):
        api = InstallerVS(self.ordner)
        self.vw.ausfuehren(api)
        ergebnis = self.vw.ausfuehren(api)
        self.assertEqual(ergebnis["vorher"], self.vw.VERSION)
        self.assertIn("Aktualisiert", api.meldungen[-1])

    def test_beschaedigter_inhalt_wird_nicht_geschrieben(self):
        self.vw.PAYLOAD = base64.b64encode(b"kaputt").decode("ascii")
        api = InstallerVS(self.ordner)
        self.assertIsNone(self.vw.ausfuehren(api))
        self.assertIn("beschädigt", api.meldungen[-1])
        self.assertEqual(os.listdir(self.ordner), [])

    def test_fehlender_ordner_bricht_sauber_ab(self):
        api = InstallerVS(os.path.join(self.ordner, "gibtesnicht"))
        self.assertIsNone(self.vw.ausfuehren(api))
        self.assertIn("nicht gefunden", api.meldungen[-1])

    def test_loader_startet_das_installierte_werkzeug(self):
        api = InstallerVS(self.ordner)
        self.vw.ausfuehren(api)
        werkzeugtest.objekt(api, "p", 9, ((1.0, 1.0, 10.0),))
        api.markiert = ("p",)
        sys.modules.pop("pd_gelaende_quelldaten", None)
        namensraum = {"__name__": "loader_test"}
        sys.modules["vs"] = api
        try:
            exec(compile(self.vw.LOADER, "loader", "exec"), namensraum)
        finally:
            sys.modules.pop("vs", None)
            sys.modules.pop("pd_gelaende_quelldaten", None)
        self.assertEqual(
            os.path.dirname(os.path.abspath(namensraum["werkzeug"].__file__)),
            os.path.abspath(self.ordner))
        self.assertIn("3D-Punkte: 1", api.meldungen[-1])


class DesktopTest(unittest.TestCase):
    def setUp(self):
        self.heim = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.heim, ignore_errors=True)
        self.setup = modul_laden("installer_desktop_lauf", INSTALLER_DESKTOP)

    def _anlegen(self, *teile):
        pfad = os.path.join(self.heim, *teile)
        os.makedirs(pfad)
        return pfad

    def test_windows_ordner_wird_gefunden(self):
        ziel = self._anlegen("AppData", "Roaming", "Nemetschek", "Vectorworks",
                             "2026", "Plug-ins")
        self.assertEqual(
            self.setup.zielordner(startpunkt=self.heim, plattform="win32"), ziel)

    def test_mac_ordner_wird_gefunden(self):
        ziel = self._anlegen("Library", "Application Support", "Vectorworks",
                             "2026", "Plug-ins")
        self.assertEqual(
            self.setup.zielordner(startpunkt=self.heim, plattform="darwin"), ziel)

    def test_neuester_jahrgang_hat_vorrang(self):
        neu = self._anlegen("Library", "Application Support", "Vectorworks",
                            "2026", "Plug-ins")
        self._anlegen("Library", "Application Support", "Vectorworks",
                      "2025", "Plug-ins")
        self.assertEqual(
            self.setup.zielordner(startpunkt=self.heim, plattform="darwin"), neu)

    def test_ohne_fund_kommt_verstaendlicher_hinweis(self):
        with self.assertRaises(self.setup.InstallationsFehler) as fehler:
            self.setup.zielordner(startpunkt=self.heim, plattform="darwin")
        self.assertIn("--ziel", str(fehler.exception))

    def test_vorgegebener_ordner_wird_verwendet(self):
        ziel = self._anlegen("eigener")
        ergebnis = self.setup.installieren(self.setup.zielordner(ziel))
        self.assertEqual(ergebnis["ziel"],
                         os.path.join(ziel, "pd_gelaende_quelldaten.py"))
        self.assertEqual(lesen(ergebnis["ziel"]), lesen(QUELLE))

    def _main(self, argumente):
        ausgabe = io.StringIO()
        with contextlib.redirect_stdout(ausgabe):
            code = self.setup.main(argumente)
        return code, ausgabe.getvalue()

    def test_main_meldet_erfolg(self):
        ziel = self._anlegen("eigener")
        code, ausgabe = self._main(["--ziel", ziel])
        self.assertEqual(code, 0)
        self.assertIn("Installation abgeschlossen", ausgabe)

    def test_main_meldet_fehlenden_ordner(self):
        code, ausgabe = self._main(["--ziel", os.path.join(self.heim, "weg")])
        self.assertEqual(code, 1)
        self.assertIn("existiert nicht", ausgabe)

    def test_main_zeigt_gefundene_ordner_ohne_zu_schreiben(self):
        code, ausgabe = self._main(["--zeigen"])
        self.assertEqual(code, 0)
        self.assertIn("Plug-ins-Ordner", ausgabe)


if __name__ == "__main__":
    unittest.main()
