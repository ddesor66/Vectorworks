"""Pure selection resolution and one-to-one quantity grouping."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Dict, FrozenSet, Iterable, Mapping, Optional, Sequence, Tuple

from .core_patterns import GlobPattern, normalize_name
from .core_quantities import SourceKey


def _casefold_lookup(values: Iterable[str]) -> Dict[str, str]:
    result: Dict[str, str] = {}
    for raw_value in values:
        value = normalize_name(raw_value)
        folded = value.casefold()
        previous = result.get(folded)
        if previous is not None and previous != value:
            raise ValueError("names collide case-insensitively")
        result[folded] = value
    return result


@dataclass(frozen=True)
class DimensionFilter:
    """Filter for one name dimension (classes or layers).

    ``active=False`` means unrestricted.  ``active=True`` with no includes
    intentionally means an empty selection.
    """

    active: bool = False
    include_patterns: Tuple[GlobPattern, ...] = ()
    exclude_patterns: Tuple[GlobPattern, ...] = ()
    explicit_includes: Tuple[str, ...] = ()
    explicit_excludes: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "include_patterns", tuple(self.include_patterns))
        object.__setattr__(self, "exclude_patterns", tuple(self.exclude_patterns))
        object.__setattr__(
            self,
            "explicit_includes",
            tuple(normalize_name(value) for value in self.explicit_includes),
        )
        object.__setattr__(
            self,
            "explicit_excludes",
            tuple(normalize_name(value) for value in self.explicit_excludes),
        )

    @classmethod
    def from_expressions(
        cls,
        active: bool,
        includes: Iterable[str] = (),
        excludes: Iterable[str] = (),
        explicit_includes: Iterable[str] = (),
        explicit_excludes: Iterable[str] = (),
        case_sensitive: bool = False,
    ) -> "DimensionFilter":
        return cls(
            active=active,
            include_patterns=tuple(
                GlobPattern(value, case_sensitive=case_sensitive) for value in includes
            ),
            exclude_patterns=tuple(
                GlobPattern(value, case_sensitive=case_sensitive) for value in excludes
            ),
            explicit_includes=tuple(explicit_includes),
            explicit_excludes=tuple(explicit_excludes),
        )

    def with_explicit_includes(self, values: Iterable[str]) -> "DimensionFilter":
        combined = list(self.explicit_includes)
        existing = {value.casefold() for value in combined}
        for raw_value in values:
            value = normalize_name(raw_value)
            if value.casefold() not in existing:
                combined.append(value)
                existing.add(value.casefold())
        return replace(self, active=True, explicit_includes=tuple(combined))

    def resolve(self, available_names: Iterable[str]) -> FrozenSet[str]:
        lookup = _casefold_lookup(available_names)
        if not self.active:
            return frozenset(lookup.values())

        included = set()
        for explicit in self.explicit_includes:
            actual = lookup.get(explicit.casefold())
            if actual is not None:
                included.add(actual)
        for actual in lookup.values():
            if any(pattern.matches(actual) for pattern in self.include_patterns):
                included.add(actual)

        excluded = set()
        for explicit in self.explicit_excludes:
            actual = lookup.get(explicit.casefold())
            if actual is not None:
                excluded.add(actual)
        for actual in lookup.values():
            if any(pattern.matches(actual) for pattern in self.exclude_patterns):
                excluded.add(actual)
        return frozenset(included.difference(excluded))


@dataclass(frozen=True)
class SelectionSpec:
    classes: DimensionFilter = DimensionFilter()
    layers: DimensionFilter = DimensionFilter()


@dataclass(frozen=True)
class ResolvedSelection:
    class_names: FrozenSet[str]
    layer_names: FrozenSet[str]

    def includes(self, class_name: str, layer_name: str) -> bool:
        return (
            normalize_name(class_name) in self.class_names
            and normalize_name(layer_name) in self.layer_names
        )


def resolve_selection(
    spec: SelectionSpec,
    available_classes: Iterable[str],
    available_layers: Iterable[str],
) -> ResolvedSelection:
    return ResolvedSelection(
        spec.classes.resolve(available_classes),
        spec.layers.resolve(available_layers),
    )


def selected_source_keys(
    source_keys: Iterable[SourceKey], selection: ResolvedSelection
) -> Tuple[SourceKey, ...]:
    unique = {
        key
        for key in source_keys
        if selection.includes(key.class_name, key.layer_name)
    }
    return tuple(
        sorted(unique, key=lambda key: (key.class_name.casefold(), key.layer_name.casefold(), key.layer_id))
    )


@dataclass(frozen=True)
class GroupDefinition:
    group_id: str
    title: str
    members: Tuple[SourceKey, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "group_id", normalize_name(self.group_id))
        object.__setattr__(self, "title", normalize_name(self.title))
        object.__setattr__(self, "members", tuple(self.members))
        if not self.group_id:
            raise ValueError("group_id must not be empty")
        if not self.title.strip():
            raise ValueError("group title must not be empty")


def build_group_assignments(
    selected_keys: Iterable[SourceKey], groups: Sequence[GroupDefinition]
) -> Mapping[SourceKey, str]:
    """Validate that each selected class/layer row belongs to at most one group."""

    allowed = set(selected_keys)
    assignments: Dict[SourceKey, str] = {}
    group_ids = set()
    titles = set()
    for group in groups:
        if group.group_id in group_ids:
            raise ValueError("duplicate group_id")
        group_ids.add(group.group_id)
        folded_title = group.title.casefold()
        if folded_title in titles:
            raise ValueError("duplicate group title")
        titles.add(folded_title)
        for member in group.members:
            if member not in allowed:
                raise ValueError("group contains a non-selected source key")
            if member in assignments:
                raise ValueError("source key belongs to more than one group")
            assignments[member] = group.group_id
    return assignments
