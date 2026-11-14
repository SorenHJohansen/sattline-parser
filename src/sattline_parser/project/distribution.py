"""Distribution companion parsing and companion-path resolution.

A distribution companion (``.p`` draft, ``.q`` official) records the systems a
unit is sent to. The file is a small nested structure of named groups::

    DistributionData
     ( Version "Distributiondata version 1.0" )
    SourceCodeSystems
     (  )
    ExecutingSystems
     ( Controller
        ( Name "172.18.0.1"
          Download ShortStopReconfig ) )

The scan is structural, not a search for a keyword: a group is only read as an
executing system when it sits inside ``ExecutingSystems``. A companion that does
not match the expected shape raises :class:`DistributionParseError` rather than
reporting an empty list, because "no executing system" and "could not tell" are
different answers.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sattline_parser.source_io import read_text_cp1252

from .formats import (
    ALL_DISTRIBUTION_EXTENSIONS,
    distribution_extensions_for_code,
    find_companion_beside,
)
from .models import DistributionData, DistributionTarget, LoadMode

#: A distribution companion is a small configuration blob, not data. A larger
#: file is refused before it is read, so a pathological companion cannot become
#: a memory vector.
MAX_DISTRIBUTION_COMPANION_BYTES = 1 << 20

__all__ = [
    "MAX_DISTRIBUTION_COMPANION_BYTES",
    "DistributionParseError",
    "parse_distribution_file",
    "parse_distribution_text",
    "resolve_distribution_companion_path",
]


class DistributionParseError(ValueError):
    """A distribution companion does not match the expected structure."""

    def __init__(self, message: str, *, line: int, column: int) -> None:
        self.message = message
        self.line = line
        self.column = column
        super().__init__(f"{message} at {line}:{column}")

    def __reduce__(self) -> tuple[object, tuple[object, ...]]:
        """Preserve the position fields across pickling."""
        return (_rebuild_distribution_error, (self.message, self.line, self.column))


def _rebuild_distribution_error(message: str, line: int, column: int) -> DistributionParseError:
    return DistributionParseError(message, line=line, column=column)


@dataclass(frozen=True, slots=True)
class _Token:
    """A word, a quoted string, or one parenthesis."""

    text: str
    kind: str  # "word" | "string" | "(" | ")"
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class _Group:
    """A named group: ``Name ( item* )``."""

    name: str
    items: tuple[_Token | _Group, ...]
    line: int
    column: int


_WORD_STOP = frozenset(' \t\r\n\f"()')


def _read_string(text: str, index: int, line: int, column: int) -> tuple[_Token, int, int, int]:
    """Read one quoted string, treating a doubled quote as an escaped quote."""
    start_line, start_column = line, column
    index += 1
    column += 1
    parts: list[str] = []
    while True:
        if index >= len(text) or text[index] == "\n":
            raise DistributionParseError("unterminated string", line=start_line, column=start_column)
        char = text[index]
        if char == '"':
            if index + 1 < len(text) and text[index + 1] == '"':
                parts.append('"')
                index += 2
                column += 2
                continue
            return _Token("".join(parts), "string", start_line, start_column), index + 1, line, column + 1
        parts.append(char)
        index += 1
        column += 1


def _read_word(text: str, index: int, line: int, column: int) -> tuple[_Token, int, int, int]:
    """Read one bare word, up to whitespace, a quote, or a parenthesis."""
    start = index
    start_column = column
    while index < len(text) and text[index] not in _WORD_STOP:
        index += 1
        column += 1
    return _Token(text[start:index], "word", line, start_column), index, line, column


def _tokenize(text: str) -> tuple[_Token, ...]:
    """Split the companion into words, quoted strings, and parentheses."""
    tokens: list[_Token] = []
    index = 0
    line = 1
    column = 1
    length = len(text)
    while index < length:
        char = text[index]
        if char == "\n":
            index += 1
            line += 1
            column = 1
            continue
        if char in " \t\r\f":
            index += 1
            column += 1
            continue
        if char in "()":
            tokens.append(_Token(char, char, line, column))
            index += 1
            column += 1
            continue
        if char == '"':
            token, index, line, column = _read_string(text, index, line, column)
        else:
            token, index, line, column = _read_word(text, index, line, column)
        tokens.append(token)
    return tuple(tokens)


#: Companion nesting is two levels deep in every observed file. The cap turns a
#: pathological input into a structured error instead of a ``RecursionError``.
_MAX_NESTING_DEPTH = 32


def _parse_groups(tokens: tuple[_Token, ...]) -> tuple[_Group, ...]:
    """Parse the top-level named groups, rejecting stray tokens."""
    groups: list[_Group] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.kind == ")":
            raise DistributionParseError("unmatched ')'", line=token.line, column=token.column)
        if token.kind != "word":
            raise DistributionParseError(
                f"expected a group name, found {token.kind}", line=token.line, column=token.column
            )
        opener = tokens[index + 1] if index + 1 < len(tokens) else None
        if opener is None or opener.kind != "(":
            raise DistributionParseError(f"expected '(' after {token.text!r}", line=token.line, column=token.column)
        items, index = _parse_items(tokens, index + 2, opened=opener, depth=0)
        groups.append(_Group(token.text, items, token.line, token.column))
    return tuple(groups)


def _parse_items(
    tokens: tuple[_Token, ...],
    index: int,
    *,
    opened: _Token,
    depth: int,
) -> tuple[tuple[_Token | _Group, ...], int]:
    """Parse the body of one group: words, strings, and nested groups."""
    if depth > _MAX_NESTING_DEPTH:
        raise DistributionParseError(
            f"companion nesting is deeper than {_MAX_NESTING_DEPTH} levels",
            line=opened.line,
            column=opened.column,
        )
    items: list[_Token | _Group] = []
    while index < len(tokens):
        token = tokens[index]
        if token.kind == ")":
            return tuple(items), index + 1
        if token.kind != "word":
            items.append(token)
            index += 1
            continue
        follower = tokens[index + 1] if index + 1 < len(tokens) else None
        if follower is not None and follower.kind == "(":
            nested, index = _parse_items(tokens, index + 2, opened=follower, depth=depth + 1)
            items.append(_Group(token.text, nested, token.line, token.column))
            continue
        items.append(token)
        index += 1
    raise DistributionParseError(
        "missing ')' for an open group",
        line=opened.line,
        column=opened.column,
    )


def _single_section(groups: tuple[_Group, ...], name: str) -> _Group:
    """The one group named *name*, compared case-insensitively."""
    matches = [group for group in groups if group.name.casefold() == name.casefold()]
    if not matches:
        line = groups[0].line if groups else 1
        column = groups[0].column if groups else 1
        raise DistributionParseError(f"missing {name!r} section", line=line, column=column)
    if len(matches) > 1:
        extra = matches[1]
        raise DistributionParseError(f"duplicate {name!r} section", line=extra.line, column=extra.column)
    return matches[0]


def _expect_sections(groups: tuple[_Group, ...], allowed: frozenset[str]) -> None:
    """Reject a top-level group the format does not define."""
    for group in groups:
        if group.name.casefold() not in allowed:
            raise DistributionParseError(
                f"unknown distribution section {group.name!r}", line=group.line, column=group.column
            )


def _parse_targets(section: _Group) -> tuple[DistributionTarget, ...]:
    """Read one distribution section into its named targets."""
    targets: list[DistributionTarget] = []
    for group in section.items:
        if not isinstance(group, _Group):
            raise DistributionParseError(
                f"expected a system group in {section.name!r}, found {group.text!r}",
                line=group.line,
                column=group.column,
            )
        targets.append(_parse_target(group, section=section.name))
    return tuple(targets)


def _key_value_pairs(group: _Group) -> tuple[tuple[str, str, _Token], ...]:
    """Read a group body as ``Key Value`` pairs, in file order.

    Every key is a bare word and every value is one word or one quoted string.
    A nested group or an unpaired key means the file does not match the format,
    so it is reported instead of being skipped.
    """
    pairs: list[tuple[str, str, _Token]] = []
    index = 0
    items = group.items
    while index < len(items):
        key = items[index]
        if isinstance(key, _Group):
            raise DistributionParseError(
                f"expected a key in {group.name!r}",
                line=key.line,
                column=key.column,
            )
        if key.kind != "word":
            raise DistributionParseError(
                f"expected a key in {group.name!r}",
                line=key.line,
                column=key.column,
            )
        value = items[index + 1] if index + 1 < len(items) else None
        if value is None:
            raise DistributionParseError(f"key {key.text!r} has no value", line=key.line, column=key.column)
        if isinstance(value, _Group):
            raise DistributionParseError(
                f"key {key.text!r} must have one scalar value",
                line=value.line,
                column=value.column,
            )
        pairs.append((key.text, value.text, key))
        index += 2
    return tuple(pairs)


def _parse_target(group: _Group, *, section: str) -> DistributionTarget:
    """Read one ``Kind ( Name "..." Attribute Value ... )`` target."""
    pairs = _key_value_pairs(group)
    name: str | None = None
    attributes: list[tuple[str, str]] = []
    seen: set[str] = set()
    for key, value, token in pairs:
        folded = key.casefold()
        if folded in seen:
            raise DistributionParseError(
                f"system {group.name!r} in {section!r} repeats key {key!r}",
                line=token.line,
                column=token.column,
            )
        seen.add(folded)
        if folded == "name":
            name = value
        else:
            attributes.append((key, value))
    if name is None:
        raise DistributionParseError(
            f"system {group.name!r} in {section!r} has no Name", line=group.line, column=group.column
        )
    return DistributionTarget(kind=group.name, name=name, attributes=tuple(attributes))


def _parse_version(section: _Group) -> str:
    pairs = _key_value_pairs(section)
    version: str | None = None
    for key, value, token in pairs:
        if key.casefold() != "version":
            raise DistributionParseError(f"unknown DistributionData key {key!r}", line=token.line, column=token.column)
        if version is not None:
            raise DistributionParseError(
                "DistributionData must declare exactly one Version",
                line=token.line,
                column=token.column,
            )
        version = value
    if version is None:
        raise DistributionParseError(
            "DistributionData must declare exactly one Version",
            line=section.line,
            column=section.column,
        )
    return version


def parse_distribution_text(text: str) -> DistributionData:
    """Parse distribution-companion *text* into a :class:`DistributionData`."""
    groups = _parse_groups(_tokenize(text))
    _expect_sections(groups, frozenset({"distributiondata", "sourcecodesystems", "executingsystems"}))
    header = _single_section(groups, "DistributionData")
    source_section = _single_section(groups, "SourceCodeSystems")
    executing_section = _single_section(groups, "ExecutingSystems")
    return DistributionData(
        version=_parse_version(header),
        source_code_systems=_parse_targets(source_section),
        executing_systems=_parse_targets(executing_section),
    )


def parse_distribution_file(path: Path) -> DistributionData:
    """Parse the distribution companion at *path*.

    A companion larger than :data:`MAX_DISTRIBUTION_COMPANION_BYTES` is reported
    as a parse error instead of being read into memory.
    """
    size = path.stat().st_size
    if size > MAX_DISTRIBUTION_COMPANION_BYTES:
        raise DistributionParseError(
            f"companion is {size} bytes, over the {MAX_DISTRIBUTION_COMPANION_BYTES} byte limit",
            line=1,
            column=1,
        )
    return parse_distribution_text(read_text_cp1252(path))


def resolve_distribution_companion_path(code_path: Path, *, mode: LoadMode) -> Path | None:
    """Resolve the distribution companion for ``code_path``.

    The companion always sits in the same directory as the code file (a
    ``with_suffix`` substitution, never a root-ordered lookup). ``.x`` code
    resolves only to ``.q`` and ``.s`` code only to ``.p``; a ``.p`` / ``.q``
    input resolves to itself. The stem matches ignoring case, so a companion
    copied from a case-insensitive filesystem still pairs.
    """
    if code_path.suffix.lower() in ALL_DISTRIBUTION_EXTENSIONS:
        return code_path
    return find_companion_beside(code_path, distribution_extensions_for_code(code_path.suffix, mode))
