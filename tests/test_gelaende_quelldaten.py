# -*- coding: utf-8 -*-
"""Regressionsprüfungen für das eigenständige Skript pd_gelaende_quelldaten."""
import importlib
import os
import sys
import types
import unittest

os.environ["PD_GELAENDE_QUELLDATEN_KEIN_AUTOSTART"] = "1"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

quelldaten = importlib.import_module("pd_gelaende_quelldaten")

PUNKT_3D = quelldaten.TYP_PUNKT_3D
POLYGON_3D = quelldaten.TYP_POLYGON_3D


class FakeVS(types.ModuleType):
    """Nachbildung der im Skript verwendeten vs-Aufrufe."""

    def __init__(self, einheiten_pro_zoll=0.0254):
        super().__init__("vs")
        self.einheiten_pro_zoll = einheiten_pro_zoll
        self.typen = {}
        self.punkte = {}
        self.texte = {}
        self.kinder = {}
        self.geschlossen = set()
        self.ebenen = {}
        self.ebenen_hoehe_mm = {}
        self.markiert = ()
        self.objekte = {}
        self.aktive_klasse = "Keine"
        self.aktive_ebene = "Bestand"
        self.neue_objekte = []
        self.letztes_objekt = None
        self.poly_puffer = None
        self.klassen = {}
        self.geloescht = []
        self.meldungen = []
        self.auswahl_kriterium = None
        self.undo = None

    # --- Lesen -----------------------------------------------------------
    def GetUnits(self):
        return (0, 0, 0, self.einheiten_pro_zoll)

    def GetTypeN(self, handle):
        return self.typen.get(handle, 0)

    def GetLayer(self, handle):
        return self.ebenen.get(handle)

    def GetLayerElevation(self, ebene):
        return (self.ebenen_hoehe_mm.get(ebene, 0.0), 0.0)

    def GetLocus3D(self, handle):
        return self.punkte[handle][0]

    def GetPolyPt3D(self, handle, index):
        return self.punkte[handle][index]

    def GetPolyPt(self, handle, index):
        return self.punkte[handle][index - 1][:2]

    def GetVertNum(self, handle):
        return len(self.punkte[handle])

    def IsPolyClosed(self, handle):
        return handle in self.geschlossen

    def GetText(self, handle):
        return self.texte.get(handle, "")

    def GetTextOrigin(self, handle):
        return self.punkte[handle][0][:2]

    def Get3DCntr(self, handle):
        return self.punkte[handle][0]

    def GetSegPt1(self, handle):
        return self.punkte[handle][0][:2]

    def GetSegPt2(self, handle):
        return self.punkte[handle][1][:2]

    def GetLocPt(self, handle):
        return self.punkte[handle][0][:2]

    def GetSymLoc3D(self, handle):
        return self.punkte[handle][0]

    def GetParametricRecord(self, handle):
        return self.objekte.get(handle)

    def GetName(self, handle):
        return str(handle or "")

    def FInGroup(self, handle):
        werte = self.kinder.get(handle, ())
        return werte[0] if werte else None

    def NextObj(self, handle):
        for werte in self.kinder.values():
            if handle in werte:
                index = werte.index(handle) + 1
                return werte[index] if index < len(werte) else None
        return None

    # --- Auswahl ---------------------------------------------------------
    def ForEachObject(self, rueckruf, kriterium):
        self.kriterium = kriterium
        for handle in self.markiert:
            rueckruf(handle)

    def ForEachObjectInLayer(self, rueckruf, _objopt, _tief, _ebenen):
        for handle in self.markiert:
            rueckruf(handle)

    def FSActLayer(self):
        return self.markiert[0] if self.markiert else None

    def NextSObj(self, handle):
        if handle in self.markiert:
            index = self.markiert.index(handle) + 1
            return self.markiert[index] if index < len(self.markiert) else None
        return None

    def Selected(self, handle):
        return handle in self.markiert

    # --- Schreiben -------------------------------------------------------
    def ActiveClass(self):
        return self.aktive_klasse

    def NameClass(self, name):
        self.aktive_klasse = name
        self.klassen.setdefault(name, {})
        self.objekte.setdefault(name, name)

    def GetObject(self, name):
        return self.objekte.get(name)

    def SetPenFore(self, handle, farbe):
        self.klassen.setdefault(handle, {})["stift"] = farbe

    def SetFillFore(self, handle, farbe):
        self.klassen.setdefault(handle, {})["fuellung"] = farbe

    def CreateLayer(self, name, _art):
        self.objekte[name] = name
        self.ebenen_hoehe_mm[name] = 0.0
        return name

    def Layer(self, name):
        self.aktive_ebene = name

    def ActLayer(self):
        return self.aktive_ebene

    def GetLName(self, ebene):
        return str(ebene or "")

    def _neu(self, typ, punkte):
        handle = "neu%d" % (len(self.neue_objekte) + 1)
        self.typen[handle] = typ
        self.punkte[handle] = tuple(punkte)
        self.ebenen[handle] = self.aktive_ebene
        self.neue_objekte.append(handle)
        self.letztes_objekt = handle
        return handle

    def Locus3D(self, punkt):
        self._neu(PUNKT_3D, (tuple(punkt),))

    def BeginPoly3D(self):
        self.poly_puffer = []

    def Add3DPt(self, punkt):
        self.poly_puffer.append(tuple(punkt))

    def EndPoly3D(self):
        self._neu(POLYGON_3D, tuple(self.poly_puffer))
        self.poly_puffer = None

    def LNewObj(self):
        return self.letztes_objekt

    def SetClass(self, handle, name):
        self.klassen.setdefault(handle, {})["klasse"] = name

    def SetPolyClosed(self, handle, wert):
        if wert:
            self.geschlossen.add(handle)

    def SetFPat(self, handle, wert):
        pass

    def SetLW(self, handle, wert):
        pass

    def DSelectAll(self):
        self.auswahl = ()

    def SelectObj(self, kriterium):
        self.auswahl_kriterium = kriterium
        self.auswahl = tuple(self.neue_objekte)

    def Count(self, kriterium):
        auf_ebene = [h for h in self.neue_objekte
                     if "(L='%s')" % self.ebenen.get(h, "") in kriterium]
        if "T=%d" % PUNKT_3D in kriterium:
            return sum(1 for h in auf_ebene if self.typen[h] == PUNKT_3D)
        if "T=%d" % POLYGON_3D in kriterium:
            return sum(1 for h in auf_ebene if self.typen[h] == POLYGON_3D)
        return sum(1 for h in auf_ebene if h in getattr(self, "auswahl", ()))

    def NameUndoEvent(self, name):
        self.undo = name

    def ReDrawAll(self):
        pass

    def DelObject(self, handle):
        self.geloescht.append(handle)

    def AlertInform(self, text, _hinweis, _hilfe):
        self.meldungen.append(text)

    def Message(self, text):
        self.meldungen.append(text)

    def ClrMessage(self):
        pass

    def HDuplicate(self, handle, _dx, _dy):
        return None

    def ConvertTo3DPolys(self, handle):
        return None


def objekt(api, handle, typ, punkte, ebene="Bestand", geschlossen=False, text=None):
    api.typen[handle] = typ
    api.punkte[handle] = tuple(punkte)
    api.ebenen[handle] = ebene
    api.ebenen_hoehe_mm.setdefault(ebene, 0.0)
    if geschlossen:
        api.geschlossen.add(handle)
    if text is not None:
        api.texte[handle] = text
    return handle


class LeseTest(unittest.TestCase):
    def setUp(self):
        self.api = FakeVS()

    def elemente(self, handle):
        return quelldaten.elemente_aus_objekt(self.api, handle, 1.0, 0.05)

    def test_3d_punkt_erhaelt_ebenenhoehe(self):
        objekt(self.api, "p", quelldaten.TYP_PUNKT_3D, ((10.0, 20.0, 5.0),))
        self.api.ebenen_hoehe_mm["Bestand"] = 3000.0        # 3,0 m Ebenenbasis
        element = self.elemente("p")[0]
        self.assertEqual(element["art"], "punkt")
        self.assertAlmostEqual(element["punkte"][0][2], 8.0)
        self.assertTrue(element["hoehe_bekannt"])

    def test_3d_polygon_bleibt_bruchkante(self):
        objekt(self.api, "b", quelldaten.TYP_POLYGON_3D,
               ((0.0, 0.0, 100.0), (10.0, 0.0, 101.5)))
        element = self.elemente("b")[0]
        self.assertEqual(element["art"], "kante")
        self.assertEqual(len(element["punkte"]), 2)

    def test_geschlossenes_3d_polygon_ist_kontur(self):
        objekt(self.api, "k", quelldaten.TYP_POLYGON_3D,
               ((0.0, 0.0, 5.0), (1.0, 0.0, 5.0), (1.0, 1.0, 5.0)), geschlossen=True)
        self.assertEqual(self.elemente("k")[0]["art"], "kontur")

    def test_text_ohne_hoehe_liest_zahl_aus_inhalt(self):
        objekt(self.api, "t", quelldaten.TYP_TEXT, ((5.0, 6.0, 0.0),), text="H=102,65")
        element = self.elemente("t")[0]
        self.assertAlmostEqual(element["punkte"][0][2], 102.65)
        self.assertTrue(element["hoehe_bekannt"])

    def test_text_mit_mehreren_zahlen_bleibt_ohne_hoehe(self):
        objekt(self.api, "t", quelldaten.TYP_TEXT, ((5.0, 6.0, 0.0),), text="P12 102,65")
        self.assertFalse(self.elemente("t")[0]["hoehe_bekannt"])

    def test_text_mit_echter_3d_hoehe_behaelt_objekthoehe(self):
        objekt(self.api, "t", quelldaten.TYP_TEXT, ((5.0, 6.0, 77.0),), text="102,65")
        self.assertAlmostEqual(self.elemente("t")[0]["punkte"][0][2], 77.0)

    def test_textzahl_wird_in_dokumenteinheiten_umgerechnet(self):
        api = FakeVS(einheiten_pro_zoll=25.4)               # Dokument in Millimetern
        objekt(api, "t", quelldaten.TYP_TEXT, ((0.0, 0.0, 0.0),), text="102,65")
        faktor = quelldaten.meter_pro_einheit(api)
        element = quelldaten.elemente_aus_objekt(api, "t", faktor, 0.05)[0]
        self.assertAlmostEqual(element["punkte"][0][2], 102650.0, places=3)

    def test_linie_wird_bruchkante_mit_zwei_punkten(self):
        objekt(self.api, "l", quelldaten.TYP_LINIE, ((0.0, 0.0, 12.0), (5.0, 5.0, 12.0)))
        element = self.elemente("l")[0]
        self.assertEqual(element["art"], "kante")
        self.assertEqual(element["punkte"],
                         ((0.0, 0.0, 12.0), (5.0, 5.0, 12.0)))

    def test_polylinie_uebernimmt_alle_stuetzpunkte(self):
        objekt(self.api, "pl", quelldaten.TYP_POLYLINIE,
               ((0.0, 0.0, 9.0), (1.0, 0.0, 9.0), (2.0, 1.0, 9.0)))
        element = self.elemente("pl")[0]
        self.assertEqual(len(element["punkte"]), 3)
        self.assertTrue(all(punkt[2] == 9.0 for punkt in element["punkte"]))

    def test_gruppe_wird_rekursiv_gelesen(self):
        objekt(self.api, "g", quelldaten.TYP_GRUPPE, ((0.0, 0.0, 0.0),))
        objekt(self.api, "g1", quelldaten.TYP_PUNKT_3D, ((1.0, 1.0, 4.0),))
        objekt(self.api, "g2", quelldaten.TYP_PUNKT_3D, ((2.0, 2.0, 5.0),))
        self.api.kinder["g"] = ("g1", "g2")
        elemente = self.elemente("g")
        self.assertEqual(len(elemente), 2)
        self.assertEqual({e["punkte"][0][2] for e in elemente}, {4.0, 5.0})

    def test_symbol_wird_einfuegepunkt(self):
        objekt(self.api, "s", quelldaten.TYP_SYMBOL, ((3.0, 4.0, 15.5),))
        element = self.elemente("s")[0]
        self.assertEqual(element["art"], "punkt")
        self.assertAlmostEqual(element["punkte"][0][2], 15.5)

    def test_mesh_liefert_jeden_eckpunkt(self):
        objekt(self.api, "m", quelldaten.TYP_MESH,
               ((0.0, 0.0, 1.0), (1.0, 0.0, 2.0), (1.0, 1.0, 3.0)))
        self.api.GetMeshVertsCnt = lambda handle: len(self.api.punkte[handle])
        self.api.GetMeshVertex = lambda handle, index: self.api.punkte[handle][index]
        elemente = self.elemente("m")
        self.assertEqual(len(elemente), 3)
        self.assertTrue(all(e["art"] == "punkt" for e in elemente))

    def test_unbekannter_typ_liefert_mittelpunkt(self):
        objekt(self.api, "x", 999, ((7.0, 8.0, 21.0),))
        element = self.elemente("x")[0]
        self.assertEqual(element["punkte"], ((7.0, 8.0, 21.0),))


class PruefTest(unittest.TestCase):
    def test_ohne_hoehe_wird_nicht_uebernommen(self):
        elemente = (quelldaten._element("punkt", ((0.0, 0.0, 0.0),), False, 10),)
        verwendbar, verworfen = quelldaten.elemente_pruefen(elemente, 1.0)
        self.assertEqual(verwendbar, ())
        self.assertEqual(verworfen[quelldaten.GRUND_OHNE_HOEHE], 1)

    def test_dubletten_werden_zusammengefasst(self):
        elemente = (quelldaten._element("punkt", ((1.0, 1.0, 5.0),), True, 9),
                    quelldaten._element("punkt", ((1.0, 1.0, 5.0),), True, 9),
                    quelldaten._element("punkt", ((1.0, 1.0, 6.0),), True, 9))
        verwendbar, verworfen = quelldaten.elemente_pruefen(elemente, 1.0)
        self.assertEqual(len(verwendbar), 2)
        self.assertEqual(verworfen[quelldaten.GRUND_DUBLETTE], 1)

    def test_deckungsgleiche_bruchkanten_werden_zusammengefasst(self):
        punkte = ((0.0, 0.0, 5.0), (10.0, 0.0, 6.0))
        elemente = (quelldaten._element("kante", punkte, True, 2),
                    quelldaten._element("kante", punkte, True, 2))
        verwendbar, verworfen = quelldaten.elemente_pruefen(elemente, 1.0)
        self.assertEqual(len(verwendbar), 1)
        self.assertEqual(verworfen[quelldaten.GRUND_DUBLETTE], 1)

    def test_unplausible_hoehe_wird_verworfen(self):
        elemente = (quelldaten._element("punkt", ((0.0, 0.0, 99000.0),), True, 9),)
        verwendbar, verworfen = quelldaten.elemente_pruefen(elemente, 1.0)
        self.assertEqual(verwendbar, ())
        self.assertEqual(verworfen[quelldaten.GRUND_UNPLAUSIBEL], 1)


class AusgabeTest(unittest.TestCase):
    def setUp(self):
        self.api = FakeVS()

    def test_punkte_und_kanten_werden_erzeugt_und_markiert(self):
        elemente = (quelldaten._element("punkt", ((1.0, 2.0, 3.0),), True, 9),
                    quelldaten._element("kante", ((0.0, 0.0, 1.0), (4.0, 0.0, 2.0)),
                                        True, 2))
        name, erzeugt, pruefung = quelldaten.quelldaten_schreiben(
            self.api, elemente, 1.0)
        self.assertEqual(name, quelldaten.ZIEL_EBENE)
        self.assertEqual(len(erzeugt), 2)
        self.assertEqual(pruefung["punkte"], 1)
        self.assertEqual(pruefung["kanten"], 1)
        self.assertEqual(pruefung["markiert"], 2)
        self.assertEqual(self.api.aktive_ebene, quelldaten.ZIEL_EBENE)
        self.assertEqual(self.api.undo, "Gelände-Quelldaten erzeugen")
        self.assertEqual(self.api.klassen["neu1"]["klasse"], quelldaten.KLASSE_PUNKT)
        self.assertEqual(self.api.klassen["neu2"]["klasse"], quelldaten.KLASSE_KANTE)

    def test_ebenenhoehe_wird_beim_schreiben_abgezogen(self):
        self.api.ebenen_hoehe_mm[quelldaten.ZIEL_EBENE] = 0.0
        original_create = self.api.CreateLayer

        def create(name, art):
            handle = original_create(name, art)
            self.api.ebenen_hoehe_mm[name] = 2000.0          # 2,0 m Ebenenbasis
            return handle

        self.api.CreateLayer = create
        elemente = (quelldaten._element("punkt", ((0.0, 0.0, 10.0),), True, 9),)
        quelldaten.quelldaten_schreiben(self.api, elemente, 1.0)
        self.assertAlmostEqual(self.api.punkte["neu1"][0][2], 8.0)

    def test_unvollstaendige_ausgabe_wird_zurueckgerollt(self):
        self.api.Count = lambda kriterium: 0
        elemente = (quelldaten._element("punkt", ((0.0, 0.0, 1.0),), True, 9),)
        with self.assertRaises(quelldaten.QuelldatenFehler):
            quelldaten.quelldaten_schreiben(self.api, elemente, 1.0)
        self.assertIn("neu1", self.api.geloescht)
        self.assertIn(quelldaten.ZIEL_EBENE, self.api.geloescht)

    def test_zweiter_lauf_erhaelt_eigene_ebene(self):
        elemente = (quelldaten._element("punkt", ((0.0, 0.0, 1.0),), True, 9),)
        quelldaten.quelldaten_schreiben(self.api, elemente, 1.0)
        name, _erzeugt, _pruefung = quelldaten.quelldaten_schreiben(
            self.api, elemente, 1.0)
        self.assertEqual(name, quelldaten.ZIEL_EBENE + "-2")


class AblaufTest(unittest.TestCase):
    def test_auswahl_wird_ohne_dubletten_zusammengefuehrt(self):
        api = FakeVS()
        api.markiert = ("a", "b", "c")
        self.assertEqual(quelldaten.markierte_objekte(api), ("a", "b", "c"))

    def test_gesamtablauf_erzeugt_quelldaten(self):
        api = FakeVS()
        objekt(api, "p", quelldaten.TYP_PUNKT_3D, ((1.0, 1.0, 10.0),))
        objekt(api, "t", quelldaten.TYP_TEXT, ((2.0, 2.0, 0.0),), text="12,50")
        objekt(api, "l", quelldaten.TYP_LINIE, ((0.0, 0.0, 5.0), (3.0, 0.0, 5.0)))
        api.markiert = ("p", "t", "l")
        ergebnis = quelldaten.quelldaten_erzeugen(api)
        self.assertIsNotNone(ergebnis)
        name, erzeugt = ergebnis
        self.assertEqual(name, quelldaten.ZIEL_EBENE)
        self.assertEqual(len(erzeugt), 3)
        self.assertIn("3D-Punkte: 2", api.meldungen[-1])
        self.assertIn("3D-Bruchkanten/-konturen: 1", api.meldungen[-1])

    def test_leere_auswahl_meldet_hinweis(self):
        api = FakeVS()
        self.assertIsNone(quelldaten.quelldaten_erzeugen(api))
        self.assertIn("keine Objekte markiert", api.meldungen[-1])

    def test_nur_hoehenlose_objekte_melden_ursache(self):
        api = FakeVS()
        objekt(api, "l", quelldaten.TYP_LINIE, ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)))
        api.markiert = ("l",)
        self.assertIsNone(quelldaten.quelldaten_erzeugen(api))
        self.assertIn("keine verwendbaren", api.meldungen[-1])


if __name__ == "__main__":
    unittest.main()
