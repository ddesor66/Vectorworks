# -*- coding: utf-8 -*-
"""
PHASE 17 - Polygonkern des Werkzeugs "Rigole komplex" (26.08.2026).

Alles hier rechnet in METERN mit einfachen Zahlenlisten. KEIN import vs -
damit laesst sich die gesamte Rasterlogik ausserhalb von Vectorworks
pruefen, so wie der uebrige Rechenkern auch.

Ein Polygon ist eine Liste von Eckpunkten [(x, y), ...] ohne
Wiederholung des Anfangspunktes.

WARUM EIN EIGENER PUNKT-IM-POLYGON-TEST
---------------------------------------
Die Skriptreferenz hat mit vs.PtInPoly zwar eine passende Funktion, warnt in
der Anmerkung aber ausdruecklich: sie arbeitet nur bei Polygonen mit
Eck-Scheiteln zuverlaessig und versagt bei kurzen Seiten. Fuer eine
Rasterbelegung, bei der jede Zelle ueber Zentimeter entscheidet, ist das zu
wenig. Der Strahlensatz-Test hier ist wenige Zeilen lang, deterministisch
und vollstaendig testbar.

WARUM DIE ECKPUNKTPROBE ALLEIN NICHT REICHT
-------------------------------------------
Bei einem KONKAVEN Polygon koennen alle vier Ecken eines Korbes innen
liegen, waehrend eine Polygonkante trotzdem quer durch den Korb schneidet
(ein schmaler Einschnitt). Deshalb wird zusaetzlich geprueft, ob sich
irgendeine Polygonkante mit irgendeiner Korbkante schneidet.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import math

# Rechengenauigkeit in Metern. Kleiner als jede bauliche Groesse, groesser
# als jedes Fliesskomma-Artefakt.
EPS = 1.0e-9

# Ein Korb muss um dieses Mass INNERHALB der Polygonkante liegen, damit
# Rundungsreste an exakt bündigen Kanten nicht zufaellig entscheiden.
# 0,1 mm - baulich bedeutungslos, rechnerisch eindeutig.
BUENDIG_TOLERANZ = 0.0001


class PolygonFehler(Exception):
    pass


# ---------------------------------------------------------------------------
# Grundrechnung
# ---------------------------------------------------------------------------

def bereinige(punkte, toleranz=1.0e-6):
    """
    Entfernt doppelte und praktisch deckungsgleiche Punkte sowie einen
    wiederholten Anfangspunkt am Ende.
    """
    sauber = []
    for p in punkte:
        x, y = float(p[0]), float(p[1])
        if sauber and abs(sauber[-1][0] - x) < toleranz \
                and abs(sauber[-1][1] - y) < toleranz:
            continue
        sauber.append((x, y))
    while len(sauber) > 1 \
            and abs(sauber[0][0] - sauber[-1][0]) < toleranz \
            and abs(sauber[0][1] - sauber[-1][1]) < toleranz:
        sauber.pop()
    return sauber


def flaeche(punkte):
    """
    Flaeche in m2 (Gaußsche Trapezformel), immer positiv.
    """
    n = len(punkte)
    if n < 3:
        return 0.0
    summe = 0.0
    for i in range(n):
        x1, y1 = punkte[i]
        x2, y2 = punkte[(i + 1) % n]
        summe += x1 * y2 - x2 * y1
    return abs(summe) / 2.0


def umfang(punkte):
    n = len(punkte)
    if n < 2:
        return 0.0
    laenge = 0.0
    for i in range(n):
        x1, y1 = punkte[i]
        x2, y2 = punkte[(i + 1) % n]
        laenge += math.hypot(x2 - x1, y2 - y1)
    return laenge


def bounding_box(punkte):
    """Rueckgabe: (xmin, ymin, xmax, ymax)."""
    if not punkte:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in punkte]
    ys = [p[1] for p in punkte]
    return (min(xs), min(ys), max(xs), max(ys))


def schwerpunkt(punkte):
    """
    Flaechenschwerpunkt. Bei entarteter Flaeche der Mittelwert der Ecken.
    """
    n = len(punkte)
    if n == 0:
        return (0.0, 0.0)
    if n < 3:
        return (sum(p[0] for p in punkte) / n, sum(p[1] for p in punkte) / n)

    a = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        x1, y1 = punkte[i]
        x2, y2 = punkte[(i + 1) % n]
        kreuz = x1 * y2 - x2 * y1
        a += kreuz
        cx += (x1 + x2) * kreuz
        cy += (y1 + y2) * kreuz
    if abs(a) < EPS:
        return (sum(p[0] for p in punkte) / n, sum(p[1] for p in punkte) / n)
    a *= 0.5
    return (cx / (6.0 * a), cy / (6.0 * a))


def laengste_kante(punkte):
    """
    Rueckgabe: (index, laenge, winkel_grad)

    Der Winkel ist der Richtungswinkel der Kante gegen die x-Achse, auf
    -90 < w <= 90 normiert. Eine Kante und ihre Gegenrichtung ergeben
    dasselbe Raster, deshalb reicht der halbe Kreis.
    """
    n = len(punkte)
    if n < 2:
        return (0, 0.0, 0.0)
    bester = 0
    beste_laenge = -1.0
    for i in range(n):
        x1, y1 = punkte[i]
        x2, y2 = punkte[(i + 1) % n]
        laenge = math.hypot(x2 - x1, y2 - y1)
        if laenge > beste_laenge + EPS:
            beste_laenge = laenge
            bester = i
    x1, y1 = punkte[bester]
    x2, y2 = punkte[(bester + 1) % n]
    winkel = math.degrees(math.atan2(y2 - y1, x2 - x1))
    while winkel > 90.0:
        winkel -= 180.0
    while winkel <= -90.0:
        winkel += 180.0
    return (bester, beste_laenge, winkel)


def drehe(punkte, winkel_grad, ursprung=(0.0, 0.0)):
    """Dreht eine Punktliste um 'ursprung'."""
    w = math.radians(float(winkel_grad))
    c, s = math.cos(w), math.sin(w)
    ox, oy = float(ursprung[0]), float(ursprung[1])
    gedreht = []
    for x, y in punkte:
        dx, dy = x - ox, y - oy
        gedreht.append((ox + dx * c - dy * s, oy + dx * s + dy * c))
    return gedreht


def drehe_punkt(p, winkel_grad, ursprung=(0.0, 0.0)):
    return drehe([p], winkel_grad, ursprung)[0]


# ---------------------------------------------------------------------------
# Lagebeziehungen
# ---------------------------------------------------------------------------

def punkt_in_polygon(p, punkte, rand_zaehlt=True):
    """
    Strahlensatz-Test (ray casting) nach Osten.

    rand_zaehlt=True: ein Punkt genau auf einer Kante gilt als innen.
    """
    x, y = float(p[0]), float(p[1])
    n = len(punkte)
    if n < 3:
        return False

    if rand_zaehlt:
        for i in range(n):
            if punkt_auf_strecke((x, y), punkte[i], punkte[(i + 1) % n]):
                return True

    innen = False
    j = n - 1
    for i in range(n):
        xi, yi = punkte[i]
        xj, yj = punkte[j]
        # Kante schneidet die waagerechte Linie durch p?
        if (yi > y) != (yj > y):
            # x-Wert des Schnittpunktes
            t = (y - yi) / (yj - yi)
            xs = xi + t * (xj - xi)
            if xs > x:
                innen = not innen
        j = i
    return innen


def punkt_auf_strecke(p, a, b, toleranz=1.0e-9):
    """Liegt p auf der Strecke a-b (inklusive Endpunkten)?"""
    px, py = p
    ax, ay = a
    bx, by = b
    kreuz = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
    laenge = math.hypot(bx - ax, by - ay)
    if laenge < toleranz:
        return math.hypot(px - ax, py - ay) < toleranz
    if abs(kreuz) / laenge > toleranz:
        return False
    skalar = (px - ax) * (bx - ax) + (py - ay) * (by - ay)
    if skalar < -toleranz:
        return False
    return skalar <= laenge * laenge + toleranz


def _richtung(ax, ay, bx, by, cx, cy):
    wert = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    if wert > EPS:
        return 1
    if wert < -EPS:
        return -1
    return 0


def strecken_schneiden(a1, a2, b1, b2):
    """
    Schneiden sich die Strecken a1-a2 und b1-b2 (Beruehrung zaehlt mit)?
    """
    d1 = _richtung(b1[0], b1[1], b2[0], b2[1], a1[0], a1[1])
    d2 = _richtung(b1[0], b1[1], b2[0], b2[1], a2[0], a2[1])
    d3 = _richtung(a1[0], a1[1], a2[0], a2[1], b1[0], b1[1])
    d4 = _richtung(a1[0], a1[1], a2[0], a2[1], b2[0], b2[1])

    if d1 * d2 < 0 and d3 * d4 < 0:
        return True
    if d1 == 0 and punkt_auf_strecke(a1, b1, b2):
        return True
    if d2 == 0 and punkt_auf_strecke(a2, b1, b2):
        return True
    if d3 == 0 and punkt_auf_strecke(b1, a1, a2):
        return True
    if d4 == 0 and punkt_auf_strecke(b2, a1, a2):
        return True
    return False


def rechteck_ganz_innen(x0, y0, x1, y1, punkte, toleranz=BUENDIG_TOLERANZ):
    """
    Liegt das achsparallele Rechteck vollstaendig im Polygon?

    Geprueft wird zweistufig:
      1. alle vier Ecken innen (leicht nach innen versetzt, damit ein exakt
         buendiger Korb nicht an Rundungsresten scheitert)
      2. keine Polygonkante schneidet eine Rechteckkante

    Schritt 2 faengt den konkaven Fall ab: vier Ecken innen, aber ein
    Einschnitt geht mitten durch.
    """
    t = float(toleranz)
    ecken = ((x0 + t, y0 + t), (x1 - t, y0 + t),
             (x1 - t, y1 - t), (x0 + t, y1 - t))
    for ecke in ecken:
        if not punkt_in_polygon(ecke, punkte):
            return False

    kanten = ((ecken[0], ecken[1]), (ecken[1], ecken[2]),
              (ecken[2], ecken[3]), (ecken[3], ecken[0]))
    n = len(punkte)
    for i in range(n):
        p1 = punkte[i]
        p2 = punkte[(i + 1) % n]
        for k1, k2 in kanten:
            if strecken_schneiden(k1, k2, p1, p2):
                return False
    return True


# ---------------------------------------------------------------------------
# Rasterbelegung
# ---------------------------------------------------------------------------

class Rasterergebnis(object):
    """
    Was bei der Belegung herauskam.

    zellen      Liste von (spalte, reihe) - Rasterkoordinaten
    ursprung    (x, y) der Zelle (0, 0) im gedrehten System
    spalten     Anzahl Rasterspalten des Suchfeldes
    reihen      Anzahl Rasterreihen des Suchfeldes
    versatz     der gefundene beste Rasterversatz (dx, dy)
    """

    __slots__ = ("zellen", "ursprung", "spalten", "reihen", "versatz",
                 "korb_laenge", "korb_breite")

    def __init__(self, zellen, ursprung, spalten, reihen, versatz,
                 korb_laenge, korb_breite):
        self.zellen = zellen
        self.ursprung = ursprung
        self.spalten = int(spalten)
        self.reihen = int(reihen)
        self.versatz = versatz
        self.korb_laenge = float(korb_laenge)
        self.korb_breite = float(korb_breite)

    @property
    def anzahl(self):
        return len(self.zellen)

    def zellrechteck(self, zelle):
        """(x0, y0, x1, y1) der Zelle im gedrehten System."""
        spalte, reihe = zelle
        x0 = self.ursprung[0] + spalte * self.korb_laenge
        y0 = self.ursprung[1] + reihe * self.korb_breite
        return (x0, y0, x0 + self.korb_laenge, y0 + self.korb_breite)

    def zellmitte(self, zelle):
        x0, y0, x1, y1 = self.zellrechteck(zelle)
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)

    def belegte_bounding_box(self):
        """(xmin, ymin, xmax, ymax) der tatsaechlich belegten Zellen."""
        if not self.zellen:
            return (0.0, 0.0, 0.0, 0.0)
        rechtecke = [self.zellrechteck(z) for z in self.zellen]
        return (min(r[0] for r in rechtecke), min(r[1] for r in rechtecke),
                max(r[2] for r in rechtecke), max(r[3] for r in rechtecke))


def _belege(punkte, korb_l, korb_b, startx, starty, spalten, reihen):
    zellen = []
    for spalte in range(spalten):
        x0 = startx + spalte * korb_l
        for reihe in range(reihen):
            y0 = starty + reihe * korb_b
            # Schnelltest: liegt die Zellmitte ueberhaupt innen?
            if not punkt_in_polygon((x0 + korb_l / 2.0, y0 + korb_b / 2.0),
                                    punkte):
                continue
            if rechteck_ganz_innen(x0, y0, x0 + korb_l, y0 + korb_b, punkte):
                zellen.append((spalte, reihe))
    return zellen


def pruefe_einfaches_polygon(punkte):
    if len(punkte) > 2000:
        raise PolygonFehler("Mehr als 2000 Umgrenzungspunkte: Bitte die Kontur vereinfachen oder aufteilen.")
    if len(punkte) < 3 or not all(math.isfinite(v) for p in punkte for v in p):
        raise PolygonFehler("Die Umgrenzung enthält keine gültige Fläche.")
    for i in range(len(punkte)):
        for j in range(i + 1, len(punkte)):
            if j == i + 1 or (i == 0 and j == len(punkte) - 1):
                continue
            if strecken_schneiden(punkte[i], punkte[(i + 1) % len(punkte)],
                                 punkte[j], punkte[(j + 1) % len(punkte)]):
                raise PolygonFehler(
                    "Die Umgrenzung überschneidet oder berührt sich selbst. "
                    "Bitte die Polygonkanten korrigieren.")
    if flaeche(punkte) <= EPS:
        raise PolygonFehler("Die Umgrenzung besitzt keine messbare Fläche.")


def belege_polygon(punkte, korb_laenge, korb_breite, such_schritte=4):
    """
    Legt ein Raster aus Koerben in ein bereits GEDREHTES Polygon (das heisst:
    die Rasterrichtung ist die x-Achse) und liefert die Zellen, die
    vollstaendig innen liegen.

    such_schritte  Wie fein der Rasterversatz durchprobiert wird. Bei n
                   werden n x n Startlagen innerhalb einer Korbzelle
                   getestet und die mit den meisten Koerben genommen. Der
                   Rand des Polygons entscheidet sonst zufaellig darueber,
                   ob eine ganze Reihe hineinpasst oder nicht.
                   1 = kein Suchen (Raster buendig an der Hüllbox).

    Rueckgabe: Rasterergebnis
    """
    pruefe_einfaches_polygon(punkte)
    korb_l = float(korb_laenge)
    korb_b = float(korb_breite)
    if not math.isfinite(korb_l) or not math.isfinite(korb_b) or korb_l <= 0.0 or korb_b <= 0.0:
        raise PolygonFehler(u"Korblaenge und Korbbreite muessen groesser "
                            u"als null sein.")
    if len(punkte) < 3:
        raise PolygonFehler(u"Das Polygon hat weniger als drei Eckpunkte.")

    xmin, ymin, xmax, ymax = bounding_box(punkte)
    breite = xmax - xmin
    hoehe = ymax - ymin
    spalten = int(math.floor(breite / korb_l)) + 1
    reihen = int(math.floor(hoehe / korb_b)) + 1

    schritte = max(1, int(such_schritte))
    if (spalten + 1) * (reihen + 1) * schritte * schritte * len(punkte) > 20000000:
        raise PolygonFehler(
            "Das Suchraster ist zu groß. Bitte die Fläche aufteilen oder "
            "größere Körbe bzw. weniger Suchschritte wählen.")
    beste = None
    for i in range(schritte):
        dx = -korb_l * i / float(schritte)
        for j in range(schritte):
            dy = -korb_b * j / float(schritte)
            startx = xmin + dx
            starty = ymin + dy
            # Durch den Versatz nach links/unten kann eine Spalte bzw. Reihe
            # mehr hineinpassen.
            zellen = _belege(punkte, korb_l, korb_b, startx, starty,
                             spalten + 1, reihen + 1)
            if beste is None or len(zellen) > len(beste[0]):
                beste = (zellen, (startx, starty), (dx, dy))

    zellen, ursprung, versatz = beste
    return Rasterergebnis(zellen, ursprung, spalten + 1, reihen + 1, versatz,
                          korb_l, korb_b)


# ---------------------------------------------------------------------------
# Schachtplaetze
# ---------------------------------------------------------------------------

def schacht_zellen(raster, mitte_ab_laenge=20.0):
    """
    Auf welchen Koerben sitzen die Kontrollschaechte?

    REGEL (Vorschlag vom 26.08.2026, bewusst einfach gehalten):
    Massgebend ist die Rasterlaengsrichtung (x). Genommen wird die REIHE,
    die dem Flaechenschwerpunkt der belegten Zellen am naechsten liegt und
    in der Zellen ganz aussen liegen. Dort bekommt der erste und der letzte
    Korb je einen Schacht; liegen sie weiter als 'mitte_ab_laenge'
    auseinander, kommt ein dritter in der Mitte dazu.

    Damit gilt fuer die komplexe Rigole dieselbe Grundidee wie fuer die
    rechteckige: die Schaechte sitzen mittig auf einem Korb, an den beiden
    Enden, bei langen Rigolen zusaetzlich in der Mitte.

    Rueckgabe: Liste von Zellen [(spalte, reihe), ...]
    """
    if not raster or not raster.zellen:
        return []

    zellen = list(raster.zellen)
    reihen = {}
    for spalte, reihe in zellen:
        reihen.setdefault(reihe, []).append(spalte)

    # Reihe mit der groessten Spannweite; bei Gleichstand die mittlere.
    kandidaten = []
    mittlere_reihe = sum(z[1] for z in zellen) / float(len(zellen))
    for reihe, spalten in reihen.items():
        kandidaten.append((max(spalten) - min(spalten), -abs(reihe - mittlere_reihe), reihe))
    kandidaten.sort()
    reihe = kandidaten[-1][2]
    spalten = sorted(reihen[reihe])

    gewaehlt = [(spalten[0], reihe)]
    if spalten[-1] != spalten[0]:
        gewaehlt.append((spalten[-1], reihe))

    if len(gewaehlt) == 2:
        abstand = (spalten[-1] - spalten[0]) * raster.korb_laenge
        if abstand > float(mitte_ab_laenge) + 1.0e-6:
            mitte = spalten[len(spalten) // 2]
            if mitte not in (spalten[0], spalten[-1]):
                gewaehlt.insert(1, (mitte, reihe))

    return gewaehlt
