"""Pure leader endpoint geometry for a pair of annotation text boxes."""
import math

from .core import SewerError


def leader_end(anchor, boxes, margin):
    coords = [p for box in boxes for p in box]
    if not coords or not all(math.isfinite(v) for p in coords for v in p):
        raise SewerError("Textbegrenzung für die Bezugslinie ist ungültig.")
    left, right = min(p[0] for p in coords)-margin, max(p[0] for p in coords)+margin
    bottom, top = min(p[1] for p in coords)-margin, max(p[1] for p in coords)+margin
    center = ((left+right)*.5, (bottom+top)*.5)
    dx, dy = anchor[0]-center[0], anchor[1]-center[1]
    if abs(dx)+abs(dy) <= 1e-12:
        return center
    factors = []
    if abs(dx) > 1e-12:
        factors.append((right-left)*.5/abs(dx))
    if abs(dy) > 1e-12:
        factors.append((top-bottom)*.5/abs(dy))
    fraction = min(factors)
    # If the anchor is inside the text region there is no visible gap to span.
    if fraction >= 1:
        return anchor
    return center[0]+fraction*dx, center[1]+fraction*dy
