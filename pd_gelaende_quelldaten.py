# -*- coding: utf-8 -*-
"""PD Gelände-Quelldaten – markierte Objekte in DGM-taugliche Ausgangsdaten wandeln.

Das Skript liest ausnahmslos alle markierten Objekte, die Vectorworks im
3D-Raum lokalisieren kann, und legt daraus auf einer neuen Ebene genau die
beiden Objektarten an, die das Geländemodell von Vectorworks 2026 als
Ausgangsdaten akzeptiert:

* 3D-Punkte (``Locus3D``) für punktförmige Quellen,
* 3D-Polygone für Bruchkanten und Höhenlinien.

Die Originale werden weder verändert noch gelöscht. Am Ende sind die erzeugten
Quelldaten markiert, sodass direkt der native Befehl
``Landschaft > Geländemodell > Geländemodell aus Ausgangsdaten`` folgen kann.

Einsatz: Skript in der Skript-Palette (Python). Die Datei kann alternativ als
Menübefehl-Plug-in eingebunden werden; der Ablauf ist identisch.

Die Funktionen erhalten das ``vs``-Modul als Parameter ``api``, damit sie
außerhalb von Vectorworks getestet werden können.
"""
from __future__ import absolute_import

import math
import os
import re

# ------------------------------------------------------------- Einstellungen --
# Alles, was angepasst werden soll, steht hier oben.

ZIEL_EBENE = "Gelände-Quelldaten"          # Name der neu angelegten Konstruktionsebene
KLASSE_PUNKT = "Gelände-Quellpunkt"        # Klasse der erzeugten 3D-Punkte
KLASSE_KANTE = "Gelände-Bruchkante"        # Klasse der erzeugten 3D-Polygone
FARBE_PUNKT = (0, 45000, 0)                # Stiftfarbe der Punkte (RGB 0..65535)
FARBE_KANTE = (0, 25000, 50000)            # Stiftfarbe der Bruchkanten
LINIENSTAERKE_KANTE = 40                   # Stiftstärke der Bruchkanten in 1/100 mm

SEHNENTOLERANZ_M = 0.05                    # Abtastgenauigkeit für Bögen/Freihandkurven [m]
MAX_ABTASTPUNKTE = 10000                   # Obergrenze der Stützpunkte je abgetasteter Kurve

TEXTHOEHE_AUS_INHALT = True                # Text ohne echte 3D-Höhe: Zahl im Text als Höhe lesen
TEXTHOEHE_IN_METERN = True                 # False = die Zahl im Text gilt als Dokumenteinheit
SYMBOL_ALS_EINFUEGEPUNKT = True            # Symbole/Blöcke als ein Punkt am Einfügepunkt
                                           # (False = gesamte 3D-Geometrie des Symbols)

OHNE_HOEHE_UEBERNEHMEN = False             # True = auch Objekte ohne echte Höhe (Z = Ebenenbasis)
DUBLETTEN_ENTFERNEN = True                 # deckungsgleiche Punkte nur einmal ausgeben
DUBLETTEN_TOLERANZ_M = 0.005               # Fangmaß für deckungsgleiche Punkte [m]
HOEHE_MIN_M = -1000.0                      # Plausibilitätsfenster der Höhen [m]
HOEHE_MAX_M = 9000.0

FORTSCHRITT_ALLE = 250                     # Statusmeldung nach je so vielen gelesenen Objekten

# --------------------------------------------------------- Vectorworks-Typen --
TYP_LINIE = 2
TYP_RECHTECK = 3
TYP_OVAL = 4
TYP_POLYGON = 5
TYP_BOGEN = 6
TYP_FREIHAND = 8
TYP_PUNKT_3D = 9
TYP_TEXT = 10
TYP_GRUPPE = 11
TYP_RUNDRECHTECK = 13
TYP_SYMBOL = 15
TYP_PUNKT_2D = 17
TYP_POLYLINIE = 21
TYP_POLYGON_3D = 25
TYP_MESH = 40
TYP_PIO = 86
TYP_NURBS = 111

TYPNAMEN = {
    2: "Linie", 3: "Rechteck", 4: "Oval/Kreis", 5: "Polygon", 6: "Bogen",
    8: "Freihandlinie", 9: "3D-Punkt", 10: "Text", 11: "Gruppe",
    13: "Abgerundetes Rechteck", 15: "Symbol", 17: "2D-Punkt",
    21: "Polylinie", 24: "Extrusionskörper", 25: "3D-Polygon",
    31: "Gruppe (Ebenenverweis)", 40: "Mesh", 63: "Bemaßung",
    84: "Volumenkörper", 86: "Plug-in-Objekt", 111: "NURBS-Kurve",
    113: "NURBS-Fläche",
}

# Eine einzelne, eindeutige Zahl im Text, zum Beispiel "102.65" oder "H=102,65".
TEXTZAHL = re.compile(r"(?<![0-9.,])[-+]?\d+(?:[.,]\d+)?(?![0-9.,])")
# Plug-in-Objekte, die als Vermessungs-/Höhenpunkt gelten.
PIO_PUNKTNAMEN = ("stake", "vermessung", "survey", "hoehe", "höhe", "punkt", "point")

# Objekttypen mit eigenem, direktem Leseweg. Alles andere wird über eine
# temporäre Kopie in 3D-Polygone aufgelöst (Kreise, Rechtecke, Volumenkörper …).
DIREKTE_TYPEN = frozenset((
    TYP_LINIE, TYP_BOGEN, TYP_FREIHAND, TYP_PUNKT_3D, TYP_TEXT, TYP_POLYGON,
    TYP_POLYLINIE, TYP_POLYGON_3D, TYP_PUNKT_2D, TYP_PIO,
))

GRUND_OHNE_HOEHE = "ohne echte Höhe (liegt auf der Ebenenbasis)"
GRUND_UNPLAUSIBEL = "Höhe außerhalb des Plausibilitätsfensters"
GRUND_DUBLETTE = "deckungsgleicher Punkt"


class QuelldatenFehler(Exception):
    """Abbruch mit einer für den Anwender verständlichen Meldung."""


# ------------------------------------------------------------ Grundfunktionen --
def _zahl(wert):
    try:
        ergebnis = float(wert)
    except (TypeError, ValueError):
        return None
    return ergebnis if math.isfinite(ergebnis) else None


def typname(typ):
    return TYPNAMEN.get(int(typ or 0), "Objekttyp %d" % int(typ or 0))


def meter_pro_einheit(api):
    """Umrechnungsfaktor Dokumenteinheit -> Meter. ``GetUnits`` liefert Einheiten je Zoll."""
    try:
        einheiten_pro_zoll = float(api.GetUnits()[3])
    except (AttributeError, TypeError, ValueError, IndexError) as fehler:
        raise QuelldatenFehler(
            "Die Dokumenteinheiten konnten nicht gelesen werden.") from fehler
    if not math.isfinite(einheiten_pro_zoll) or einheiten_pro_zoll <= 0.0:
        raise QuelldatenFehler("Die Dokumenteinheiten sind ungültig.")
    return 0.0254 / einheiten_pro_zoll


def ebenen_basis(api, ebene, faktor):
    """Basishöhe einer Ebene in Dokumenteinheiten (GetLayerElevation liefert Millimeter)."""
    if not ebene:
        return 0.0
    try:
        return float(api.GetLayerElevation(ebene)[0]) / 1000.0 / faktor
    except (AttributeError, TypeError, ValueError, IndexError):
        return 0.0


def ebenen_hoehe(api, handle, faktor):
    """Basishöhe der Ebene, auf der ein Objekt liegt, in Dokumenteinheiten."""
    try:
        ebene = api.GetLayer(handle)
    except (AttributeError, TypeError):
        return 0.0
    return ebenen_basis(api, ebene, faktor)


def markierte_objekte(api):
    """Alle markierten Objekte über mehrere unabhängige Vectorworks-Wege lesen.

    Große Importauswahlen (DWG-Vermessungen) werden von einzelnen
    Auswahl-Iteratoren abgeschnitten. Deshalb werden die Ergebnisse mehrerer
    Wege in Auswahlreihenfolge zusammengeführt und entdoppelt.
    """
    ergebnis = []
    gesehen = set()

    def sammeln(handle):
        if handle and handle not in gesehen:
            gesehen.add(handle)
            ergebnis.append(handle)

    try:
        api.ForEachObject(sammeln, "(SEL=TRUE)")
    except (AttributeError, TypeError):
        pass
    try:
        handle = api.FSActLayer()
        kette = set()
        while handle and handle not in kette:
            kette.add(handle)
            sammeln(handle)
            handle = api.NextSObj(handle)
    except (AttributeError, TypeError):
        pass
    try:
        # objOptions 2 = nur markierte Objekte, traversal 2 = tief in Container,
        # layerOptions 1 = alle Ebenen.
        api.ForEachObjectInLayer(sammeln, 2, 2, 1)
    except (AttributeError, TypeError):
        pass

    def sammeln_wenn_markiert(handle):
        try:
            if api.Selected(handle):
                sammeln(handle)
        except (AttributeError, TypeError):
            pass

    try:
        api.ForEachObjectInLayer(sammeln_wenn_markiert, 0, 2, 1)
    except (AttributeError, TypeError):
        pass
    return tuple(ergebnis)


# ------------------------------------------------------------ Objekte lesen ---
def _element(art, punkte, bekannt, typ):
    return {"art": art, "punkte": tuple(punkte), "hoehe_bekannt": bool(bekannt),
            "typ": int(typ or 0)}


def _textzahl(api, handle):
    """Genau eine eindeutige Zahl aus dem Textinhalt lesen, sonst None."""
    try:
        inhalt = str(api.GetText(handle) or "").strip()
    except (AttributeError, TypeError):
        return None
    treffer = TEXTZAHL.findall(inhalt)
    if len(treffer) != 1:
        return None
    return _zahl(treffer[0].replace(",", "."))


def _kurve_abtasten(api, handle, sehne_einheiten):
    """Bogen/Freihandlinie über die Kurvenlänge in 2D-Stützpunkte zerlegen."""
    laenge = _zahl(api.HLength(handle)) or 0.0
    if laenge <= 0.0:
        return ()
    schritte = max(1, min(MAX_ABTASTPUNKTE,
                          int(math.ceil(laenge / max(sehne_einheiten, 1e-9)))))
    punkte = []
    for index in range(schritte + 1):
        wert = api.PointAlongPoly(handle, laenge * index / schritte)
        if not isinstance(wert, (tuple, list)) or len(wert) < 2 or not wert[0]:
            return ()
        punkt = wert[1]
        if not isinstance(punkt, (tuple, list)) or len(punkt) < 2:
            return ()
        punkte.append((float(punkt[0]), float(punkt[1])))
    return tuple(punkte)


def _bogen_abtasten(api, handle, sehne_einheiten):
    """Ersatzweg für importierte Bögen, die HLength/PointAlongPoly ablehnen."""
    try:
        mitte = api.HCenter(handle)
        start = api.GetSegPt1(handle)
        _startwinkel, oeffnung = api.GetArc(handle)
        radius = math.hypot(float(start[0]) - float(mitte[0]),
                            float(start[1]) - float(mitte[1]))
        bogen = math.radians(float(oeffnung))
        if radius <= 0.0 or abs(bogen) <= 1e-12:
            return ()
        schritte = max(1, min(MAX_ABTASTPUNKTE, int(math.ceil(
            abs(radius * bogen) / max(sehne_einheiten, 1e-9)))))
        winkel = math.atan2(float(start[1]) - float(mitte[1]),
                            float(start[0]) - float(mitte[0]))
        return tuple((float(mitte[0]) + radius * math.cos(winkel + bogen * i / schritte),
                      float(mitte[1]) + radius * math.sin(winkel + bogen * i / schritte))
                     for i in range(schritte + 1))
    except (AttributeError, TypeError, ValueError, IndexError):
        return ()


def _gruppeninhalt(api, handle):
    """Direkte Mitglieder einer Gruppe lesen, ohne das Original aufzulösen."""
    kind = api.FInGroup(handle)
    gesehen = set()
    while kind and kind not in gesehen:
        gesehen.add(kind)
        yield kind
        kind = api.NextObj(kind)


def _mesh_punkte(api, handle):
    """Jeden vorhandenen Mesh-Eckpunkt als eigenen 3D-Stützpunkt übernehmen."""
    try:
        anzahl = int(api.GetMeshVertsCnt(handle) or 0)
    except Exception:
        return ()
    ergebnis = []
    for index in range(max(0, anzahl)):
        try:
            x, y, z = api.GetMeshVertex(handle, index)
            ergebnis.append(_element("punkt", ((float(x), float(y), float(z)),),
                                     True, TYP_MESH))
        except (AttributeError, TypeError, ValueError, IndexError):
            continue
    return tuple(ergebnis)


def _konvertierte_3d_elemente(api, handle, ebene_z):
    """3D-Geometrie über eine temporäre Kopie lesen; die Kopie wird gelöscht.

    So liefern Kreise, Rechtecke, Symbole, Volumenkörper und andere importierte
    Fremdtypen ihre tatsächliche Geometrie statt nur eines Mittelpunkts.
    """
    kopie = None
    umgewandelt = None
    ergebnis = []

    def kandidaten(wurzel):
        yield wurzel
        try:
            ist_gruppe = int(api.GetTypeN(wurzel) or 0) == TYP_GRUPPE
        except (AttributeError, TypeError, ValueError):
            ist_gruppe = False
        if ist_gruppe:
            for kind in _gruppeninhalt(api, wurzel):
                for tiefer in kandidaten(kind):
                    yield tiefer

    try:
        kopie = api.HDuplicate(handle, 0.0, 0.0)
        if not kopie:
            return ()
        umgewandelt = api.ConvertTo3DPolys(kopie)
        if not umgewandelt:
            return ()
        for kandidat in kandidaten(umgewandelt):
            if int(api.GetTypeN(kandidat) or 0) != TYP_POLYGON_3D:
                continue
            # GetPolyPt3D liefert die wirksame Höhe einschließlich Ebenenbasis.
            punkte = tuple((float(x), float(y), float(z))
                           for x, y, z in (api.GetPolyPt3D(kandidat, index)
                                           for index in range(int(api.GetVertNum(kandidat) or 0))))
            if len(punkte) < 2:
                continue
            bekannt = any(abs(punkt[2] - ebene_z) > 1e-9 for punkt in punkte)
            art = "kontur" if api.IsPolyClosed(kandidat) else "kante"
            ergebnis.append(_element(art, punkte, bekannt, TYP_POLYGON_3D))
        return tuple(ergebnis)
    except Exception:
        return ()
    finally:
        try:
            if umgewandelt:
                api.DelObject(umgewandelt)
            elif kopie:
                api.DelObject(kopie)
        except Exception:
            pass


def _einfuegepunkt(api, handle, ebene_z, typ):
    """Symbol-/PIO-Einfügepunkt als 3D-Punkt lesen (Z ist ebenenrelativ)."""
    try:
        x, y, z = api.GetSymLoc3D(handle)
    except (AttributeError, TypeError, ValueError):
        return None
    hoehe = _zahl(z)
    if hoehe is None:
        return None
    return _element("punkt", ((float(x), float(y), hoehe + ebene_z),),
                    abs(hoehe) > 1e-9, typ)


def _ist_punkt_pio(api, handle):
    try:
        satz = api.GetParametricRecord(handle)
        name = str(api.GetName(satz) if satz else "").casefold()
    except (AttributeError, TypeError):
        return False
    return any(teil in name for teil in PIO_PUNKTNAMEN)


def _einzelelement(api, handle, faktor, sehne_einheiten):
    """Einen Objekttyp mit direktem Leseweg in ein Quellelement übersetzen."""
    typ = int(api.GetTypeN(handle) or 0)
    ebene_z = ebenen_hoehe(api, handle, faktor)

    if typ == TYP_PUNKT_3D:
        x, y, z = api.GetLocus3D(handle)
        return _element("punkt", ((float(x), float(y), float(z) + ebene_z),), True, typ)

    if typ == TYP_POLYGON_3D:
        punkte = tuple((float(x), float(y), float(z))
                       for x, y, z in (api.GetPolyPt3D(handle, index)
                                       for index in range(int(api.GetVertNum(handle) or 0))))
        if len(punkte) < 2:
            return None
        art = "kontur" if api.IsPolyClosed(handle) else "kante"
        return _element(art, punkte, True, typ)

    if typ == TYP_PIO and _ist_punkt_pio(api, handle):
        element = _einfuegepunkt(api, handle, ebene_z, typ)
        if element:
            return element

    # 2D-Geometrie besitzt oft keinen eigenen 3D-Mittelpunkt. Dann gilt die
    # Ebenenbasishöhe – das Objekt wird deswegen nicht verworfen.
    hat_3d_mitte = False
    try:
        mitte = api.Get3DCntr(handle)
        if not isinstance(mitte, (tuple, list)) or len(mitte) < 3:
            raise ValueError("kein 3D-Mittelpunkt")
        z_wert = float(mitte[2]) + ebene_z
        hat_3d_mitte = True
    except (AttributeError, TypeError, ValueError, IndexError):
        mitte = (0.0, 0.0, 0.0)
        z_wert = ebene_z
    bekannt = hat_3d_mitte and abs(z_wert - ebene_z) > 1e-9

    if typ == TYP_PUNKT_2D:
        try:
            x, y = api.GetLocPt(handle)
        except (AttributeError, TypeError, ValueError):
            return None
        return _element("punkt", ((float(x), float(y), z_wert),), bekannt, typ)

    if typ == TYP_TEXT:
        try:
            ursprung = api.GetTextOrigin(handle)
            x, y = float(ursprung[0]), float(ursprung[1])
        except (AttributeError, TypeError, ValueError, IndexError):
            x, y = float(mitte[0]), float(mitte[1])
        if TEXTHOEHE_AUS_INHALT and not bekannt:
            gelesen = _textzahl(api, handle)
            if gelesen is not None:
                z_wert = gelesen / faktor if TEXTHOEHE_IN_METERN else gelesen
                bekannt = True
        return _element("punkt", ((x, y, z_wert),), bekannt, typ)

    if typ == TYP_LINIE:
        erster, zweiter = api.GetSegPt1(handle), api.GetSegPt2(handle)
        punkte = ((float(erster[0]), float(erster[1]), z_wert),
                  (float(zweiter[0]), float(zweiter[1]), z_wert))
        return _element("kante", punkte, bekannt, typ)

    if typ in (TYP_POLYGON, TYP_POLYLINIE):
        punkte = tuple((float(x), float(y), z_wert)
                       for x, y in (api.GetPolyPt(handle, index)
                                    for index in range(1, int(api.GetVertNum(handle) or 0) + 1)))
        if len(punkte) < 2:
            return None
        art = "kontur" if api.IsPolyClosed(handle) else "kante"
        return _element(art, punkte, bekannt, typ)

    if typ in (TYP_BOGEN, TYP_FREIHAND):
        punkte_2d = _kurve_abtasten(api, handle, sehne_einheiten)
        if not punkte_2d and typ == TYP_BOGEN:
            punkte_2d = _bogen_abtasten(api, handle, sehne_einheiten)
        if len(punkte_2d) >= 2:
            return _element("kante", tuple((x, y, z_wert) for x, y in punkte_2d),
                            bekannt, typ)
        return None

    # Jedes andere im 3D-Raum lokalisierbare Objekt liefert wenigstens einen
    # Stützpunkt an seinem Vectorworks-3D-Mittelpunkt.
    if hat_3d_mitte:
        return _element("punkt", ((float(mitte[0]), float(mitte[1]), z_wert),), bekannt, typ)
    return None


def elemente_aus_objekt(api, handle, faktor, sehne_einheiten, vorfahren=()):
    """Ein markiertes Objekt vollständig in Quellelemente auflösen."""
    typ = int(api.GetTypeN(handle) or 0)

    if typ == TYP_MESH:
        punkte = _mesh_punkte(api, handle)
        if punkte:
            return punkte

    if typ == TYP_NURBS:
        try:
            punkte = tuple(tuple(float(wert) for wert in api.GetPolyPt3D(handle, index))
                           for index in range(int(api.GetVertNum(handle) or 0)))
        except (AttributeError, TypeError, ValueError, IndexError):
            punkte = ()
        if len(punkte) >= 2:
            return (_element("kante", punkte, True, typ),)

    if typ == TYP_GRUPPE:
        if handle in vorfahren:
            return ()
        ergebnis = []
        for kind in _gruppeninhalt(api, handle):
            ergebnis.extend(elemente_aus_objekt(
                api, kind, faktor, sehne_einheiten, vorfahren + (handle,)))
        if ergebnis:
            return tuple(ergebnis)

    if typ == TYP_SYMBOL and SYMBOL_ALS_EINFUEGEPUNKT:
        element = _einfuegepunkt(api, handle, ebenen_hoehe(api, handle, faktor), typ)
        if element:
            return (element,)

    if typ not in DIREKTE_TYPEN:
        umgewandelt = _konvertierte_3d_elemente(
            api, handle, ebenen_hoehe(api, handle, faktor))
        if umgewandelt:
            return umgewandelt

    element = _einzelelement(api, handle, faktor, sehne_einheiten)
    if element:
        return (element,)
    if typ == TYP_PIO:
        return _konvertierte_3d_elemente(api, handle, ebenen_hoehe(api, handle, faktor))
    return ()


def elemente_sammeln(api, handles, faktor, sehne_einheiten, melden=None):
    """Alle markierten Objekte lesen und nicht lesbare Typen protokollieren."""
    elemente = []
    unlesbar = {}
    for nummer, handle in enumerate(tuple(handles or ()), start=1):
        try:
            gefunden = elemente_aus_objekt(api, handle, faktor, sehne_einheiten)
        except Exception:
            gefunden = ()
        if gefunden:
            elemente.extend(gefunden)
        else:
            try:
                typ = int(api.GetTypeN(handle) or 0)
            except (AttributeError, TypeError, ValueError):
                typ = 0
            unlesbar[typ] = unlesbar.get(typ, 0) + 1
        if melden and FORTSCHRITT_ALLE > 0 and nummer % FORTSCHRITT_ALLE == 0:
            melden(nummer)
    return tuple(elemente), unlesbar


# ------------------------------------------------------------------ Prüfung ---
def elemente_pruefen(elemente, faktor):
    """Höhen prüfen, Dubletten zusammenfassen und die Ausgabemenge bilden."""
    verwendbar = []
    verworfen = {}
    gesehen = set()
    raster = max(DUBLETTEN_TOLERANZ_M / faktor, 1e-12)

    def verwerfen(grund, anzahl=1):
        verworfen[grund] = verworfen.get(grund, 0) + anzahl

    for element in elemente:
        punkte = tuple(element.get("punkte") or ())
        if not punkte:
            continue
        if not element.get("hoehe_bekannt") and not OHNE_HOEHE_UEBERNEHMEN:
            verwerfen(GRUND_OHNE_HOEHE)
            continue
        hoehen_m = [punkt[2] * faktor for punkt in punkte]
        if any(not (HOEHE_MIN_M <= hoehe <= HOEHE_MAX_M) for hoehe in hoehen_m):
            verwerfen(GRUND_UNPLAUSIBEL)
            continue
        if element["art"] == "punkt":
            x, y, z = punkte[0]
            if DUBLETTEN_ENTFERNEN:
                schluessel = (round(x / raster), round(y / raster), round(z / raster))
                if schluessel in gesehen:
                    verwerfen(GRUND_DUBLETTE)
                    continue
                gesehen.add(schluessel)
            verwendbar.append(element)
            continue
        if len(punkte) < 2:
            continue
        if DUBLETTEN_ENTFERNEN:
            # Dieselbe Bruchkante kann über mehrere Auswahlwege (Gruppe und
            # Gruppeninhalt) gelesen werden; sie wird nur einmal ausgegeben.
            schluessel = (element["art"],) + tuple(
                (round(x / raster), round(y / raster), round(z / raster))
                for x, y, z in punkte)
            if schluessel in gesehen:
                verwerfen(GRUND_DUBLETTE)
                continue
            gesehen.add(schluessel)
        verwendbar.append(element)
    return tuple(verwendbar), verworfen


# ------------------------------------------------------------------ Ausgabe ---
def klasse_sichern(api, name, farbe):
    """Zielklasse anlegen, falls sie fehlt, und die aktive Klasse beibehalten."""
    aktiv = str(api.ActiveClass() or "")
    if not api.GetObject(name):
        api.NameClass(name)
    handle = api.GetObject(name)
    if not handle:
        raise QuelldatenFehler("Die Klasse konnte nicht angelegt werden: " + name)
    try:
        api.SetPenFore(handle, tuple(farbe))
        api.SetFillFore(handle, tuple(farbe))
    finally:
        if aktiv and api.ActiveClass() != aktiv:
            api.NameClass(aktiv)
    return name


def freier_name(api, basis):
    basis = str(basis or ZIEL_EBENE).strip() or ZIEL_EBENE
    if not api.GetObject(basis):
        return basis
    index = 2
    while api.GetObject("%s-%d" % (basis, index)):
        index += 1
    return "%s-%d" % (basis, index)


def quelldaten_schreiben(api, elemente, faktor, ebenenname=ZIEL_EBENE):
    """3D-Punkte und 3D-Polygone auf einer neuen Ebene anlegen und markieren."""
    if not elemente:
        raise QuelldatenFehler("Es sind keine verwendbaren Quelldaten vorhanden.")
    zielname = freier_name(api, ebenenname)
    vorherige_klasse = str(api.ActiveClass() or "")
    try:
        vorherige_ebene = str(api.GetLName(api.ActLayer()) or "")
    except (AttributeError, TypeError):
        vorherige_ebene = ""
    klasse_sichern(api, KLASSE_PUNKT, FARBE_PUNKT)
    klasse_sichern(api, KLASSE_KANTE, FARBE_KANTE)
    ebene = None
    erzeugt = []
    fertig = False
    try:
        ebene = api.CreateLayer(zielname, 1)          # 1 = Konstruktionsebene
        if not ebene:
            raise QuelldatenFehler("Die Quelldaten-Ebene konnte nicht angelegt werden.")
        api.Layer(zielname)
        ziel_z = ebenen_basis(api, ebene, faktor)
        for element in elemente:
            if element["art"] == "punkt":
                x, y, z = element["punkte"][0]
                api.Locus3D((x, y, z - ziel_z))
                handle = api.LNewObj()
                if not handle or int(api.GetTypeN(handle) or 0) != TYP_PUNKT_3D:
                    raise QuelldatenFehler("Ein 3D-Quellpunkt konnte nicht erzeugt werden.")
                erzeugt.append(handle)
                api.SetClass(handle, KLASSE_PUNKT)
                api.SetPenFore(handle, FARBE_PUNKT)
            else:
                api.BeginPoly3D()
                try:
                    for x, y, z in element["punkte"]:
                        api.Add3DPt((x, y, z - ziel_z))
                finally:
                    api.EndPoly3D()
                handle = api.LNewObj()
                if not handle or int(api.GetTypeN(handle) or 0) != TYP_POLYGON_3D:
                    raise QuelldatenFehler("Eine 3D-Bruchkante konnte nicht erzeugt werden.")
                erzeugt.append(handle)
                api.SetPolyClosed(handle, element["art"] == "kontur")
                api.SetFPat(handle, 0)
                api.SetClass(handle, KLASSE_KANTE)
                api.SetPenFore(handle, FARBE_KANTE)
                api.SetLW(handle, LINIENSTAERKE_KANTE)
        if len(erzeugt) != len(elemente):
            raise QuelldatenFehler("Es wurden nicht alle Quelldaten erzeugt.")

        api.DSelectAll()
        kriterium = "(L='%s')" % str(zielname).replace("'", "''")
        try:
            # Native Kriterienauswahl statt langer Einzelschleife.
            api.SelectObj(kriterium)
        except (AttributeError, TypeError):
            for handle in erzeugt:
                api.SetSelect(handle)
        pruefung = _ausgabe_pruefen(api, zielname, elemente, erzeugt)
        api.NameUndoEvent("Gelände-Quelldaten erzeugen")
        api.ReDrawAll()
        fertig = True
        return zielname, tuple(erzeugt), pruefung
    except Exception:
        for handle in erzeugt:
            if handle:
                api.DelObject(handle)
        if ebene:
            api.DelObject(ebene)
        raise
    finally:
        if vorherige_klasse and api.ActiveClass() != vorherige_klasse:
            api.NameClass(vorherige_klasse)
        # Nach erfolgreicher Ausgabe bleibt die Quelldaten-Ebene aktiv,
        # damit der Geländemodell-Befehl direkt folgen kann.
        if not fertig and vorherige_ebene:
            api.Layer(vorherige_ebene)


def _ausgabe_pruefen(api, zielname, elemente, erzeugt):
    """Vectorworks selbst zählen lassen, statt Vollständigkeit zu behaupten."""
    erwartet_punkte = sum(1 for element in elemente if element["art"] == "punkt")
    erwartet_kanten = len(elemente) - erwartet_punkte
    ebene = str(zielname).replace("'", "''")
    try:
        punkte = int(api.Count("((L='%s') & (T=%d))" % (ebene, TYP_PUNKT_3D)) or 0)
        kanten = int(api.Count("((L='%s') & (T=%d))" % (ebene, TYP_POLYGON_3D)) or 0)
        markiert = int(api.Count("((L='%s') & (SEL=TRUE))" % ebene) or 0)
        gezaehlt = True
    except (AttributeError, TypeError, ValueError):
        punkte, kanten, gezaehlt = erwartet_punkte, erwartet_kanten, False
        markiert = len(erzeugt)
    if punkte != erwartet_punkte or kanten != erwartet_kanten:
        raise QuelldatenFehler(
            "Die Ausgabe ist unvollständig: erwartet %d Punkte und %d Bruchkanten, "
            "gefunden %d Punkte und %d Bruchkanten."
            % (erwartet_punkte, erwartet_kanten, punkte, kanten))
    if gezaehlt and markiert != len(erzeugt):
        raise QuelldatenFehler(
            "Es wurden nur %d von %d Quellobjekten markiert."
            % (markiert, len(erzeugt)))
    return {"punkte": punkte, "kanten": kanten, "markiert": markiert,
            "gezaehlt": gezaehlt}


# ------------------------------------------------------------------ Meldung ---
def melden(api, text):
    try:
        api.AlertInform(str(text), "", False)
    except (AttributeError, TypeError):
        api.AlrtDialog(str(text))


def bericht(zielname, pruefung, verworfen, unlesbar, gelesen):
    zeilen = [
        "Gelände-Quelldaten erzeugt.",
        "",
        "Gelesene markierte Objekte: %d" % gelesen,
        "Neue Ebene: %s" % zielname,
        "3D-Punkte: %d" % pruefung["punkte"],
        "3D-Bruchkanten/-konturen: %d" % pruefung["kanten"],
        "Markiert: %d" % pruefung["markiert"],
    ]
    if verworfen:
        zeilen.append("")
        zeilen.append("Nicht übernommen:")
        for grund in sorted(verworfen):
            zeilen.append("  %s: %d" % (grund, verworfen[grund]))
    if unlesbar:
        zeilen.append("")
        zeilen.append("Nicht lesbare Objekttypen:")
        for typ in sorted(unlesbar):
            zeilen.append("  %s: %d" % (typname(typ), unlesbar[typ]))
    zeilen.append("")
    zeilen.append("Nächster Schritt: Auswahl beibehalten und")
    zeilen.append("Landschaft > Geländemodell > Geländemodell aus Ausgangsdaten aufrufen.")
    return "\n".join(zeilen)


def quelldaten_erzeugen(api):
    """Gesamtablauf: markierte Objekte lesen, prüfen, ausgeben und melden."""
    try:
        faktor = meter_pro_einheit(api)
        handles = markierte_objekte(api)
        if not handles:
            melden(api, "Es sind keine Objekte markiert.\n\n"
                        "Bitte die umzuwandelnden Objekte markieren und das Skript erneut starten.")
            return None
        sehne_einheiten = max(SEHNENTOLERANZ_M / faktor, 1e-9)

        def fortschritt(nummer):
            try:
                api.Message("Gelände-Quelldaten: %d von %d Objekten gelesen …"
                            % (nummer, len(handles)))
            except (AttributeError, TypeError):
                pass

        elemente, unlesbar = elemente_sammeln(
            api, handles, faktor, sehne_einheiten, fortschritt)
        try:
            api.ClrMessage()
        except (AttributeError, TypeError):
            pass
        verwendbar, verworfen = elemente_pruefen(elemente, faktor)
        if not verwendbar:
            melden(api, "Aus %d markierten Objekten konnten keine verwendbaren "
                        "Quelldaten gebildet werden.\n\n"
                        "Häufigste Ursache: Die Objekte besitzen keine echte Höhe. "
                        "Dann OHNE_HOEHE_UEBERNEHMEN oder TEXTHOEHE_AUS_INHALT "
                        "im Kopf des Skripts anpassen." % len(handles))
            return None
        zielname, erzeugt, pruefung = quelldaten_schreiben(api, verwendbar, faktor)
        melden(api, bericht(zielname, pruefung, verworfen, unlesbar, len(handles)))
        return zielname, erzeugt
    except QuelldatenFehler as fehler:
        melden(api, "Abbruch: %s\n\nEs wurden keine Objekte hinterlassen." % fehler)
        return None


def _autostart():
    if os.environ.get("PD_GELAENDE_QUELLDATEN_KEIN_AUTOSTART"):
        return
    try:
        import vs
    except ImportError:
        return
    quelldaten_erzeugen(vs)


_autostart()
