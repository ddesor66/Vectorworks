"""Unicode-aware glob matching and safe capture-based rename planning.

This module deliberately contains no Vectorworks imports.  It turns user input
into deterministic data that a thin Vectorworks adapter can preview and apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
import hashlib
import re
import unicodedata
from typing import Iterable, List, Optional, Sequence, Tuple


class PatternSyntaxError(ValueError):
    """Raised when a glob or replacement contains an invalid escape."""


class RenameRuleError(ValueError):
    """Raised when a capture rename rule is internally inconsistent."""


def normalize_name(value: str) -> str:
    """Return a stable Unicode representation without changing whitespace."""

    if not isinstance(value, str):
        raise TypeError("name must be a string")
    return unicodedata.normalize("NFC", value)


@dataclass(frozen=True)
class _Token:
    kind: str
    value: str = ""


def _tokenize_glob(expression: str) -> Tuple[_Token, ...]:
    expression = normalize_name(expression)
    tokens: List[_Token] = []
    literal: List[str] = []

    def flush_literal() -> None:
        if literal:
            tokens.append(_Token("literal", "".join(literal)))
            literal[:] = []

    index = 0
    while index < len(expression):
        char = expression[index]
        if char == "\\":
            if index + 1 >= len(expression):
                raise PatternSyntaxError("dangling escape at end of pattern")
            literal.append(expression[index + 1])
            index += 2
            continue
        if char == "*":
            flush_literal()
            tokens.append(_Token("star"))
        elif char == "?":
            flush_literal()
            tokens.append(_Token("question"))
        else:
            literal.append(char)
        index += 1
    flush_literal()
    return tuple(tokens)


def _regex_from_tokens(tokens: Sequence[_Token], capture: bool) -> str:
    parts = ["^"]
    for token in tokens:
        if token.kind == "literal":
            parts.append(re.escape(token.value))
        elif token.kind == "star":
            parts.append("(.*?)" if capture else ".*")
        elif token.kind == "question":
            parts.append("(.)" if capture else ".")
        else:  # pragma: no cover - internal invariant
            raise AssertionError("unknown pattern token")
    parts.append("$")
    return "".join(parts)


@dataclass(frozen=True)
class GlobPattern:
    """An anchored glob where only ``*`` and ``?`` are special."""

    expression: str
    case_sensitive: bool = False
    _tokens: Tuple[_Token, ...] = field(init=False, repr=False, compare=False)
    _regex: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        normalized = normalize_name(self.expression)
        tokens = _tokenize_glob(normalized)
        flags = re.DOTALL | (0 if self.case_sensitive else re.IGNORECASE)
        object.__setattr__(self, "expression", normalized)
        object.__setattr__(self, "_tokens", tokens)
        object.__setattr__(
            self, "_regex", re.compile(_regex_from_tokens(tokens, capture=False), flags)
        )

    def matches(self, value: str) -> bool:
        return self._regex.fullmatch(normalize_name(value)) is not None

    def expand(self, values: Iterable[str]) -> Tuple[str, ...]:
        """Return matching actual names in deterministic natural order."""

        normalized = {normalize_name(value) for value in values}
        return tuple(sorted((v for v in normalized if self.matches(v)), key=_natural_key))


def _natural_key(value: str) -> Tuple[object, ...]:
    parts = re.split(r"(\d+)", normalize_name(value).casefold())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def class_catalog_fingerprint(names: Iterable[str]) -> str:
    """Hash the exact normalized class catalog used for a rename preview."""

    ordered = sorted({normalize_name(name) for name in names}, key=_natural_key)
    encoded = "\0".join(ordered).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class _ReplacementToken:
    kind: str
    value: str = ""
    index: int = 0


def _tokenize_replacement(expression: str) -> Tuple[_ReplacementToken, ...]:
    expression = normalize_name(expression)
    tokens: List[_ReplacementToken] = []
    literal: List[str] = []

    def flush_literal() -> None:
        if literal:
            tokens.append(_ReplacementToken("literal", "".join(literal)))
            literal[:] = []

    index = 0
    while index < len(expression):
        char = expression[index]
        if char == "\\":
            if index + 1 >= len(expression):
                raise PatternSyntaxError("dangling escape at end of replacement")
            literal.append(expression[index + 1])
            index += 2
            continue
        if char == "$" and index + 1 < len(expression) and expression[index + 1].isdigit():
            flush_literal()
            end = index + 1
            while end < len(expression) and expression[end].isdigit():
                end += 1
            capture_index = int(expression[index + 1 : end])
            if capture_index < 1:
                raise RenameRuleError("capture references start at $1")
            tokens.append(_ReplacementToken("reference", index=capture_index))
            index = end
            continue
        if char == "$" and index + 1 < len(expression) and expression[index + 1] == "$":
            literal.append("$")
            index += 2
            continue
        if char == "*":
            flush_literal()
            tokens.append(_ReplacementToken("star"))
        elif char == "?":
            flush_literal()
            tokens.append(_ReplacementToken("question"))
        else:
            literal.append(char)
        index += 1
    flush_literal()
    return tuple(tokens)


@dataclass(frozen=True)
class RenameMatch:
    old_name: str
    new_name: str
    captures: Tuple[str, ...]


@dataclass(frozen=True)
class RenameRule:
    """One anchored, capture-producing rename rule.

    The replacement may either use explicit ``$1`` references or shorthand
    wildcards.  Shorthand wildcards must have the same type sequence as the
    source wildcards, which makes ``*-EW-*`` -> ``*-Entwaesserung-*`` safe.
    """

    rule_id: str
    source: str
    target: str
    case_sensitive: bool = False
    _source_tokens: Tuple[_Token, ...] = field(init=False, repr=False, compare=False)
    _target_tokens: Tuple[_ReplacementToken, ...] = field(
        init=False, repr=False, compare=False
    )
    _regex: re.Pattern = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        rule_id = normalize_name(self.rule_id)
        source = normalize_name(self.source)
        target = normalize_name(self.target)
        if not rule_id:
            raise RenameRuleError("rule_id must not be empty")

        source_tokens = _tokenize_glob(source)
        target_tokens = _tokenize_replacement(target)
        source_wildcards = tuple(
            token.kind for token in source_tokens if token.kind in ("star", "question")
        )
        shorthand = tuple(
            token.kind for token in target_tokens if token.kind in ("star", "question")
        )
        explicit = tuple(token for token in target_tokens if token.kind == "reference")
        if shorthand and explicit:
            raise RenameRuleError(
                "do not mix shorthand wildcards with explicit $n references"
            )
        if shorthand != source_wildcards and shorthand:
            raise RenameRuleError(
                "replacement shorthand must repeat the source wildcard type sequence"
            )
        capture_count = len(source_wildcards)
        for token in explicit:
            if token.index > capture_count:
                raise RenameRuleError("replacement references a missing capture")

        flags = re.DOTALL | (0 if self.case_sensitive else re.IGNORECASE)
        object.__setattr__(self, "rule_id", rule_id)
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "target", target)
        object.__setattr__(self, "_source_tokens", source_tokens)
        object.__setattr__(self, "_target_tokens", target_tokens)
        object.__setattr__(
            self, "_regex", re.compile(_regex_from_tokens(source_tokens, capture=True), flags)
        )

    def apply(self, old_name: str) -> Optional[RenameMatch]:
        old_name = normalize_name(old_name)
        match = self._regex.fullmatch(old_name)
        if match is None:
            return None
        captures = tuple(normalize_name(value) for value in match.groups())
        output: List[str] = []
        shorthand_index = 0
        for token in self._target_tokens:
            if token.kind == "literal":
                output.append(token.value)
            elif token.kind == "reference":
                output.append(captures[token.index - 1])
            elif token.kind in ("star", "question"):
                output.append(captures[shorthand_index])
                shorthand_index += 1
            else:  # pragma: no cover - internal invariant
                raise AssertionError("unknown replacement token")
        return RenameMatch(old_name, normalize_name("".join(output)), captures)


class RenameStatus(str, Enum):
    READY = "ready"
    NO_MATCH = "no_match"
    UNCHANGED = "unchanged"
    INVALID = "invalid"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class RenameProposal:
    old_name: str
    new_name: str
    rule_id: Optional[str]
    captures: Tuple[str, ...]
    status: RenameStatus
    messages: Tuple[str, ...] = ()


@dataclass(frozen=True)
class RenameStep:
    old_name: str
    new_name: str
    source_name: str


@dataclass(frozen=True)
class RenamePlan:
    catalog_fingerprint: str
    proposals: Tuple[RenameProposal, ...]
    phase_to_temporary: Tuple[RenameStep, ...]
    phase_to_final: Tuple[RenameStep, ...]

    @property
    def has_conflicts(self) -> bool:
        return any(
            proposal.status in (RenameStatus.INVALID, RenameStatus.CONFLICT)
            for proposal in self.proposals
        )

    @property
    def can_apply(self) -> bool:
        return bool(self.phase_to_final) and not self.has_conflicts

    def catalog_is_current(self, names: Iterable[str]) -> bool:
        return self.catalog_fingerprint == class_catalog_fingerprint(names)


def _invalid_target_messages(
    target: str, system_names_casefold: set, max_length: int
) -> Tuple[str, ...]:
    messages: List[str] = []
    if not target:
        messages.append("target name is empty")
    if len(target) > max_length:
        messages.append("target name exceeds maximum length")
    if any(unicodedata.category(char) == "Cc" for char in target):
        messages.append("target name contains a control character")
    if target.casefold() in system_names_casefold:
        messages.append("target name is reserved")
    return tuple(messages)


def _temporary_name(source: str, occupied_casefold: set, max_length: int) -> str:
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()
    counter = 0
    while True:
        suffix = digest[:12] if counter == 0 else "{}_{:02d}".format(digest[:9], counter)
        candidate = ("__PD_KM_TMP_" + suffix)[:max_length]
        if candidate.casefold() not in occupied_casefold:
            occupied_casefold.add(candidate.casefold())
            return candidate
        counter += 1


def build_rename_plan(
    existing_names: Iterable[str],
    rules: Sequence[RenameRule],
    selected_names: Optional[Iterable[str]] = None,
    system_names: Iterable[str] = ("None", "Keine"),
    max_length: int = 63,
) -> RenamePlan:
    """Create a preview and a two-phase, non-merging rename plan.

    Rules use first-match-wins semantics and are always evaluated against the
    original name.  A plan containing any invalid/conflicting selected row has
    no executable phases; the UI must let the user correct or deselect it and
    rebuild the plan.
    """

    if max_length < 1:
        raise ValueError("max_length must be positive")
    names = tuple(sorted({normalize_name(name) for name in existing_names}, key=_natural_key))
    selected_casefold = (
        {normalize_name(name).casefold() for name in selected_names}
        if selected_names is not None
        else {name.casefold() for name in names}
    )
    by_casefold = {name.casefold(): name for name in names}
    if len(by_casefold) != len(names):
        raise ValueError("existing names collide case-insensitively")
    system_casefold = {normalize_name(name).casefold() for name in system_names}

    proposals: List[RenameProposal] = []
    for old_name in names:
        if old_name.casefold() not in selected_casefold:
            continue
        result: Optional[RenameMatch] = None
        matched_rule: Optional[RenameRule] = None
        for rule in rules:
            result = rule.apply(old_name)
            if result is not None:
                matched_rule = rule
                break
        if result is None or matched_rule is None:
            proposals.append(
                RenameProposal(old_name, old_name, None, (), RenameStatus.NO_MATCH)
            )
            continue
        if old_name.casefold() in system_casefold and result.new_name != old_name:
            proposals.append(
                RenameProposal(
                    old_name,
                    result.new_name,
                    matched_rule.rule_id,
                    result.captures,
                    RenameStatus.INVALID,
                    ("system class cannot be renamed",),
                )
            )
            continue
        if result.new_name == old_name:
            proposals.append(
                RenameProposal(
                    old_name,
                    result.new_name,
                    matched_rule.rule_id,
                    result.captures,
                    RenameStatus.UNCHANGED,
                )
            )
            continue
        messages = _invalid_target_messages(result.new_name, system_casefold, max_length)
        proposals.append(
            RenameProposal(
                old_name,
                result.new_name,
                matched_rule.rule_id,
                result.captures,
                RenameStatus.INVALID if messages else RenameStatus.READY,
                messages,
            )
        )

    # Two sources must never be merged into one target.
    target_to_indexes = {}
    for index, proposal in enumerate(proposals):
        if proposal.status == RenameStatus.READY:
            target_to_indexes.setdefault(proposal.new_name.casefold(), []).append(index)
    for indexes in target_to_indexes.values():
        if len(indexes) > 1:
            for index in indexes:
                proposal = proposals[index]
                proposals[index] = replace(
                    proposal,
                    status=RenameStatus.CONFLICT,
                    messages=proposal.messages + ("multiple sources have the same target",),
                )

    # A target is available only if its current owner is itself in a valid move.
    # Repeat because invalidating one move can make another target unavailable.
    changed = True
    while changed:
        changed = False
        ready_by_old = {
            proposal.old_name.casefold(): proposal
            for proposal in proposals
            if proposal.status == RenameStatus.READY
        }
        for index, proposal in enumerate(proposals):
            if proposal.status != RenameStatus.READY:
                continue
            owner = by_casefold.get(proposal.new_name.casefold())
            if owner is None or owner.casefold() == proposal.old_name.casefold():
                continue
            owner_move = ready_by_old.get(owner.casefold())
            if owner_move is None or owner_move.new_name.casefold() == owner.casefold():
                proposals[index] = replace(
                    proposal,
                    status=RenameStatus.CONFLICT,
                    messages=proposal.messages + ("target class already exists",),
                )
                changed = True

    has_conflicts = any(
        proposal.status in (RenameStatus.INVALID, RenameStatus.CONFLICT)
        for proposal in proposals
    )
    phase_one: List[RenameStep] = []
    phase_two: List[RenameStep] = []
    if not has_conflicts:
        ready = sorted(
            (proposal for proposal in proposals if proposal.status == RenameStatus.READY),
            key=lambda proposal: _natural_key(proposal.old_name),
        )
        occupied = {name.casefold() for name in names}
        occupied.update(proposal.new_name.casefold() for proposal in ready)
        temporary_by_old = {}
        for proposal in ready:
            temporary = _temporary_name(proposal.old_name, occupied, max_length)
            temporary_by_old[proposal.old_name] = temporary
            phase_one.append(RenameStep(proposal.old_name, temporary, proposal.old_name))
        for proposal in ready:
            phase_two.append(
                RenameStep(
                    temporary_by_old[proposal.old_name],
                    proposal.new_name,
                    proposal.old_name,
                )
            )

    return RenamePlan(
        class_catalog_fingerprint(names),
        tuple(proposals),
        tuple(phase_one),
        tuple(phase_two),
    )
