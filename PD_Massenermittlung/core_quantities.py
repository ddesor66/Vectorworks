"""Pure quantity data model and deterministic aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import Dict, Iterable, Mapping, Optional, Sequence, Tuple

from .core_patterns import normalize_name


def _natural_key(value: str) -> Tuple[object, ...]:
    parts = re.split(r"(\d+)", normalize_name(value).casefold())
    return tuple(int(part) if part.isdigit() else part for part in parts)


@dataclass(frozen=True, order=True)
class SourceKey:
    """A unique table row origin including its placed element type.

    Ordinary drawing geometry deliberately shares the ``geometry`` type so
    the established class/layer totals remain compact.  Placed symbols and
    groups carry their definition/group type and therefore receive separate
    quantity rows inside the same class and layer.
    """

    class_name: str
    layer_id: str
    layer_name: str
    element_kind: str = "geometry"
    element_name: str = "Geometrie"

    def __post_init__(self) -> None:
        object.__setattr__(self, "class_name", normalize_name(self.class_name))
        object.__setattr__(self, "layer_id", normalize_name(self.layer_id))
        object.__setattr__(self, "layer_name", normalize_name(self.layer_name))
        element_kind = normalize_name(self.element_kind).casefold() or "geometry"
        element_name = normalize_name(self.element_name)
        if not element_name:
            element_name = {
                "geometry": "Geometrie",
                "group": "Unbenannte Gruppe",
                "symbol": "Unbenanntes Symbol",
            }.get(element_kind, "Sonstiges Element")
        object.__setattr__(self, "element_kind", element_kind)
        object.__setattr__(self, "element_name", element_name)
        if not self.class_name:
            raise ValueError("class_name must not be empty")
        if not self.layer_id:
            raise ValueError("layer_id must not be empty")
        if not self.layer_name:
            raise ValueError("layer_name must not be empty")

    @property
    def element_label(self) -> str:
        prefix = {
            "geometry": "Geometrie",
            "group": "Gruppe",
            "symbol": "Symbol",
        }.get(self.element_kind, "Element")
        if self.element_kind == "geometry" and self.element_name == "Geometrie":
            return self.element_name
        return "{}: {}".format(prefix, self.element_name)


@dataclass(frozen=True)
class Point2D:
    x_m: float
    y_m: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.x_m) or not math.isfinite(self.y_m):
            raise ValueError("point coordinates must be finite")


@dataclass(frozen=True)
class Path2D:
    """A linearly sampled path in SI units.

    The Vectorworks adapter is responsible for sampling curved polyline
    segments with a documented tolerance before constructing this object.
    """

    points: Tuple[Point2D, ...]
    closed: bool = False

    def __post_init__(self) -> None:
        points = tuple(self.points)
        object.__setattr__(self, "points", points)
        minimum = 3 if self.closed else 2
        if len(points) < minimum:
            raise ValueError("path has too few points")

    @property
    def length_m(self) -> float:
        pairs = list(zip(self.points, self.points[1:]))
        if self.closed and self.points[-1] != self.points[0]:
            pairs.append((self.points[-1], self.points[0]))
        return math.fsum(
            math.hypot(second.x_m - first.x_m, second.y_m - first.y_m)
            for first, second in pairs
        )

    @property
    def area_m2(self) -> float:
        if not self.closed:
            return 0.0
        points = self.points
        products = [
            first.x_m * second.y_m - second.x_m * first.y_m
            for first, second in zip(points, points[1:])
        ]
        if points[-1] != points[0]:
            products.append(
                points[-1].x_m * points[0].y_m
                - points[0].x_m * points[-1].y_m
            )
        return abs(math.fsum(products)) * 0.5


class ObjectKind(str, Enum):
    LINE = "line"
    RECTANGLE = "rectangle"
    OVAL = "oval"
    POLYGON = "polygon"
    ARC = "arc"
    ROUNDED_RECTANGLE = "rounded_rectangle"
    POLYLINE = "polyline"
    GENERIC_GEOMETRY = "generic_geometry"
    GROUP = "group"
    SYMBOL = "symbol"
    UNSUPPORTED = "unsupported"

    @property
    def is_geometry(self) -> bool:
        return self in (
            ObjectKind.LINE,
            ObjectKind.RECTANGLE,
            ObjectKind.OVAL,
            ObjectKind.POLYGON,
            ObjectKind.ARC,
            ObjectKind.ROUNDED_RECTANGLE,
            ObjectKind.POLYLINE,
            ObjectKind.GENERIC_GEOMETRY,
        )


@dataclass(frozen=True)
class ObjectFact:
    """Normalized facts for one placed Vectorworks object or geometry leaf."""

    object_id: str
    source_key: SourceKey
    kind: ObjectKind
    path: Optional[Path2D] = None
    length_m: Optional[float] = None
    area_m2: Optional[float] = None
    parent_ids: Tuple[str, ...] = ()
    representative_id: Optional[str] = None
    warnings: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "object_id", normalize_name(self.object_id))
        object.__setattr__(
            self, "parent_ids", tuple(normalize_name(value) for value in self.parent_ids)
        )
        object.__setattr__(
            self,
            "representative_id",
            normalize_name(self.representative_id)
            if self.representative_id is not None
            else self.object_id,
        )
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if not self.object_id:
            raise ValueError("object_id must not be empty")
        if self.kind.is_geometry and self.path is None and self.length_m is None:
            raise ValueError("geometry object requires a path or a length override")
        for value, label in ((self.length_m, "length_m"), (self.area_m2, "area_m2")):
            if value is not None and (not math.isfinite(value) or value < 0.0):
                raise ValueError("{} must be finite and non-negative".format(label))

    @property
    def measured_length_m(self) -> float:
        if not self.kind.is_geometry:
            return 0.0
        if self.length_m is not None:
            return self.length_m
        return self.path.length_m if self.path is not None else 0.0

    @property
    def measured_area_m2(self) -> float:
        if not self.kind.is_geometry:
            return 0.0
        if self.area_m2 is not None:
            return self.area_m2
        return self.path.area_m2 if self.path is not None else 0.0

    @property
    def piece_count(self) -> int:
        return 1 if self.kind.is_geometry or self.kind in (
            ObjectKind.SYMBOL, ObjectKind.GROUP) else 0


@dataclass(frozen=True)
class QuantityAdjustment:
    """An auditable reduction produced by duplicate analysis."""

    adjustment_id: str
    source_key: SourceKey
    kind: str
    object_ids: Tuple[str, ...]
    length_delta_m: float = 0.0
    area_delta_m2: float = 0.0
    piece_delta: int = 0
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "adjustment_id", normalize_name(self.adjustment_id))
        object.__setattr__(
            self, "object_ids", tuple(sorted({normalize_name(v) for v in self.object_ids}))
        )
        if not self.adjustment_id:
            raise ValueError("adjustment_id must not be empty")
        if not self.object_ids:
            raise ValueError("adjustment must reference at least one object")
        for value, label in (
            (self.length_delta_m, "length_delta_m"),
            (self.area_delta_m2, "area_delta_m2"),
        ):
            if not math.isfinite(value) or value > 1e-12:
                raise ValueError("{} must be finite and non-positive".format(label))
        if self.piece_delta > 0:
            raise ValueError("piece_delta must be non-positive")


@dataclass(frozen=True)
class QuantityRow:
    source_key: SourceKey
    group_id: Optional[str]
    raw_length_m: float
    net_length_m: float
    raw_area_m2: float
    net_area_m2: float
    raw_piece_count: int
    net_piece_count: int
    group_count: int
    symbol_count: int
    object_ids: Tuple[str, ...]
    representative_id: Optional[str]
    adjustment_ids: Tuple[str, ...] = ()
    warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class GroupTotal:
    group_id: str
    title: str
    length_m: float
    area_m2: float
    piece_count: int
    group_count: int
    symbol_count: int


def _non_negative(value: float, label: str) -> float:
    if value < -1e-9:
        raise ValueError("adjustments make {} negative".format(label))
    return max(0.0, value)


def aggregate_quantities(
    objects: Iterable[ObjectFact],
    adjustments: Iterable[QuantityAdjustment] = (),
    group_assignments: Optional[Mapping[SourceKey, str]] = None,
) -> Tuple[QuantityRow, ...]:
    """Aggregate by exact class, layer and placed element type."""

    objects_by_key: Dict[SourceKey, list] = {}
    object_by_id: Dict[str, ObjectFact] = {}
    for fact in objects:
        if fact.object_id in object_by_id:
            raise ValueError("duplicate object_id: {}".format(fact.object_id))
        object_by_id[fact.object_id] = fact
        objects_by_key.setdefault(fact.source_key, []).append(fact)

    adjustments_by_key: Dict[SourceKey, list] = {}
    adjustment_ids = set()
    for adjustment in adjustments:
        if adjustment.adjustment_id in adjustment_ids:
            raise ValueError("duplicate adjustment_id")
        adjustment_ids.add(adjustment.adjustment_id)
        unknown = [value for value in adjustment.object_ids if value not in object_by_id]
        if unknown:
            raise ValueError("adjustment references an unknown object")
        wrong_key = [
            value
            for value in adjustment.object_ids
            if object_by_id[value].source_key != adjustment.source_key
        ]
        if wrong_key:
            raise ValueError("adjustment crosses source keys")
        adjustments_by_key.setdefault(adjustment.source_key, []).append(adjustment)

    assignments = group_assignments or {}
    rows = []
    quantity_keys = (
        source_key
        for source_key, facts in objects_by_key.items()
        if any(fact.kind != ObjectKind.UNSUPPORTED for fact in facts)
    )
    ordered_keys = sorted(
        quantity_keys,
        key=lambda key: (
            _natural_key(key.class_name), _natural_key(key.layer_name),
            key.layer_id, _natural_key(key.element_kind),
            _natural_key(key.element_name)),
    )
    for source_key in ordered_keys:
        facts = sorted(objects_by_key[source_key], key=lambda fact: fact.object_id)
        row_adjustments = sorted(
            adjustments_by_key.get(source_key, ()), key=lambda item: item.adjustment_id
        )
        raw_length = math.fsum(fact.measured_length_m for fact in facts)
        raw_area = math.fsum(fact.measured_area_m2 for fact in facts)
        raw_pieces = sum(fact.piece_count for fact in facts)
        net_length = _non_negative(
            raw_length + math.fsum(item.length_delta_m for item in row_adjustments),
            "length",
        )
        net_area = _non_negative(
            raw_area + math.fsum(item.area_delta_m2 for item in row_adjustments),
            "area",
        )
        net_pieces = raw_pieces + sum(item.piece_delta for item in row_adjustments)
        if net_pieces < 0:
            raise ValueError("adjustments make piece count negative")
        geometry_representatives = [
            fact.representative_id for fact in facts if fact.kind.is_geometry
        ]
        warnings = sorted(
            {
                warning
                for fact in facts
                for warning in fact.warnings
                if warning
            }
        )
        rows.append(
            QuantityRow(
                source_key=source_key,
                group_id=assignments.get(source_key),
                raw_length_m=raw_length,
                net_length_m=net_length,
                raw_area_m2=raw_area,
                net_area_m2=net_area,
                raw_piece_count=raw_pieces,
                net_piece_count=net_pieces,
                group_count=sum(1 for fact in facts if fact.kind == ObjectKind.GROUP),
                symbol_count=sum(1 for fact in facts if fact.kind == ObjectKind.SYMBOL),
                object_ids=tuple(fact.object_id for fact in facts),
                representative_id=(
                    geometry_representatives[0]
                    if geometry_representatives
                    else (facts[0].representative_id if facts else None)
                ),
                adjustment_ids=tuple(item.adjustment_id for item in row_adjustments),
                warnings=tuple(warnings),
            )
        )
    return tuple(rows)


def calculate_group_totals(
    rows: Sequence[QuantityRow], group_titles: Mapping[str, str]
) -> Tuple[GroupTotal, ...]:
    """Return one net total per explicitly assigned group."""

    grouped: Dict[str, list] = {}
    for row in rows:
        if row.group_id is not None:
            grouped.setdefault(row.group_id, []).append(row)
    totals = []
    for group_id, group_rows in grouped.items():
        if group_id not in group_titles:
            raise ValueError("missing title for group {}".format(group_id))
        totals.append(
            GroupTotal(
                group_id=group_id,
                title=normalize_name(group_titles[group_id]),
                length_m=math.fsum(row.net_length_m for row in group_rows),
                area_m2=math.fsum(row.net_area_m2 for row in group_rows),
                piece_count=sum(row.net_piece_count for row in group_rows),
                group_count=sum(row.group_count for row in group_rows),
                symbol_count=sum(row.symbol_count for row in group_rows),
            )
        )
    return tuple(sorted(totals, key=lambda total: _natural_key(total.title)))
