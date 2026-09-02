"""Conservative, auditable duplicate and parallel-path reductions."""

from __future__ import annotations

import bisect
from dataclasses import dataclass
import heapq
import math
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    TypeVar,
)

from .core_quantities import (
    ObjectFact,
    ObjectKind,
    Path2D,
    Point2D,
    QuantityAdjustment,
    SourceKey,
)


# Must match the maximum deviation guaranteed by vw_adapter's successful
# PointAlongPolyN sampling.  When two independently sampled representations
# are compared, their envelopes can differ by twice this amount.
ADAPTIVE_CURVE_ERROR_M = 0.0001


_PointValue = TypeVar("_PointValue")


@dataclass(frozen=True)
class DuplicatePolicy:
    exact_enabled: bool = True
    parallel_enabled: bool = False
    max_spacing_m: float = 0.0
    geometry_tolerance_m: float = 0.0001
    angle_tolerance_deg: float = 1.0
    min_overlap_ratio: float = 0.80
    reject_ambiguous: bool = True
    ambiguity_overlap_delta: float = 0.02

    def __post_init__(self) -> None:
        if not math.isfinite(self.geometry_tolerance_m) or self.geometry_tolerance_m <= 0:
            raise ValueError("geometry_tolerance_m must be positive")
        if not math.isfinite(self.max_spacing_m) or self.max_spacing_m < 0:
            raise ValueError("max_spacing_m must be non-negative")
        if self.parallel_enabled and self.max_spacing_m <= self.geometry_tolerance_m:
            raise ValueError("parallel spacing must exceed geometry tolerance")
        if not (0.0 <= self.angle_tolerance_deg <= 90.0):
            raise ValueError("angle_tolerance_deg must be between 0 and 90")
        if not (0.0 < self.min_overlap_ratio <= 1.0):
            raise ValueError("min_overlap_ratio must be in (0, 1]")
        if not (0.0 <= self.ambiguity_overlap_delta <= 1.0):
            raise ValueError("ambiguity_overlap_delta must be in [0, 1]")


@dataclass(frozen=True)
class DuplicateCluster:
    source_key: SourceKey
    representative_id: str
    duplicate_ids: Tuple[str, ...]


@dataclass(frozen=True)
class ParallelPair:
    source_key: SourceKey
    first_id: str
    second_id: str
    overlap_ratio: float
    mean_spacing_m: float
    centerline_length_m: float


@dataclass(frozen=True)
class DuplicateAnalysis:
    adjustments: Tuple[QuantityAdjustment, ...]
    exact_clusters: Tuple[DuplicateCluster, ...]
    parallel_pairs: Tuple[ParallelPair, ...]
    warnings: Tuple[str, ...]


def _quantize(value: float, tolerance: float) -> int:
    scaled = value / tolerance
    return int(math.floor(scaled + 0.5)) if scaled >= 0 else int(math.ceil(scaled - 0.5))


def _is_redundant_collinear(
    first: Tuple[int, int],
    middle: Tuple[int, int],
    last: Tuple[int, int],
) -> bool:
    """Return whether ``middle`` only subdivides one straight segment.

    The test deliberately operates on the already quantized integer grid.  It
    therefore removes only a point that is exactly collinear at the duplicate
    comparison tolerance and lies between its neighbours.  A reversal, a
    genuine corner, or a sampled curve point remains part of the key.
    """

    first_dx = middle[0] - first[0]
    first_dy = middle[1] - first[1]
    second_dx = last[0] - middle[0]
    second_dy = last[1] - middle[1]
    cross_product = first_dx * second_dy - first_dy * second_dx
    same_direction = first_dx * second_dx + first_dy * second_dy > 0
    return cross_product == 0 and same_direction


def _remove_redundant_cyclic(
    points: Sequence[_PointValue],
    is_redundant: Callable[[_PointValue, _PointValue, _PointValue], bool],
) -> Tuple[_PointValue, ...]:
    """Remove cyclic subdivisions with near-linear predicate work.

    A linked ring avoids rebuilding and rescanning the complete list after
    every deletion.  The minimum-index heap deliberately mirrors the previous
    "remove the first match, then restart" order.  Heap entries also capture
    both neighbours, so a stale result is discarded without another geometry
    predicate call.  Only the two neighbours of a removed point can have
    changed status.
    """

    count = len(points)
    if count <= 3:
        return tuple(points)

    previous = [(index - 1) % count for index in range(count)]
    following = [(index + 1) % count for index in range(count)]
    active = [True] * count
    candidates: List[Tuple[int, int, int]] = []

    def enqueue(index: int) -> None:
        if not active[index]:
            return
        first_index = previous[index]
        last_index = following[index]
        if is_redundant(
            points[first_index], points[index], points[last_index]
        ):
            heapq.heappush(
                candidates, (index, first_index, last_index)
            )

    for index in range(count):
        enqueue(index)

    remaining = count
    while candidates and remaining > 3:
        index, first_index, last_index = heapq.heappop(candidates)
        if (
            not active[index]
            or previous[index] != first_index
            or following[index] != last_index
        ):
            continue

        active[index] = False
        following[first_index] = last_index
        previous[last_index] = first_index
        remaining -= 1
        if remaining > 3:
            enqueue(first_index)
            enqueue(last_index)

    return tuple(point for index, point in enumerate(points) if active[index])


def _remove_redundant_collinear_points(
    points: Tuple[Tuple[int, int], ...], closed: bool
) -> Tuple[Tuple[int, int], ...]:
    """Canonicalize straight subdivisions without simplifying real geometry."""

    if len(points) < 3:
        return points
    if not closed:
        simplified: List[Tuple[int, int]] = []
        for point in points:
            simplified.append(point)
            while len(simplified) >= 3 and _is_redundant_collinear(
                simplified[-3], simplified[-2], simplified[-1]
            ):
                del simplified[-2]
        return tuple(simplified)

    return _remove_redundant_cyclic(points, _is_redundant_collinear)


def _quantized_path(path: Path2D, tolerance: float) -> Tuple[Tuple[int, int], ...]:
    points: List[Tuple[int, int]] = []
    for point in path.points:
        quantized = (_quantize(point.x_m, tolerance), _quantize(point.y_m, tolerance))
        if not points or points[-1] != quantized:
            points.append(quantized)
    if path.closed and len(points) > 1 and points[-1] == points[0]:
        points.pop()
    return _remove_redundant_collinear_points(tuple(points), path.closed)


def _least_rotation(
    points: Tuple[Tuple[int, int], ...]
) -> Tuple[Tuple[int, int], ...]:
    """Return the lexicographically least cyclic rotation in linear time."""

    count = len(points)
    if count < 2:
        return points
    doubled = points + points
    first_index = 0
    second_index = 1
    offset = 0
    while first_index < count and second_index < count and offset < count:
        first = doubled[first_index + offset]
        second = doubled[second_index + offset]
        if first == second:
            offset += 1
            continue
        if first > second:
            first_index = first_index + offset + 1
            if first_index <= second_index:
                first_index = second_index + 1
        else:
            second_index = second_index + offset + 1
            if second_index <= first_index:
                second_index = first_index + 1
        offset = 0
    start = min(first_index, second_index)
    return points[start:] + points[:start]


def _minimum_closed_rotation(points: Tuple[Tuple[int, int], ...]) -> Tuple[Tuple[int, int], ...]:
    if not points:
        return points
    return min(_least_rotation(points), _least_rotation(tuple(reversed(points))))


def exact_geometry_key(
    fact: ObjectFact, tolerance_m: float
) -> Optional[Tuple[object, ...]]:
    """Return a direction/start-point independent path key, or ``None``."""

    if not fact.kind.is_geometry or fact.path is None:
        return None
    points = _quantized_path(fact.path, tolerance_m)
    minimum = 3 if fact.path.closed else 2
    if len(points) < minimum:
        return None
    if fact.path.closed:
        canonical = _minimum_closed_rotation(points)
        family = "closed_path"
    else:
        reversed_points = tuple(reversed(points))
        canonical = min(points, reversed_points)
        family = "open_path"
    return family, canonical


@dataclass(frozen=True)
class _Segment:
    first: Point2D
    second: Point2D
    length_m: float
    unit_x: float
    unit_y: float


def _distance(first: Point2D, second: Point2D) -> float:
    return math.hypot(second.x_m - first.x_m, second.y_m - first.y_m)


def _redundant_collinear_point2d(
    first: Point2D,
    middle: Point2D,
    last: Point2D,
    tolerance: float,
) -> bool:
    """Return whether ``middle`` only subdivides one straight run.

    This normalization happens before segment alignment, so a parallel line
    represented as ``0--5--10`` can safely match ``0--10``.  The projection
    test prevents removal at reversals; the perpendicular test is bounded by
    the user-independent geometry tolerance.
    """

    delta_x = last.x_m - first.x_m
    delta_y = last.y_m - first.y_m
    squared_length = delta_x * delta_x + delta_y * delta_y
    if squared_length <= tolerance * tolerance:
        return False
    factor = ((middle.x_m - first.x_m) * delta_x
              + (middle.y_m - first.y_m) * delta_y) / squared_length
    if factor <= 0.0 or factor >= 1.0:
        return False
    projected = Point2D(
        first.x_m + factor * delta_x,
        first.y_m + factor * delta_y,
    )
    return _distance(middle, projected) <= tolerance


def _remove_redundant_collinear_point2d(
    points: Sequence[Point2D], closed: bool, tolerance: float
) -> List[Point2D]:
    if len(points) < 3:
        return list(points)
    if not closed:
        simplified: List[Point2D] = []
        for point in points:
            simplified.append(point)
            while len(simplified) >= 3 and _redundant_collinear_point2d(
                simplified[-3], simplified[-2], simplified[-1], tolerance
            ):
                del simplified[-2]
        return simplified

    return list(
        _remove_redundant_cyclic(
            points,
            lambda first, middle, last: _redundant_collinear_point2d(
                first, middle, last, tolerance
            ),
        )
    )


def _path_segments(path: Path2D, tolerance: float) -> Tuple[_Segment, ...]:
    points: List[Point2D] = []
    for point in path.points:
        if not points or _distance(points[-1], point) > tolerance:
            points.append(point)
    if path.closed and len(points) > 1 and _distance(points[-1], points[0]) <= tolerance:
        points.pop()
    points = _remove_redundant_collinear_point2d(
        points, path.closed, tolerance)
    pairs = list(zip(points, points[1:]))
    if path.closed and len(points) >= 3:
        pairs.append((points[-1], points[0]))
    segments = []
    for first, second in pairs:
        length = _distance(first, second)
        if length <= tolerance:
            continue
        segments.append(
            _Segment(
                first,
                second,
                length,
                (second.x_m - first.x_m) / length,
                (second.y_m - first.y_m) / length,
            )
        )
    return tuple(segments)


def _bbox(path: Path2D) -> Tuple[float, float, float, float]:
    return (
        min(point.x_m for point in path.points),
        min(point.y_m for point in path.points),
        max(point.x_m for point in path.points),
        max(point.y_m for point in path.points),
    )


def _bbox_near(first: Path2D, second: Path2D, spacing: float) -> bool:
    a = _bbox(first)
    b = _bbox(second)
    return not (
        a[2] + spacing < b[0]
        or b[2] + spacing < a[0]
        or a[3] + spacing < b[1]
        or b[3] + spacing < a[1]
    )


@dataclass(frozen=True)
class _BBoxEntry:
    """Cached path bounds used by the parallel-candidate sweep."""

    fact_index: int
    min_x: float
    min_y: float
    max_x: float
    max_y: float


class _ActiveYIntervals:
    """Dynamic interval index for one x-sweep.

    Leaves are ordered once by ``(min_y, fact_index)``.  Each segment-tree
    node stores the greatest ``max_y`` of its currently active leaves.  A
    query can therefore discard a whole subtree when every interval ends
    below the requested range.  Work is proportional to the reported bbox
    candidates (plus logarithmic index overhead), rather than to every active
    object.
    """

    def __init__(self, entries: Sequence[_BBoxEntry]) -> None:
        ordered = sorted(entries, key=lambda item: (item.min_y, item.fact_index))
        self._fact_indices = tuple(item.fact_index for item in ordered)
        self._min_y = tuple(item.min_y for item in ordered)
        self._positions = {
            fact_index: position
            for position, fact_index in enumerate(self._fact_indices)
        }
        size = 1
        while size < len(ordered):
            size *= 2
        self._size = size
        self._maximum_y = [-math.inf] * (2 * size)

    def _set(self, fact_index: int, maximum_y: float) -> None:
        position = self._size + self._positions[fact_index]
        self._maximum_y[position] = maximum_y
        position //= 2
        while position:
            self._maximum_y[position] = max(
                self._maximum_y[position * 2],
                self._maximum_y[position * 2 + 1],
            )
            position //= 2

    def add(self, entry: _BBoxEntry) -> None:
        self._set(entry.fact_index, entry.max_y)

    def remove(self, entry: _BBoxEntry) -> None:
        self._set(entry.fact_index, -math.inf)

    def overlapping(self, minimum_y: float, maximum_y: float) -> Tuple[int, ...]:
        """Return active ids whose closed y intervals meet the query."""

        upper_position = bisect.bisect_right(self._min_y, maximum_y) - 1
        if upper_position < 0 or not self._fact_indices:
            return ()

        matches: List[int] = []

        def visit(node: int, left: int, right: int) -> None:
            if left > upper_position or self._maximum_y[node] < minimum_y:
                return
            if left == right:
                if left < len(self._fact_indices):
                    matches.append(self._fact_indices[left])
                return
            middle = (left + right) // 2
            visit(node * 2, left, middle)
            if middle < upper_position:
                visit(node * 2 + 1, middle + 1, right)

        visit(1, 0, self._size - 1)
        return tuple(matches)


def _parallel_pair_indices(
    facts: Sequence[ObjectFact], spacing: float
) -> Tuple[Tuple[int, int], ...]:
    """Return exactly the pairs that can pass the bbox/closure prechecks.

    The former nested loop called the expensive geometric comparison for all
    ``n * (n - 1) / 2`` pairs.  This deterministic x sweep expires disjoint
    boxes with a heap and queries y overlap through a segment tree.  Different
    open/closed path families are indexed separately, matching the first
    checks in :func:`_parallel_candidate` without changing acceptance or
    ambiguity rules.
    """

    groups: Dict[bool, List[_BBoxEntry]] = {False: [], True: []}
    for fact_index, fact in enumerate(facts):
        if fact.path is None:
            continue
        min_x, min_y, max_x, max_y = _bbox(fact.path)
        groups[fact.path.closed].append(
            _BBoxEntry(fact_index, min_x, min_y, max_x, max_y)
        )

    pairs: List[Tuple[int, int]] = []
    for entries in groups.values():
        if len(entries) < 2:
            continue
        by_index = {entry.fact_index: entry for entry in entries}
        active_y = _ActiveYIntervals(entries)
        active_x: List[Tuple[float, int]] = []
        for current in sorted(entries, key=lambda item: (item.min_x, item.fact_index)):
            while active_x and active_x[0][0] + spacing < current.min_x:
                _maximum_x, expired_index = heapq.heappop(active_x)
                active_y.remove(by_index[expired_index])

            nearby_indices = active_y.overlapping(
                current.min_y - spacing,
                current.max_y + spacing,
            )
            for other_index in nearby_indices:
                first_index, second_index = sorted(
                    (other_index, current.fact_index)
                )
                pairs.append((first_index, second_index))

            active_y.add(current)
            heapq.heappush(active_x, (current.max_x, current.fact_index))

    # Preserve the old representative-id traversal order.  Later ambiguity
    # and greedy-pair decisions are intentionally unchanged.
    return tuple(sorted(pairs))


def _midpoint(segment: _Segment) -> Point2D:
    return Point2D(
        (segment.first.x_m + segment.second.x_m) * 0.5,
        (segment.first.y_m + segment.second.y_m) * 0.5,
    )


def _point_line_distance(point: Point2D, line: _Segment) -> float:
    delta_x = point.x_m - line.first.x_m
    delta_y = point.y_m - line.first.y_m
    return abs(delta_x * line.unit_y - delta_y * line.unit_x)


def _project(point: Point2D, axis: _Segment) -> float:
    return point.x_m * axis.unit_x + point.y_m * axis.unit_y


def _segment_relation(
    first: _Segment, second: _Segment, policy: DuplicatePolicy
) -> Optional[Tuple[float, float, float]]:
    dot = abs(first.unit_x * second.unit_x + first.unit_y * second.unit_y)
    dot = min(1.0, max(-1.0, dot))
    angle = math.degrees(math.acos(dot))
    if angle > policy.angle_tolerance_deg:
        return None

    # Endpoint checks are essential for slightly diverging long lines. A
    # midpoint-only test can look close while the ends are far outside the
    # user-approved maximum spacing.
    spacing = max(
        _point_line_distance(first.first, second),
        _point_line_distance(first.second, second),
        _point_line_distance(second.first, first),
        _point_line_distance(second.second, first),
    )
    # The user enters the minimum distance *from which* separate measurement
    # starts.  Equality must therefore remain separate; only smaller spacings
    # qualify for a one-line reduction.
    if spacing >= policy.max_spacing_m:
        return None

    first_interval = sorted((_project(first.first, first), _project(first.second, first)))
    second_interval = sorted((_project(second.first, first), _project(second.second, first)))
    overlap = max(
        0.0,
        min(first_interval[1], second_interval[1])
        - max(first_interval[0], second_interval[0]),
    )
    minimum_length = min(first.length_m, second.length_m)
    ratio = min(1.0, overlap / minimum_length) if minimum_length > 0 else 0.0
    return ratio, spacing, overlap


@dataclass(frozen=True)
class _InternalParallelCandidate:
    fact: ObjectFact
    first_segment_index: int
    second_segment_index: int
    overlap_ratio: float
    overlap_length_m: float
    spacing_m: float
    length_difference_m: float

    @property
    def sort_key(self) -> Tuple[object, ...]:
        return (
            -self.overlap_ratio,
            self.spacing_m,
            self.length_difference_m,
            self.fact.object_id,
            self.first_segment_index,
            self.second_segment_index,
        )


def _internal_parallel_candidates(
    fact: ObjectFact, policy: DuplicatePolicy
) -> Tuple[_InternalParallelCandidate, ...]:
    """Find non-coincident parallel runs inside one path geometry."""

    if fact.path is None:
        return ()
    segments = _path_segments(fact.path, policy.geometry_tolerance_m)
    candidates: List[_InternalParallelCandidate] = []
    for first_index, first in enumerate(segments):
        for second_index in range(first_index + 1, len(segments)):
            second = segments[second_index]
            relation = _segment_relation(first, second, policy)
            if relation is None:
                continue
            overlap_ratio, spacing, overlap_length = relation
            if (
                spacing <= policy.geometry_tolerance_m
                or overlap_ratio < policy.min_overlap_ratio
                or overlap_length <= policy.geometry_tolerance_m
            ):
                continue
            candidates.append(
                _InternalParallelCandidate(
                    fact,
                    first_index,
                    second_index,
                    overlap_ratio,
                    overlap_length,
                    spacing,
                    abs(first.length_m - second.length_m),
                )
            )
    return tuple(sorted(candidates, key=lambda item: item.sort_key))


@dataclass(frozen=True)
class _ParallelCandidate:
    first: ObjectFact
    second: ObjectFact
    overlap_ratio: float
    overlap_length_m: float
    mean_spacing_m: float
    length_difference_m: float

    @property
    def sort_key(self) -> Tuple[object, ...]:
        return (
            -self.overlap_ratio,
            self.mean_spacing_m,
            self.length_difference_m,
            self.first.object_id,
            self.second.object_id,
        )


def _segment_alignments(
    segments: Tuple[_Segment, ...], closed: bool
) -> Iterable[Tuple[_Segment, ...]]:
    if not closed:
        yield segments
        yield tuple(reversed(segments))
        return
    for sequence in (segments, tuple(reversed(segments))):
        for index in range(len(sequence)):
            yield sequence[index:] + sequence[:index]


def _is_adaptively_sampled_curve(fact: ObjectFact) -> bool:
    return any("PointAlongPolyN" in warning for warning in fact.warnings)


def _resample_path(
    path: Path2D, sample_segments: int, tolerance: float
) -> Optional[Tuple[Point2D, ...]]:
    """Resample a linear approximation at equal normalized arclength.

    This is used only as a second-stage comparison for curves which the
    Vectorworks adapter already sampled within its declared tolerance.  It
    allows nearby offset curves to have different adaptive vertex counts while
    keeping correspondence deterministic.
    """

    segments = _path_segments(path, tolerance)
    if not segments or sample_segments < 1:
        return None
    total_length = math.fsum(segment.length_m for segment in segments)
    if total_length <= tolerance:
        return None
    sample_count = sample_segments if path.closed else sample_segments + 1
    targets = [
        total_length * index / float(sample_segments)
        for index in range(sample_count)
    ]
    points: List[Point2D] = []
    segment_index = 0
    segment_start_distance = 0.0
    for target in targets:
        while (
            segment_index < len(segments) - 1
            and target > segment_start_distance + segments[segment_index].length_m
        ):
            segment_start_distance += segments[segment_index].length_m
            segment_index += 1
        segment = segments[segment_index]
        fraction = (target - segment_start_distance) / segment.length_m
        fraction = min(1.0, max(0.0, fraction))
        points.append(
            Point2D(
                segment.first.x_m
                + fraction * (segment.second.x_m - segment.first.x_m),
                segment.first.y_m
                + fraction * (segment.second.y_m - segment.first.y_m),
            )
        )
    return tuple(points)


def _point_sequence_segments(
    points: Tuple[Point2D, ...], closed: bool, tolerance: float
) -> Optional[Tuple[_Segment, ...]]:
    pairs = list(zip(points, points[1:]))
    if closed and len(points) >= 3:
        pairs.append((points[-1], points[0]))
    result = []
    for first, second in pairs:
        length = _distance(first, second)
        if length <= tolerance:
            return None
        result.append(
            _Segment(
                first,
                second,
                length,
                (second.x_m - first.x_m) / length,
                (second.y_m - first.y_m) / length,
            )
        )
    return tuple(result)


def _resampled_alignments(
    first: Tuple[Point2D, ...],
    second: Tuple[Point2D, ...],
    closed: bool,
    max_distance: float,
) -> Iterable[Tuple[Point2D, ...]]:
    if not closed:
        yield second
        yield tuple(reversed(second))
        return

    # At most eight nearest possible start stations are evaluated per
    # direction.  A valid offset curve must place the first station within the
    # accepted spacing.  Bounding this set avoids quadratic work on long,
    # densely sampled rings.
    for sequence in (second, tuple(reversed(second))):
        ranked = sorted(
            ((_distance(first[0], point), index)
             for index, point in enumerate(sequence)),
            key=lambda item: (item[0], item[1]),
        )
        for distance, index in ranked[:8]:
            if distance > max_distance:
                continue
            yield sequence[index:] + sequence[:index]


def _resampled_alignment_score(
    first_path: Path2D,
    second_path: Path2D,
    tolerance: float,
    max_distance: float,
    angle_tolerance_deg: float,
) -> Optional[float]:
    first_segments = _path_segments(first_path, tolerance)
    second_segments = _path_segments(second_path, tolerance)
    sample_segments = max(16, len(first_segments), len(second_segments))
    # Beyond this bound a second lossy down-sampling could conceal a local
    # deviation.  Returning no match is conservative; the adapter warning then
    # remains in the audit protocol and the two native lengths stay untouched.
    if sample_segments > 4096:
        return None
    first_points = _resample_path(first_path, sample_segments, tolerance)
    second_points = _resample_path(second_path, sample_segments, tolerance)
    if first_points is None or second_points is None:
        return None

    best = None
    for aligned_second in _resampled_alignments(
        first_points, second_points, first_path.closed, max_distance
    ):
        if len(first_points) != len(aligned_second):
            continue
        distances = tuple(
            _distance(first, second)
            for first, second in zip(first_points, aligned_second)
        )
        if not distances or max(distances) > max_distance:
            continue
        first_tangents = _point_sequence_segments(
            first_points, first_path.closed, tolerance)
        second_tangents = _point_sequence_segments(
            aligned_second, second_path.closed, tolerance)
        if (first_tangents is None or second_tangents is None
                or len(first_tangents) != len(second_tangents)):
            continue
        valid_angles = True
        for first_segment, second_segment in zip(first_tangents, second_tangents):
            dot = abs(
                first_segment.unit_x * second_segment.unit_x
                + first_segment.unit_y * second_segment.unit_y
            )
            dot = min(1.0, max(-1.0, dot))
            if math.degrees(math.acos(dot)) > angle_tolerance_deg:
                valid_angles = False
                break
        if not valid_angles:
            continue
        score = math.fsum(distances) / len(distances)
        if best is None or score < best:
            best = score
    return best


def _resampled_curve_parallel_candidate(
    first: ObjectFact, second: ObjectFact, policy: DuplicatePolicy
) -> Optional[_ParallelCandidate]:
    if first.path is None or second.path is None:
        return None
    if not (_is_adaptively_sampled_curve(first)
            or _is_adaptively_sampled_curve(second)):
        return None
    # Each sampled chord can deviate from its native curve by up to the
    # adapter's declared error.  Reduce the accepted sampled spacing by both
    # envelopes, so an approximation cannot turn an actually out-of-range
    # pair into an accepted pair.
    safe_sample_spacing = (
        policy.max_spacing_m - 2.0 * ADAPTIVE_CURVE_ERROR_M)
    if safe_sample_spacing <= policy.geometry_tolerance_m:
        return None
    mean_spacing = _resampled_alignment_score(
        first.path,
        second.path,
        policy.geometry_tolerance_m,
        safe_sample_spacing,
        policy.angle_tolerance_deg,
    )
    if mean_spacing is None:
        return None
    mean_spacing += 2.0 * ADAPTIVE_CURVE_ERROR_M
    if (
        mean_spacing <= policy.geometry_tolerance_m
        or mean_spacing >= policy.max_spacing_m
    ):
        return None
    first_length = first.measured_length_m
    second_length = second.measured_length_m
    longer = max(first_length, second_length)
    if longer <= policy.geometry_tolerance_m:
        return None
    overlap_length = min(first_length, second_length)
    overlap_ratio = min(1.0, overlap_length / longer)
    if overlap_ratio < policy.min_overlap_ratio:
        return None
    return _ParallelCandidate(
        first,
        second,
        overlap_ratio,
        overlap_length,
        mean_spacing,
        abs(first_length - second_length),
    )


def _parallel_candidate(
    first: ObjectFact, second: ObjectFact, policy: DuplicatePolicy
) -> Optional[_ParallelCandidate]:
    if first.path is None or second.path is None:
        return None
    if first.path.closed != second.path.closed:
        return None
    if not _bbox_near(first.path, second.path, policy.max_spacing_m):
        return None
    first_segments = _path_segments(first.path, policy.geometry_tolerance_m)
    second_segments = _path_segments(second.path, policy.geometry_tolerance_m)
    if not first_segments or not second_segments:
        return None

    # Densely sampled closed curves must not enter the all-rotation segment
    # alignment below (quadratic work).  Their adapter marker selects the
    # bounded normalized-arclength comparison directly.
    if (_is_adaptively_sampled_curve(first)
            or _is_adaptively_sampled_curve(second)):
        return _resampled_curve_parallel_candidate(first, second, policy)

    if len(first_segments) != len(second_segments):
        return None

    first_length = math.fsum(segment.length_m for segment in first_segments)
    second_length = math.fsum(segment.length_m for segment in second_segments)
    best = None
    for aligned_second in _segment_alignments(second_segments, second.path.closed):
        relations = []
        for first_segment, second_segment in zip(first_segments, aligned_second):
            relation = _segment_relation(first_segment, second_segment, policy)
            if relation is None:
                relations = []
                break
            relations.append(relation)
        if not relations:
            continue
        overlap_length = math.fsum(relation[2] for relation in relations)
        # Use the longer path as denominator.  This deliberately rejects a
        # short line that merely covers part of a longer one; averaging those
        # two full lengths would otherwise under-measure the unmatched part.
        overlap_ratio = min(1.0, overlap_length / max(first_length, second_length))
        if overlap_ratio < policy.min_overlap_ratio:
            continue
        weights = [
            min(first_segment.length_m, second_segment.length_m)
            for first_segment, second_segment in zip(first_segments, aligned_second)
        ]
        total_weight = math.fsum(weights)
        mean_spacing = (
            math.fsum(relation[1] * weight for relation, weight in zip(relations, weights))
            / total_weight
        )
        if mean_spacing <= policy.geometry_tolerance_m:
            # Coincident partial paths are not safe to reduce as parallel pairs.
            continue
        score = (-overlap_ratio, mean_spacing, abs(first_length - second_length))
        if best is None or score < best[0]:
            best = (score, overlap_length, mean_spacing)
    if best is None:
        return None
    return _ParallelCandidate(
        first,
        second,
        -best[0][0],
        best[1],
        best[2],
        best[0][2],
    )


def detect_parallel_source_keys(
    objects: Iterable[ObjectFact],
    geometry_tolerance_m: float = 0.0001,
    angle_tolerance_deg: float = 0.01,
    min_overlap_ratio: float = 0.80,
) -> Tuple[SourceKey, ...]:
    """Return class/layer keys containing at least one parallel path pair.

    Detection intentionally has no user spacing limit.  It answers only the
    first-stage question whether two non-coincident paths, or two runs inside
    one path, follow each other in parallel.  The separate quantity policy
    later applies the user-approved minimum spacing for separate measurement.

    Facts are compared only inside the same class and design layer.  This
    prevents geometry on different stories/layers from being interpreted as a
    double line.
    """

    if (not math.isfinite(geometry_tolerance_m)
            or geometry_tolerance_m <= 0.0):
        raise ValueError("geometry_tolerance_m must be positive")

    by_key: Dict[SourceKey, List[ObjectFact]] = {}
    for fact in objects:
        if fact.kind.is_geometry and fact.path is not None:
            by_key.setdefault(fact.source_key, []).append(fact)

    detected: List[SourceKey] = []
    for source_key in sorted(by_key):
        facts = sorted(by_key[source_key], key=lambda item: item.object_id)

        # All coordinates are finite by Path2D's invariant.  A span larger
        # than the complete source extent cannot reject a pair on spacing;
        # _parallel_candidate therefore decides only shape, direction and
        # overlap at this detection stage.
        x_values = [point.x_m for fact in facts for point in fact.path.points]
        y_values = [point.y_m for fact in facts for point in fact.path.points]
        source_span = max(
            max(x_values) - min(x_values),
            max(y_values) - min(y_values),
            geometry_tolerance_m * 2.0,
        )
        policy = DuplicatePolicy(
            exact_enabled=False,
            parallel_enabled=True,
            max_spacing_m=source_span + geometry_tolerance_m,
            geometry_tolerance_m=geometry_tolerance_m,
            angle_tolerance_deg=angle_tolerance_deg,
            min_overlap_ratio=min_overlap_ratio,
            reject_ambiguous=False,
        )

        if any(_internal_parallel_candidates(fact, policy) for fact in facts):
            detected.append(source_key)
            continue
        if len(facts) < 2:
            continue

        found = False
        for first_index, first in enumerate(facts):
            for second in facts[first_index + 1:]:
                if _parallel_candidate(first, second, policy) is not None:
                    detected.append(source_key)
                    found = True
                    break
            if found:
                break

    return tuple(detected)


def _is_ambiguous(
    candidates: Sequence[_ParallelCandidate], policy: DuplicatePolicy
) -> bool:
    if len(candidates) < 2:
        return False
    ordered = sorted(candidates, key=lambda candidate: candidate.sort_key)
    first, second = ordered[0], ordered[1]
    spacing_delta = max(policy.geometry_tolerance_m, policy.max_spacing_m * 0.10)
    return (
        abs(first.overlap_ratio - second.overlap_ratio)
        <= policy.ambiguity_overlap_delta
        and abs(first.mean_spacing_m - second.mean_spacing_m) <= spacing_delta
    )


def analyze_duplicates(
    objects: Iterable[ObjectFact],
    policies: Optional[Mapping[SourceKey, DuplicatePolicy]] = None,
    default_policy: DuplicatePolicy = DuplicatePolicy(),
) -> DuplicateAnalysis:
    """Build reductions without mutating or discarding any source fact."""

    by_key: Dict[SourceKey, List[ObjectFact]] = {}
    seen_ids = set()
    audit_warnings: List[str] = []
    for fact in objects:
        if fact.object_id in seen_ids:
            raise ValueError("duplicate object_id")
        seen_ids.add(fact.object_id)
        if fact.kind.is_geometry:
            by_key.setdefault(fact.source_key, []).append(fact)
            audit_warnings.extend(
                "Geometriehinweis [%s / %s / %s]: %s"
                % (
                    fact.source_key.class_name,
                    fact.source_key.layer_name,
                    fact.object_id,
                    warning,
                )
                for warning in fact.warnings
                if warning
            )
        elif fact.kind == ObjectKind.UNSUPPORTED:
            details = tuple(warning for warning in fact.warnings if warning) or (
                "Nicht ausgewerteter Objekttyp",
            )
            audit_warnings.extend(
                "Nicht ausgewertet [%s / %s / %s]: %s"
                % (
                    fact.source_key.class_name,
                    fact.source_key.layer_name,
                    fact.object_id,
                    warning,
                )
                for warning in details
            )

    adjustments: List[QuantityAdjustment] = []
    exact_clusters: List[DuplicateCluster] = []
    parallel_pairs: List[ParallelPair] = []
    warnings: List[str] = audit_warnings
    policy_map = policies or {}

    for source_key in sorted(by_key):
        policy = policy_map.get(source_key, default_policy)
        facts = sorted(by_key[source_key], key=lambda fact: fact.object_id)
        representatives = list(facts)

        if policy.exact_enabled:
            grouped: Dict[Tuple[object, ...], List[ObjectFact]] = {}
            without_key = []
            for fact in facts:
                key = exact_geometry_key(fact, policy.geometry_tolerance_m)
                if key is None:
                    without_key.append(fact)
                else:
                    grouped.setdefault(key, []).append(fact)
            representatives = list(without_key)
            for cluster in grouped.values():
                cluster.sort(key=lambda fact: fact.object_id)
                representative = cluster[0]
                representatives.append(representative)
                if len(cluster) < 2:
                    continue
                duplicate_ids = tuple(fact.object_id for fact in cluster[1:])
                exact_clusters.append(
                    DuplicateCluster(source_key, representative.object_id, duplicate_ids)
                )
                adjustments.append(
                    QuantityAdjustment(
                        adjustment_id="exact:" + representative.object_id,
                        source_key=source_key,
                        kind="exact_duplicate",
                        object_ids=tuple(fact.object_id for fact in cluster),
                        length_delta_m=-math.fsum(
                            fact.measured_length_m for fact in cluster[1:]
                        ),
                        area_delta_m2=-math.fsum(
                            fact.measured_area_m2 for fact in cluster[1:]
                        ),
                        piece_delta=-(len(cluster) - 1),
                        note="exact geometry counted once",
                    )
                )

        representatives.sort(key=lambda fact: fact.object_id)
        if not policy.parallel_enabled:
            continue

        candidates: List[_ParallelCandidate] = []
        for first_index, second_index in _parallel_pair_indices(
            representatives, policy.max_spacing_m
        ):
            candidate = _parallel_candidate(
                representatives[first_index], representatives[second_index], policy
            )
            if candidate is not None:
                candidates.append(candidate)

        candidates_by_id: Dict[str, List[_ParallelCandidate]] = {}
        for candidate in candidates:
            candidates_by_id.setdefault(candidate.first.object_id, []).append(candidate)
            candidates_by_id.setdefault(candidate.second.object_id, []).append(candidate)
        ambiguous_ids = {
            object_id
            for object_id, object_candidates in candidates_by_id.items()
            if policy.reject_ambiguous and _is_ambiguous(object_candidates, policy)
        }
        for object_id in sorted(ambiguous_ids):
            warnings.append("ambiguous parallel candidates: " + object_id)

        used_ids = set()
        for candidate in sorted(candidates, key=lambda item: item.sort_key):
            first_id = candidate.first.object_id
            second_id = candidate.second.object_id
            if first_id in ambiguous_ids or second_id in ambiguous_ids:
                continue
            if first_id in used_ids or second_id in used_ids:
                continue
            used_ids.add(first_id)
            used_ids.add(second_id)
            raw_length = candidate.first.measured_length_m + candidate.second.measured_length_m
            if candidate.first.path is not None and candidate.first.path.closed:
                # Complete offset rings describe one closed centerline; their
                # average perimeter is the correct neutral length.
                centerline_length = raw_length * 0.5
            else:
                # For partially overlapping open paths, preserve every
                # unmatched tail and count only the shared run once.
                centerline_length = max(
                    0.0, raw_length - candidate.overlap_length_m)
            parallel_pairs.append(
                ParallelPair(
                    source_key,
                    first_id,
                    second_id,
                    candidate.overlap_ratio,
                    candidate.mean_spacing_m,
                    centerline_length,
                )
            )
            adjustments.append(
                QuantityAdjustment(
                    adjustment_id="parallel:{}:{}".format(first_id, second_id),
                    source_key=source_key,
                    kind="parallel_pair",
                    object_ids=(first_id, second_id),
                    length_delta_m=centerline_length - raw_length,
                    area_delta_m2=0.0,
                    piece_delta=-1,
                    note=("parallel pair measured once across overlap; "
                          "unmatched tails and area unchanged"),
                )
            )

        # A closed or folded path can itself contain parallel runs (for
        # example the two long sides of one narrow rectangle).  Cross-object
        # pairs take precedence so the same measured length is never reduced
        # twice.
        for fact in representatives:
            if fact.object_id in used_ids:
                continue
            used_segment_indexes = set()
            for candidate in _internal_parallel_candidates(fact, policy):
                first_index = candidate.first_segment_index
                second_index = candidate.second_segment_index
                if (
                    first_index in used_segment_indexes
                    or second_index in used_segment_indexes
                ):
                    continue
                used_segment_indexes.add(first_index)
                used_segment_indexes.add(second_index)
                raw_pair_length = (
                    candidate.overlap_length_m
                    + candidate.overlap_length_m
                )
                centerline_length = candidate.overlap_length_m
                pair_id = "{}:{}".format(first_index + 1, second_index + 1)
                parallel_pairs.append(
                    ParallelPair(
                        source_key,
                        fact.object_id,
                        fact.object_id,
                        candidate.overlap_ratio,
                        candidate.spacing_m,
                        centerline_length,
                    )
                )
                adjustments.append(
                    QuantityAdjustment(
                        adjustment_id="parallel-internal:{}:{}".format(
                            fact.object_id, pair_id),
                        source_key=source_key,
                        kind="parallel_segments",
                        object_ids=(fact.object_id,),
                        length_delta_m=centerline_length - raw_pair_length,
                        area_delta_m2=0.0,
                        piece_delta=0,
                        note=(
                            "parallel segments inside one object measured "
                            "once; area and piece count unchanged"
                        ),
                    )
                )

    return DuplicateAnalysis(
        adjustments=tuple(sorted(adjustments, key=lambda item: item.adjustment_id)),
        exact_clusters=tuple(
            sorted(
                exact_clusters,
                key=lambda cluster: (
                    cluster.source_key,
                    cluster.representative_id,
                    cluster.duplicate_ids,
                ),
            )
        ),
        parallel_pairs=tuple(
            sorted(
                parallel_pairs,
                key=lambda pair: (pair.source_key, pair.first_id, pair.second_id),
            )
        ),
        warnings=tuple(sorted(warnings)),
    )
