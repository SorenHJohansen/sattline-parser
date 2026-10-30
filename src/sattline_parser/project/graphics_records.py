"""Structural readers for ``.g`` / ``.y`` graphics companion records.

The readers cover family 1, family 2, family 4 and family 5 (subtype 1 and
subtype 2, including the older layout), plus the binding reader and the
indexed-text loop.

The readers consume *fields*, so a record boundary follows from its own
structure and never from blank lines: the heuristic this replaces changed the
record count of 582 of 743 corpus files when blank lines were removed. Field
meanings are unnamed where unknown; consumption is all that is claimed here.

The readers are byte-faithful to the companion format, which matters for a
companion written with CRLF line endings: ``getc`` consumes the CR, so a
``getc`` + ``LINE()`` pair can read an empty payload and stop before the next
line. Three deviations are deliberate:

* ``WORD()`` consumes the byte that ends the word, including a
  line break. Here a line break is left in the stream for the following
  ``END()``; that is equivalent for every field followed by ``END()``.
* ``MORE()`` cannot tell "more fields" from the padding the
  writer emits before the line break, so the optional trailing fields it guards
  are left to the field's own ``END()``.
* The separator ``getc`` before a picture-display payload does not consume a
  line break, so an LF-only companion reads the payload it actually has.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, NoReturn, cast

_WHITESPACE = " \t\r\n\v\f"
#: Delimiters ``WORD()`` consumes directly; a line break is left to ``END()``.
_WORD_DELIMITERS = " \t\v\f"
_INT_RE = re.compile(r"[+-]?\d+")
_FLOAT_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")
_VERSION_RE = re.compile(r"Syntax version\s+(\d+)\.(\d+)")
_UNTERMINATED_RECORD = "Unterminated graphics record; expected trailing '0' line"

EntryKind = Literal["literal", "variable", "variable_invalid", "other"]


@dataclass(frozen=True, slots=True)
class GraphicsSyntaxVersion:
    """Syntax version from the companion header — the readers branch on it."""

    major: int
    minor: int

    @property
    def reads_picture_shape_byte(self) -> bool:
        """``major > 1 and minor > 18`` reads a separate picture-shape byte."""
        return self.major > 1 and self.minor > 18

    @property
    def uses_legacy_bindings(self) -> bool:
        """``major == 0 and minor < 107`` selects the pre-qualifier layout."""
        return self.major == 0 and self.minor < 107

    @property
    def uses_legacy_picture_display(self) -> bool:
        """``major == 0 and minor <= 96`` selects the legacy layout (no shape byte)."""
        return self.major == 0 and self.minor <= 96

    def is_at_or_after(self, major: int, minor: int) -> bool:
        """Inverse of :meth:`is_before`, named for the polarity of the gate."""
        return not self.is_before(major, minor)

    def is_before(self, major: int, minor: int) -> bool:
        """Whether this version precedes ``major.minor``.

        Two global flags gate older trailing fields: one is set for versions
        before 2.7 (family 1 subrecord 2) and one for versions before 2.18
        (family 1 subrecord 3).
        """
        return (self.major, self.minor) < (major, minor)


#: Assumed version when a companion file carries no ``" Syntax version x.y``
#: header line (synthetic fixtures). Modern layout, so no legacy branch.
DEFAULT_SYNTAX_VERSION = GraphicsSyntaxVersion(major=2, minor=23)


class GraphicsRecordError(Exception):
    """A companion record the reader cannot consume.

    The caller turns this into a ``GraphicsMessage``; return-value handling for
    a failed ``scanf`` is unknown, so the readers fail loudly instead of
    continuing with a stale value. ``severity`` separates a parser limitation
    (a sub-reader that was never implemented) from content that the reader
    rejects.
    """

    message: str
    line: int
    unterminated: bool
    severity: Literal["error", "warning"]

    def __init__(
        self,
        message: str,
        *,
        line: int,
        unterminated: bool = False,
        severity: Literal["error", "warning"] = "error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.unterminated = unterminated
        self.severity = severity


@dataclass(frozen=True, slots=True)
class GraphicsRecordEntry:
    """One indexed picture-display entry from a family-5 subtype-2 record."""

    index: int
    kind: EntryKind
    text: str
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class GraphicsRecord:
    """One companion record, bounded by its own field structure."""

    family_code: int
    start_line: int
    end_line: int
    subtype: int | None = None
    entries: tuple[GraphicsRecordEntry, ...] = ()
    #: Inline default payload of a picture display (``default_disc``/`text`),
    #: which is the path used when no entry matches. ``None`` for other records.
    default_entry: GraphicsRecordEntry | None = None


@dataclass(frozen=True, slots=True)
class CompanionRecords:
    """Every record read from a companion file, plus the first failure."""

    version: GraphicsSyntaxVersion
    records: tuple[GraphicsRecord, ...] = ()
    error: GraphicsRecordError | None = None


class _BaselineKind(StrEnum):
    """Baseline variant passed to the binding reader."""

    B1 = "b1"  # WORD(); "Not" enables a second counted reference
    B2 = "b2"  # I
    B3 = "b3"  # F
    B4 = "b4"  # WORD2(); "Invalid" collapses to an empty string
    B11 = "b11"  # WORD2() — same consumption as B4, different payload meaning
    B12 = "b12"  # WORD2() — same consumption as B4, different payload meaning


@dataclass(frozen=True, slots=True)
class _Binding:
    qualifier: str
    baseline: str | int | float
    baseline_kind: _BaselineKind
    text: str
    line: int
    column: int


class _Scanner:
    """``FILE``-like position with the primitive readers of the companion format."""

    __slots__ = ("_column", "_line", "_position", "_text", "_value_column", "_value_line")

    def __init__(self, text: str, *, position: int = 0, line: int = 1) -> None:
        self._text = text
        self._position = position
        self._line = line
        self._column = self._column_at(position)
        self._value_line = line
        self._value_column = self._column

    @property
    def eof(self) -> bool:
        return self._position >= len(self._text)

    @property
    def line(self) -> int:
        """1-based line number of the next byte to consume."""
        return self._line

    @property
    def column(self) -> int:
        """1-based column number of the next byte to consume."""
        return self._column

    @property
    def value_line(self) -> int:
        """Line the most recently read value started on."""
        return self._value_line

    @property
    def value_column(self) -> int:
        """Column the most recently read value started on."""
        return self._value_column

    def _column_at(self, position: int) -> int:
        return position - self._text.rfind("\n", 0, position)

    def _peek(self) -> str | None:
        return self._text[self._position] if self._position < len(self._text) else None

    def _advance_to(self, end: int) -> None:
        while self._position < end:
            if self._text[self._position] == "\n":
                self._line += 1
            self._position += 1
        self._column = self._column_at(self._position)

    def _take(self) -> str | None:
        if self._position >= len(self._text):
            return None
        char = self._text[self._position]
        self._advance_to(self._position + 1)
        return char

    def _fail_unterminated(self) -> NoReturn:
        raise GraphicsRecordError(_UNTERMINATED_RECORD, line=self._line, unterminated=True)

    def _fail_expected(self, what: str) -> NoReturn:
        raise GraphicsRecordError(f"Malformed graphics record: expected {what}", line=self._line)

    def _begin_value(self) -> None:
        self._value_line = self._line
        self._value_column = self._column

    def skip_whitespace(self) -> None:
        """Skip the whitespace every numeric/word reader skips before a value."""
        while (char := self._peek()) is not None and char in _WHITESPACE:
            self._take()

    def mark(self) -> None:
        """``MARK``: line sync.

        The helper skips lines that do not start in column two. Every
        reader skips whitespace, so a plain skip is equivalent for a well-formed
        companion and cannot desynchronise a record boundary.
        """
        self.skip_whitespace()

    def getc(self) -> str:
        """``getc()`` — one raw byte; used for the picture-shape byte."""
        self._begin_value()
        char = self._take()
        if char is None:
            self._fail_unterminated()
        return char

    def more(self) -> bool:
        """``MORE()``: an optional same-line field follows.

        The helper tests only for LF and never skips whitespace. A CRLF
        companion leaves the CR in place after a numeric read, so both line-break
        bytes count as "nothing more on this line"; after a word the
        reader has already consumed that CR, which is what this matches.
        """
        char = self._peek()
        return char is not None and char not in "\r\n"

    def at_record_start(self) -> bool:
        """Whether the next byte can open a record (a family or subtype number)."""
        char = self._peek()
        return char is not None and (char.isdigit() or char in "+-")

    def read_inline_separator(self) -> None:
        """Consume the single byte the writer puts between a value and a payload.

        A bare ``getc`` would take that byte unconditionally. Here a line break
        is left in the stream so that an LF-only companion (whose writer never
        emitted the separator) still reads an empty payload instead of the next
        line.
        """
        char = self._peek()
        if char is not None and char not in "\r\n":
            self._take()

    def end_line(self) -> None:
        """``END()`` — discard the rest of the line, then consume its LF."""
        end = self._text.find("\n", self._position)
        self._advance_to(len(self._text) if end < 0 else end + 1)

    def read_int(self) -> int:
        """``I`` — ``scanf("%d")``."""
        self.skip_whitespace()
        if self.eof:
            self._fail_unterminated()
        match = _INT_RE.match(self._text, self._position)
        if match is None:
            self._fail_expected("an integer")
        self._begin_value()
        self._advance_to(match.end())
        return int(match.group(0))

    def read_short(self) -> int:
        """``H`` — ``scanf("%hd")``; the corpus values fit the integer range."""
        return self.read_int()

    def read_float(self) -> float:
        """``F`` — ``scanf("%g")``."""
        self.skip_whitespace()
        if self.eof:
            self._fail_unterminated()
        match = _FLOAT_RE.match(self._text, self._position)
        if match is None:
            self._fail_expected("a floating-point number")
        self._begin_value()
        self._advance_to(match.end())
        return float(match.group(0))

    def read_double(self) -> float:
        """``D`` — ``scanf("%lg")``."""
        return self.read_float()

    def read_word(self) -> str:
        """``WORD()``: whitespace-delimited token."""
        self.skip_whitespace()
        if self.eof:
            self._fail_unterminated()
        self._begin_value()
        start = self._position
        end = start
        while end < len(self._text) and self._text[end] not in _WHITESPACE:
            end += 1
        word = self._text[start:end]
        self._advance_to(end)
        if end < len(self._text) and self._text[end] in _WORD_DELIMITERS:
            self._advance_to(end + 1)
        return word

    def read_word2(self) -> str:
        """``WORD2()``: ``WORD()`` with ``Invalid`` -> empty."""
        word = self.read_word()
        return "" if word.casefold() == "invalid" else word

    def read_line(self) -> str:
        """``LINE()``: one ``fgets`` from the current position."""
        if self.eof:
            self._fail_unterminated()
        self._begin_value()
        end = self._text.find("\n", self._position)
        if end < 0:
            line = self._text[self._position :]
            self._advance_to(len(self._text))
        else:
            line = self._text[self._position : end]
            self._advance_to(end + 1)
        return line.rstrip("\r")

    def read_counted_bytes(self, length: int) -> str:
        """The counted payload of ``COUNTED()``; an embedded LF reads as space."""
        self._begin_value()
        chars: list[str] = []
        for _ in range(max(length, 0)):
            char = self._take()
            if char is None:
                break
            chars.append(" " if char in "\r\n" else char)
        return "".join(chars)

    def read_counted(self) -> str:
        """``COUNTED()`` — ``n = I``, ``getc()``, then exactly ``n`` bytes."""
        length = self.read_int()
        self.getc()
        return self.read_counted_bytes(length)


def parse_syntax_version(header: str) -> GraphicsSyntaxVersion:
    """Read ``major``/``minor`` from a companion header line."""
    match = _VERSION_RE.search(header)
    if match is None:
        return DEFAULT_SYNTAX_VERSION
    return GraphicsSyntaxVersion(major=int(match.group(1)), minor=int(match.group(2)))


def read_companion_records(text: str) -> CompanionRecords:
    """Read every record of a companion file, stopping at the first failure."""
    scanner, version = _open_companion(text)
    records: list[GraphicsRecord] = []
    error: GraphicsRecordError | None = None
    while True:
        scanner.skip_whitespace()
        if scanner.eof:
            break
        if not scanner.at_record_start():
            # ``MARK`` line sync at the top level: a line that cannot open a
            # record (a comment, a stray name) is skipped, not reported.
            scanner.end_line()
            continue
        start_line = scanner.line
        try:
            records.append(_read_record(scanner, version, start_line))
        except GraphicsRecordError as exc:
            error = (
                GraphicsRecordError(_UNTERMINATED_RECORD, line=start_line, unterminated=True)
                if exc.unterminated
                else exc
            )
            break
    return CompanionRecords(version=version, records=tuple(records), error=error)


def _open_companion(text: str) -> tuple[_Scanner, GraphicsSyntaxVersion]:
    """Skip the ``" Syntax version ..."`` header line and return the reader."""
    header_end = text.find("\n")
    first_line = text if header_end < 0 else text[:header_end]
    if not first_line.lstrip().startswith('"'):
        return _Scanner(text), DEFAULT_SYNTAX_VERSION
    version = parse_syntax_version(first_line)
    if header_end < 0:
        return _Scanner(text, position=len(text), line=2), version
    return _Scanner(text, position=header_end + 1, line=2), version


def _read_record(scanner: _Scanner, version: GraphicsSyntaxVersion, start_line: int) -> GraphicsRecord:
    family = scanner.read_int()
    if family == 1:
        _read_family_1(scanner, version)
        return GraphicsRecord(family_code=family, start_line=start_line, end_line=scanner.value_line)
    if family == 2:
        _read_family_2(scanner, version)
        return GraphicsRecord(family_code=family, start_line=start_line, end_line=scanner.value_line)
    if family == 4:
        _read_family_4(scanner)
        return GraphicsRecord(family_code=family, start_line=start_line, end_line=scanner.value_line)
    if family == 5:
        subtype, entries, default_entry = _read_family_5(scanner, version)
        return GraphicsRecord(
            family_code=family,
            start_line=start_line,
            end_line=scanner.value_line,
            subtype=subtype,
            entries=entries,
            default_entry=default_entry,
        )
    raise GraphicsRecordError(f"Unsupported graphics record family {family}", line=start_line)


def _fail_unsupported(scanner: _Scanner, what: str) -> NoReturn:
    """Stop on a sub-reader that is not implemented instead of guessing."""
    raise GraphicsRecordError(
        f"Graphics record content is not supported for {what}; record scan stopped",
        line=scanner.line,
        severity="warning",
    )


def _read_doubles(scanner: _Scanner, count: int) -> None:
    for _ in range(count):
        scanner.read_double()


def _read_ints(scanner: _Scanner, count: int) -> None:
    for _ in range(count):
        scanner.read_int()


def _read_float(scanner: _Scanner, count: int) -> None:
    for _ in range(count):
        scanner.read_float()


def _read_bindings(scanner: _Scanner, kind: _BaselineKind, version: GraphicsSyntaxVersion, count: int) -> None:
    for _ in range(count):
        _read_binding(scanner, kind, version)


def _read_family_1(scanner: _Scanner, version: GraphicsSyntaxVersion) -> None:
    """Family 1: ``B1, D4, H, [I2], [B2], END; disc loop``."""
    scanner.mark()
    _read_binding(scanner, _BaselineKind.B1, version)
    _read_doubles(scanner, 4)  # D4
    scanner.read_short()  # H
    # [I2] / [B2] are optional same-line fields; the END below owns the line.
    scanner.end_line()
    while True:
        scanner.mark()
        discriminator = scanner.read_int()
        if discriminator == 0:
            break
        _read_family_1_payload(scanner, discriminator, version)
        scanner.end_line()
    scanner.end_line()


def _read_family_1_payload(scanner: _Scanner, discriminator: int, version: GraphicsSyntaxVersion) -> None:
    """Per-discriminator payload; every reader returns before the outer ``END()``."""
    if discriminator == 1:
        _read_family_1_subrecord_1(scanner, version)
        return
    if discriminator == 2:
        _read_family_1_subrecord_2(scanner, version)
        return
    if discriminator == 4:
        _read_family_1_subrecord_4(scanner, version)
        return
    if discriminator == 3:
        _read_family_1_subrecord_3(scanner, version)
        return
    if discriminator in {5, 6}:
        scanner.read_float()
        scanner.read_short()
        return
    if discriminator == 7:
        _read_family_1_subrecord_7(scanner)
        return
    _fail_unsupported(scanner, f"family 1 discriminator {discriminator}")


def _read_family_1_subrecord_1(scanner: _Scanner, version: GraphicsSyntaxVersion) -> None:
    """Family 1, discriminator 1."""
    _read_doubles(scanner, 3)
    _read_binding(scanner, _BaselineKind.B11, version)
    _read_binding(scanner, _BaselineKind.B11, version)
    _read_ints(scanner, 2)  # H[2]
    _read_ints(scanner, 2)  # I[2]
    if scanner.more():
        scanner.read_int()
        _read_binding(scanner, _BaselineKind.B11, version)
    if scanner.more():
        scanner.read_float()
    if scanner.more():
        _read_ints(scanner, 2)
        _read_binding(scanner, _BaselineKind.B12, version)
    if scanner.more():
        _read_binding(scanner, _BaselineKind.B11, version)
    if scanner.more():
        scanner.read_int()
        scanner.end_line()
        _read_binding(scanner, _BaselineKind.B1, version)
        scanner.read_int()
        _read_binding(scanner, _BaselineKind.B1, version)
        scanner.read_int()
        _read_binding(scanner, _BaselineKind.B1, version)


def _read_family_1_subrecord_4(scanner: _Scanner, version: GraphicsSyntaxVersion) -> None:
    """Family 1 case 4.

    ``I[2]`` is read with one ``scanf("%d%d")``, so the second integer may sit on
    the next physical line; the following ``MORE()`` is evaluated only after both
    have been read.
    """
    _read_ints(scanner, 2)
    _read_binding(scanner, _BaselineKind.B3, version)
    _read_ints(scanner, 2)
    if scanner.more():
        scanner.read_float()
        _read_binding(scanner, _BaselineKind.B2, version)
        _read_binding(scanner, _BaselineKind.B2, version)
    if scanner.more():
        _read_binding(scanner, _BaselineKind.B2, version)


def _read_family_1_subrecord_7(scanner: _Scanner) -> None:
    """Family 1 case 7: ``D[4], H[2], I, [I]``."""
    _read_doubles(scanner, 4)
    _read_ints(scanner, 2)  # H[2]
    scanner.read_int()
    if scanner.more():
        scanner.read_int()


def _read_family_1_subrecord_2(scanner: _Scanner, version: GraphicsSyntaxVersion) -> None:
    """Family 1, discriminator 2."""
    _read_doubles(scanner, 3)
    _read_binding(scanner, _BaselineKind.B3, version)
    _read_binding(scanner, _BaselineKind.B3, version)
    scanner.read_int()
    scanner.read_short()
    _read_ints(scanner, 2)
    if scanner.more():
        scanner.read_int()
    if scanner.more():
        _read_float(scanner, 2)
        _read_binding(scanner, _BaselineKind.B2, version)
    if scanner.more():
        _read_binding(scanner, _BaselineKind.B4, version)
        _read_binding(scanner, _BaselineKind.B1, version)
    if scanner.more():
        scanner.read_int()
        scanner.end_line()
        _read_binding(scanner, _BaselineKind.B1, version)
    # A global flag is set for versions *before* 2.7, and the reader takes
    # its trailing block when that flag is clear.
    if version.is_at_or_after(2, 7):
        _read_binding(scanner, _BaselineKind.B1, version)
        scanner.end_line()
        _read_binding(scanner, _BaselineKind.B3, version)
        _read_binding(scanner, _BaselineKind.B3, version)


def _read_family_1_subrecord_3(scanner: _Scanner, version: GraphicsSyntaxVersion) -> None:
    """Family 1, discriminator 3."""
    scanner.read_int()
    _read_binding(scanner, _BaselineKind.B3, version)
    _read_ints(scanner, 3)
    if scanner.more():
        _read_binding(scanner, _BaselineKind.B2, version)
        _read_binding(scanner, _BaselineKind.B2, version)
    if scanner.more():
        _read_binding(scanner, _BaselineKind.B1, version)
    if scanner.more():
        scanner.read_int()
        _read_binding(scanner, _BaselineKind.B4, version)
    if scanner.more():
        _read_binding(scanner, _BaselineKind.B12, version)
    if scanner.more():
        _read_binding(scanner, _BaselineKind.B4, version)
        _read_binding(scanner, _BaselineKind.B4, version)
    if scanner.more():
        scanner.read_int()
    if scanner.more():
        _read_binding(scanner, _BaselineKind.B1, version)
    if scanner.more():
        _read_bindings(scanner, _BaselineKind.B2, version, 3)
    if scanner.more():
        scanner.read_int()
        scanner.end_line()
        _read_binding(scanner, _BaselineKind.B1, version)
        scanner.read_int()
        _read_binding(scanner, _BaselineKind.B2, version)
    # A global flag is set for versions *before* 2.18, and the reader takes
    # its trailing block when that flag is clear.
    if version.is_at_or_after(2, 18):
        for kind in (
            _BaselineKind.B2,
            _BaselineKind.B12,
            _BaselineKind.B12,
            _BaselineKind.B2,
            _BaselineKind.B2,
            _BaselineKind.B1,
            _BaselineKind.B3,
            _BaselineKind.B1,
        ):
            scanner.end_line()
            _read_binding(scanner, kind, version)


def _read_family_2(scanner: _Scanner, version: GraphicsSyntaxVersion) -> None:
    """Family 2: ``B1, D4, I, H, [I], END; disc loop``."""
    scanner.mark()
    _read_binding(scanner, _BaselineKind.B1, version)
    _read_doubles(scanner, 4)  # D4
    scanner.read_int()  # I
    scanner.read_short()  # H
    # [I] is an optional same-line field; the END below owns the line.
    scanner.end_line()
    while True:
        scanner.mark()
        discriminator = scanner.read_int()
        if discriminator == 0:
            break
        _read_family_2_payload(scanner, discriminator, version)
        scanner.end_line()
    scanner.end_line()


def _read_family_2_payload(scanner: _Scanner, discriminator: int, version: GraphicsSyntaxVersion) -> None:
    if discriminator == 1:
        _read_family_2_subrecord_1(scanner, version)
        return
    if discriminator == 2:
        _read_binding(scanner, _BaselineKind.B3, version)
        scanner.read_float()  # F
        return
    if discriminator == 3:
        # The corpus writes `3 <B3 binding> <D2> <I3> [B2 B2]`: after the
        # discriminator, a binding, then D2 and I3.
        _read_binding(scanner, _BaselineKind.B3, version)
        _read_doubles(scanner, 2)  # D2
        _read_ints(scanner, 3)  # I3
        if scanner.more():
            _read_binding(scanner, _BaselineKind.B2, version)
            _read_binding(scanner, _BaselineKind.B2, version)
        return
    if discriminator == 4:
        scanner.read_int()  # I
        _read_binding(scanner, _BaselineKind.B3, version)
        _read_ints(scanner, 3)  # I3
        # [F, B2, B2] is an optional same-line triple; the trailing END owns it.
        return
    _fail_unsupported(scanner, f"family 2 discriminator {discriminator}")


def _read_family_2_subrecord_1(scanner: _Scanner, version: GraphicsSyntaxVersion) -> None:
    """Family 2, discriminator 1."""
    _read_binding(scanner, _BaselineKind.B3, version)
    _read_binding(scanner, _BaselineKind.B3, version)
    _read_doubles(scanner, 3)
    _read_ints(scanner, 2)
    if scanner.more():
        scanner.read_int()
    if scanner.more():
        _read_float(scanner, 2)
        _read_binding(scanner, _BaselineKind.B2, version)
        scanner.read_short()
        scanner.read_int()


def _read_family_4(scanner: _Scanner) -> None:
    """Family 4: ``D4, H3, [word], trailing = I, END``."""
    scanner.mark()
    _read_doubles(scanner, 4)  # D4
    _read_ints(scanner, 3)  # H3
    # The optional word rides on the H3 line; MARK then starts the trailing
    # integer, which is read but never validated against zero.
    scanner.end_line()
    scanner.read_int()  # trailing
    scanner.end_line()


def _read_family_5(
    scanner: _Scanner, version: GraphicsSyntaxVersion
) -> tuple[int, tuple[GraphicsRecordEntry, ...], GraphicsRecordEntry | None]:
    """Family 5: common properties, subtype, then the subtype reader."""
    scanner.mark()
    _read_binding(scanner, _BaselineKind.B1, version)
    _read_doubles(scanner, 4)  # D4
    scanner.read_short()  # H
    scanner.mark()
    subtype = max(scanner.read_int(), 0)
    scanner.end_line()
    if subtype == 1:
        _read_picture_display_table(scanner, version)
        return subtype, (), None
    if subtype == 2:
        if version.uses_legacy_picture_display:
            _read_picture_display_legacy(scanner, version)
            return subtype, (), None
        entries, default_entry = _read_picture_display(scanner, version)
        return subtype, entries, default_entry
    raise GraphicsRecordError(f"Unsupported graphics record subtype {subtype}", line=scanner.value_line)


def _read_picture_display_table(scanner: _Scanner, version: GraphicsSyntaxVersion) -> None:
    """Picture-display subtype 1 (indexed text table)."""
    scanner.read_line()  # title
    scanner.read_line()  # default text
    scanner.read_int()
    scanner.end_line()
    scanner.read_int()
    scanner.end_line()
    _read_binding(scanner, _BaselineKind.B4, version)
    _read_binding(scanner, _BaselineKind.B2, version)
    count = scanner.read_int()
    scanner.end_line()
    _read_indexed_text_entries(scanner, count)
    scanner.read_int()  # trailing
    scanner.end_line()


def _read_indexed_text_entries(scanner: _Scanner, count: int) -> None:
    """Indexed text table: ``count x { index = I; END; text = read_line; trim }``."""
    for _ in range(max(count, 0)):
        scanner.read_int()
        scanner.end_line()
        scanner.read_line()


def _read_picture_display(
    scanner: _Scanner, version: GraphicsSyntaxVersion
) -> tuple[tuple[GraphicsRecordEntry, ...], GraphicsRecordEntry]:
    """Picture-display subtype 2 for ``major != 0 or minor > 96``."""
    _read_binding(scanner, _BaselineKind.B4, version)
    _read_binding(scanner, _BaselineKind.B2, version)
    count = scanner.read_int()
    scanner.end_line()
    entries: list[GraphicsRecordEntry] = []
    for _ in range(max(count, 0)):
        index = scanner.read_int()
        discriminator = scanner.read_int()
        if discriminator == 0:
            scanner.read_inline_separator()
            raw_text = scanner.read_line()
            entries.append(
                GraphicsRecordEntry(
                    index=index,
                    kind="literal",
                    text=raw_text.strip(),
                    line=scanner.value_line,
                    column=scanner.value_column + (len(raw_text) - len(raw_text.lstrip())),
                )
            )
            continue
        entries.append(_binding_entry(scanner, version, index=index))
        scanner.end_line()
    default_entry = _read_picture_display_default(scanner, version)
    _read_binding(scanner, _BaselineKind.B1, version)
    if version.reads_picture_shape_byte:
        scanner.end_line()
        scanner.getc()  # shape byte: only lowercase 'f' is false
    scanner.end_line()
    scanner.read_int()  # trailing
    scanner.end_line()
    return tuple(entries), default_entry


def _read_picture_display_default(scanner: _Scanner, version: GraphicsSyntaxVersion) -> GraphicsRecordEntry:
    """The payload used when no indexed entry matches.

    ``default_disc == 0`` writes the payload as the rest of the discriminator's
    line; any other discriminator carries a binding payload instead.
    """
    discriminator = scanner.read_int()
    if discriminator != 0:
        entry = _binding_entry(scanner, version, index=discriminator)
        scanner.end_line()
        return entry
    scanner.read_inline_separator()
    # The separator getc comes first, then a WORD2() for versions
    # before 0.100 and a LINE() otherwise (every nonzero-major version).
    if version.major == 0 and version.minor < 100:
        text = scanner.read_word2()
        return GraphicsRecordEntry(
            index=0, kind="literal", text=text, line=scanner.value_line, column=scanner.value_column
        )
    raw_text = scanner.read_line()
    return GraphicsRecordEntry(
        index=0,
        kind="literal",
        text=raw_text.strip(),
        line=scanner.value_line,
        column=scanner.value_column + (len(raw_text) - len(raw_text.lstrip())),
    )


def _read_picture_display_legacy(scanner: _Scanner, version: GraphicsSyntaxVersion) -> None:
    """Picture-display subtype 2 for ``major == 0 and minor <= 96``."""
    scanner.read_line()  # title
    scanner.read_line()  # default text
    scanner.read_int()
    scanner.end_line()
    scanner.read_int()
    scanner.end_line()
    _read_binding(scanner, _BaselineKind.B4, version)
    _read_binding(scanner, _BaselineKind.B2, version)
    count = scanner.read_int()
    scanner.end_line()
    _read_indexed_text_entries(scanner, count)
    marker = scanner.read_int()
    if marker == 0:
        return
    if marker != 55:
        _fail_unsupported(scanner, f"family 5 legacy picture-display marker {marker}")
    _read_binding(scanner, _BaselineKind.B1, version)
    scanner.read_int()  # trailing
    scanner.end_line()


def _binding_entry(scanner: _Scanner, version: GraphicsSyntaxVersion, *, index: int) -> GraphicsRecordEntry:
    binding = _read_binding(scanner, _BaselineKind.B4, version)
    return GraphicsRecordEntry(
        index=index,
        kind=_binding_entry_kind(binding),
        text=binding.text,
        line=binding.line,
        column=binding.column,
    )


def _binding_entry_kind(binding: _Binding) -> EntryKind:
    if binding.qualifier.casefold() != "var":
        return "other"
    # Every entry binding is read as B4, so its baseline is a WORD2 token.
    folded = cast("str", binding.baseline).casefold()
    if not folded:
        return "variable_invalid"
    if folded in {"true", "false"} or folded.lstrip("+-").isdigit():
        return "variable"
    return "other"


def _read_baseline(scanner: _Scanner, kind: _BaselineKind, *, legacy: bool) -> str | int | float:
    if kind is _BaselineKind.B1:
        return scanner.read_int() if legacy else scanner.read_word()
    if kind is _BaselineKind.B2:
        return scanner.read_int()
    if kind is _BaselineKind.B3:
        return scanner.read_float()
    # B4 / B11 / B12 all read a WORD2() baseline; only their payload meaning
    # differs, which does not change consumption.
    return scanner.read_word2()


def _read_binding(scanner: _Scanner, kind: _BaselineKind, version: GraphicsSyntaxVersion) -> _Binding:
    """Read a binding: qualifier, baseline, then a length-delimited payload.

    The reader never calls ``END()``; callers own the rest of the line.
    """
    if version.uses_legacy_bindings:
        length = scanner.read_int()
        if length > 0:
            scanner.getc()
            text = scanner.read_counted_bytes(length)
        else:
            text = scanner.read_word()
        line, column = scanner.value_line, scanner.value_column
        baseline = _read_baseline(scanner, kind, legacy=True)
        return _Binding(qualifier="", baseline=baseline, baseline_kind=kind, text=text, line=line, column=column)
    qualifier = scanner.read_word()
    baseline = _read_baseline(scanner, kind, legacy=False)
    text = ""
    line, column = scanner.value_line, scanner.value_column
    folded = qualifier.casefold()
    if folded == "var":
        text = scanner.read_counted()
        if kind is _BaselineKind.B1 and baseline == "Not":
            scanner.read_counted()  # a second counted reference
    elif folded in {"lit", "expr"}:
        text = scanner.read_counted()
    if text:
        line, column = scanner.value_line, scanner.value_column
    return _Binding(qualifier=qualifier, baseline=baseline, baseline_kind=kind, text=text, line=line, column=column)


__all__ = [
    "DEFAULT_SYNTAX_VERSION",
    "CompanionRecords",
    "GraphicsRecord",
    "GraphicsRecordEntry",
    "GraphicsRecordError",
    "GraphicsSyntaxVersion",
    "parse_syntax_version",
    "read_companion_records",
]
