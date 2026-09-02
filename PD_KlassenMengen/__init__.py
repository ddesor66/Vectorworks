"""Pure-Python core for the PD class and quantity tools."""

from .core_patterns import (
    GlobPattern,
    PatternSyntaxError,
    RenamePlan,
    RenameRule,
    build_rename_plan,
)
from .core_quantities import (
    ObjectFact,
    ObjectKind,
    Path2D,
    Point2D,
    QuantityAdjustment,
    QuantityRow,
    SourceKey,
    aggregate_quantities,
)

VERSION = "1.3.13"

__all__ = [
    "GlobPattern",
    "ObjectFact",
    "ObjectKind",
    "Path2D",
    "PatternSyntaxError",
    "Point2D",
    "QuantityAdjustment",
    "QuantityRow",
    "RenamePlan",
    "RenameRule",
    "SourceKey",
    "aggregate_quantities",
    "build_rename_plan",
]
