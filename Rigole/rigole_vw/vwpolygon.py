# -*- coding: utf-8 -*-
"""
PHASE 17 - Das gezeichnete Umgrenzungspolygon aus der Zeichnung holen.

Diese Datei ist die einzige Stelle, an der die Polygonfunktionen von
Vectorworks angefasst werden. Alles Weitere rechnet rigole_core/polygon.py
in reinem Python.

VERWENDETE API-FUNKTIONEN (alle in der VW-2026-Referenz nachgeschlagen)
----------------------------------------------------------------------
    vs.GetTypeN(h)                  Objekttyp: 5 = Polygon, 21 = Polylinie
    vs.IsPolyClosed(h)              geschlossen?
    vs.GetVertNum(h)                Anzahl Eckpunkte
    vs.GetPolyPt(h, i)              Eckpunkt i (1-basiert)
    vs.GetPolylineVertex(h, i)      Eckpunkt i mit Scheiteltyp
    vs.GetNumHoles(h)               Anzahl Oeffnungen (Loecher)
    vs.ConvertToPolygon(h, aufl)    erzeugt eine Kopie mit Eckscheiteln
    vs.DelObject(h)                 loescht die Kopie wieder
    vs.SetName / vs.GetName         Objektname

NICHT verwendet wird vs.PtInPoly: Die Referenz merkt dort ausdruecklich an,
dass die Funktion nur bei Polygonen mit Eck-Scheiteln und grossen Seiten
verlaesslich arbeitet. Fuer die Rasterbelegung ist das zu wenig - der Test
steckt deshalb in rigole_core/polygon.py.

BOEGEN UND KURVEN
-----------------
Eine Polylinie kann Bezier-, Kubik-, Bogen- und Radiusscheitel haben. Deren
Verlauf laesst sich nicht aus den Eckpunkten ablesen. Solche Objekte werden
deshalb ueber vs.ConvertToPolygon in ein Polygon mit lauter Eckscheiteln
umgewandelt; gelesen wird die Kopie, danach wird sie sofort geloescht. Das
Original bleibt unangetastet.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_core import polygon as poly
from rigole_vw import vwutils


TYP_POLYGON = 5
TYP_POLYLINE = 21

# Aufloesung fuer vs.ConvertToPolygon. Die Referenz nennt als wirksame Werte
# 0, 8, 16, 32, 64, 128, 256, 512 - hoeher heisst mehr Eckpunkte. 64 bildet
# einen Bogen auf wenige Zentimeter genau ab und haelt die Punktzahl klein.
KURVEN_AUFLOESUNG = 64


class UmgrenzungFehler(Exception):
    pass


def objekttyp(h):
    try:
        return int(vs.GetTypeN(h))
    except Exception:
        return 0


def ist_umgrenzung(h):
    """Taugt das Objekt als Umgrenzung? (Polygon oder Polylinie)"""
    if not vwutils.handle_ok(h):
        return False
    return objekttyp(h) in (TYP_POLYGON, TYP_POLYLINE)


def _geschlossen(h):
    try:
        return bool(vs.IsPolyClosed(h))
    except Exception:
        # Aeltere Staende ohne die Funktion: nicht daran scheitern.
        return True


def _loecher(h):
    """Anzahl der Oeffnungen oder 0, wenn nicht ermittelbar."""
    try:
        ok, anzahl = vs.GetNumHoles(h)
    except Exception:
        return 0
    try:
        return int(anzahl) if ok else 0
    except (TypeError, ValueError):
        return 0


def _hat_kurvenscheitel(h):
    """
    Hat die Polylinie Scheitel, die keine einfachen Ecken sind?
    Scheiteltyp laut Referenz: 0 = Ecke, 1 = Bezier, 2 = Kubik,
    3 = Bogen, 4 = Radius.
    """
    if objekttyp(h) != TYP_POLYLINE:
        return False
    try:
        anzahl = int(vs.GetVertNum(h))
    except Exception:
        return False
    for i in range(1, anzahl + 1):
        try:
            _p, typ, _radius = vs.GetPolylineVertex(h, i)
        except Exception:
            return True          # im Zweifel begradigen
        try:
            if int(typ) != 0:
                return True
        except (TypeError, ValueError):
            return True
    return False


def _eckpunkte(h):
    """Rohe Eckpunkte in DOKUMENTEINHEITEN."""
    try:
        anzahl = int(vs.GetVertNum(h))
    except Exception:
        raise UmgrenzungFehler(
            u"Die Eckpunkte der Umgrenzung liessen sich nicht lesen.")
    punkte = []
    for i in range(1, anzahl + 1):
        try:
            p = vs.GetPolyPt(h, i)
            punkte.append((float(p[0]), float(p[1])))
        except Exception:
            continue
    return punkte


def lies_umgrenzung(h, unit_ctx):
    """
    Liefert (punkte_in_metern, hinweise).

    'hinweise' ist eine Liste von Klartextzeilen, die das Werkzeug dem
    Anwender zeigen kann - etwa dass Boegen begradigt wurden.

    Loest UmgrenzungFehler aus, wenn das Objekt nicht taugt.
    """
    hinweise = []
    if not vwutils.handle_ok(h):
        raise UmgrenzungFehler(u"Es wurde kein Objekt uebergeben.")

    typ = objekttyp(h)
    if typ not in (TYP_POLYGON, TYP_POLYLINE):
        raise UmgrenzungFehler(meldung_falscher_typ(typ))

    if not _geschlossen(h):
        raise UmgrenzungFehler(
            u"Das angeklickte Objekt ist NICHT GESCHLOSSEN.\n\n"
            u"Eine Rigole braucht eine geschlossene Umgrenzung. Bitte "
            u"schliessen Sie den Linienzug (Objektinfo: Haken bei "
            u"„Geschlossen“) und klicken Sie erneut.")

    loecher = _loecher(h)
    if loecher > 0:
        hinweise.append(
            u"Die Umgrenzung hat %d Oeffnung(en). Ausgespart wird nicht - "
            u"das Werkzeug fuellt nur die aeussere Umrandung. Bitte im Plan "
            u"pruefen." % (loecher,))

    quelle = h
    kopie = None
    if _hat_kurvenscheitel(h):
        try:
            kopie = vs.ConvertToPolygon(h, KURVEN_AUFLOESUNG)
        except Exception:
            kopie = None
        if vwutils.handle_ok(kopie):
            quelle = kopie
            hinweise.append(
                u"Die Umgrenzung enthaelt Boegen oder Kurven. Sie wurden "
                u"fuer die Berechnung in gerade Abschnitte zerlegt; das "
                u"gezeichnete Objekt bleibt unveraendert.")
        else:
            hinweise.append(
                u"Die Umgrenzung enthaelt Boegen oder Kurven, die sich "
                u"nicht zerlegen liessen. Gerechnet wird mit den "
                u"Eckpunkten - der Rand kann dadurch abweichen.")

    try:
        roh = _eckpunkte(quelle)
    finally:
        if kopie is not None and vwutils.handle_ok(kopie):
            try:
                vs.DelObject(kopie)
            except Exception:
                pass

    punkte = poly.bereinige([(unit_ctx.from_doc(x), unit_ctx.from_doc(y))
                             for (x, y) in roh])
    if len(punkte) < 3:
        raise UmgrenzungFehler(
            u"Die Umgrenzung hat weniger als drei brauchbare Eckpunkte.")

    return punkte, hinweise


# ---------------------------------------------------------------------------
# Wiederfinden beim Bearbeiten
# ---------------------------------------------------------------------------

def name_sichern(h, wunschname):
    """
    Sorgt dafuer, dass das Umgrenzungspolygon einen Namen hat, und liefert
    ihn zurueck.

    Hat der Anwender dem Objekt schon selbst einen Namen gegeben, bleibt
    dieser stehen - fremde Benennungen werden nicht ueberschrieben.
    Rueckgabe: der gueltige Name oder "" (dann ist Bearbeiten spaeter nicht
    moeglich, das Werkzeug sagt das).
    """
    vorhanden = ""
    try:
        vorhanden = str(vs.GetName(h) or "")
    except Exception:
        vorhanden = ""
    if vorhanden.strip():
        return vorhanden

    try:
        vs.SetName(h, wunschname)
    except Exception:
        return ""
    try:
        return str(vs.GetName(h) or "")
    except Exception:
        return wunschname


def hole_nach_name(name):
    """Das Umgrenzungspolygon zu einem gespeicherten Namen oder None."""
    if not str(name or "").strip():
        return None
    try:
        h = vs.GetObject(str(name))
    except Exception:
        return None
    if not vwutils.handle_ok(h):
        return None
    return h if ist_umgrenzung(h) else None


# ---------------------------------------------------------------------------
# Meldungstexte
# ---------------------------------------------------------------------------

TYPNAMEN = {
    2: u"eine Linie", 3: u"ein Rechteck", 4: u"ein Oval",
    6: u"ein Bogen", 10: u"ein Text", 11: u"eine Gruppe",
    13: u"ein abgerundetes Rechteck", 15: u"eine Symbolinstanz",
    24: u"ein Extrusionskoerper", 68: u"eine Wand",
}


def meldung_falscher_typ(typ):
    was = TYPNAMEN.get(int(typ or 0), u"ein Objekt dieser Art")
    return (u"Das angeklickte Objekt ist %s.\n\n"
            u"Das Werkzeug „Rigole komplex“ braucht ein "
            u"geschlossenes POLYGON oder eine geschlossene POLYLINIE als "
            u"Umgrenzung.\n\n"
            u"Hinweis: Ein Rechteck laesst sich in Vectorworks ueber "
            u"„Aendern > Umwandeln > In Polygone umwandeln“ "
            u"umwandeln." % (was,))


def meldung_nichts_getroffen():
    return (u"An dieser Stelle liegt kein Objekt, das als Umgrenzung "
            u"taugt.\n\n"
            u"Bitte zeichnen Sie zuerst ein geschlossenes Polygon und "
            u"klicken Sie dann mit dem Werkzeug darauf - am besten auf eine "
            u"seiner Kanten oder, wenn es eine Fuellung hat, in die "
            u"Flaeche.\n\n"
            u"Angeklickt werden kann nur, was auch mit dem Auswahlwerkzeug "
            u"erreichbar ist. Alternativ das Polygon vorher markieren.")
