# -*- coding: utf-8 -*-
"""Rigid drawing axes for rotated Top/Plan; no changes to the user's view.

VW 2026 Script Reference: ScreenPtToModelPt2D(p) returns the model point
for a rotated-plan coordinate. Use its basis, not an assumed angle sign.
All stored source geometry stays in model coordinates.
"""
import math


class PlanFrame:
    def __init__(self, angle=0.0):
        self.angle = float(angle)
        if not math.isfinite(self.angle):
            raise ValueError("Die Planausrichtung ist nicht lesbar.")
        radians = math.radians(self.angle)
        self.c, self.s = math.cos(radians), math.sin(radians)

    @classmethod
    def current(cls, api):
        try:
            origin, right, up = [api.ScreenPtToModelPt2D(p) for p in
                                ((0.0, 0.0), (1024.0, 0.0), (0.0, 1024.0))]
            ux, uy = ((float(right[i]) - float(origin[i])) / 1024.0
                      for i in (0, 1))
            vx, vy = ((float(up[i]) - float(origin[i])) / 1024.0
                      for i in (0, 1))
            values = (ux, uy, vx, vy)
            if (not all(math.isfinite(v) for v in values)
                    or abs(ux * ux + uy * uy - 1.0) > 1e-6
                    or abs(vx * vx + vy * vy - 1.0) > 1e-6
                    or abs(ux * vx + uy * vy) > 1e-6
                    or abs(ux * vy - uy * vx - 1.0) > 1e-6):
                raise ValueError("Keine orthogonalen Planachsen.")
            return cls(math.degrees(math.atan2(uy, ux)))
        except Exception as error:
            raise ValueError(
                "Die aktuelle Plandrehung konnte nicht sicher gelesen werden. "
                "Bitte in die 2D-Planansicht wechseln. Es wurde nichts gezeichnet."
            ) from error

    def local(self, point):
        x, y = float(point[0]), float(point[1])
        return self.c * x + self.s * y, -self.s * x + self.c * y

    def model(self, point):
        x, y = float(point[0]), float(point[1])
        return self.c * x - self.s * y, self.s * x + self.c * y

    def local_points(self, points):
        return [self.local(p) for p in points]

    def model_points(self, points):
        return [self.model(p) for p in points]

    def offset(self, origin, dx, dy):
        x, y = self.model((dx, dy))
        return float(origin[0]) + x, float(origin[1]) + y

    def rotate_created(self, api, handles):
        """Only newly registered objects; callers own rollback on any failure."""
        if abs(self.angle) < 1e-10:
            return
        seen = []
        for handle in handles:
            if not handle:
                raise ValueError("Ein neues Objekt konnte nicht ausgerichtet werden.")
            if handle in seen:
                continue
            seen.append(handle)
            api.HRotate(handle, (0.0, 0.0), self.angle)


def wall_frame(api, parameters):
    """Capture once on creation; retain an existing wall's construction axes."""
    if "plan_angle_deg" not in parameters:
        parameters["plan_angle_deg"] = PlanFrame.current(api).angle
    return PlanFrame(parameters["plan_angle_deg"])


def rigole_angle(api, existing=None):
    """A rebuild retains the real instance angle, including manual rotation."""
    if existing is not None:
        return PlanFrame(api.GetSymRot(existing)).angle
    return PlanFrame.current(api).angle
