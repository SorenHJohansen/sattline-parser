"""The quoted header lines that precede a ``BasePicture`` module.

Every unit opens with three quoted lines and an optional description comment.
The lines are editor bookkeeping rather than language syntax, so the parser
keeps their text exactly as written and exposes the fields the editor writes as
derived properties. A line this package does not recognise (an invalid-input
fixture, or a newer spelling) keeps its text and yields ``None`` for the field it
does not carry, so nothing is lost and nothing is invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .expressions import CodeComment

__all__ = ["HeaderInfo"]

_SYNTAX_PREFIX = "syntax version"
_ORIGINAL_DATE_PREFIX = "original file date"
_PROGRAM_DATE_PREFIX = "program date"


def _field_after(text: str, prefix: str) -> str | None:
    """The text after a case-insensitive ``prefix``, or ``None`` when absent."""
    if not text.casefold().startswith(prefix):
        return None
    return text[len(prefix) :].strip().lstrip(":").strip()


@dataclass(frozen=True)
class HeaderInfo:
    """What the file header says, plus the optional change description.

    ``syntax_version_line``, ``original_file_date_line``, and
    ``program_date_line`` hold the text inside the quotes, exactly as written.
    The properties below read the fields the editor writes; an unrecognised line
    keeps its text and yields ``None`` for the field it does not carry.
    """

    syntax_version_line: str
    original_file_date_line: str
    program_date_line: str
    description: CodeComment | None = field(default=None)

    @property
    def syntax_version(self) -> str | None:
        """The editor version, such as ``2.23``."""
        rest = _field_after(self.syntax_version_line, _SYNTAX_PREFIX)
        if rest is None:
            return None
        version, _, _tail = rest.partition(",")
        return version.strip() or None

    @property
    def original_file_date(self) -> str | None:
        """The written original file date; ``---`` when the editor had none."""
        rest = _field_after(self.original_file_date_line, _ORIGINAL_DATE_PREFIX)
        return rest or None

    @property
    def program_date(self) -> str | None:
        """The written program date, without the trailing ``name:`` field."""
        rest = _field_after(self.program_date_line, _PROGRAM_DATE_PREFIX)
        if rest is None:
            return None
        written, _, _name = rest.partition(",")
        return written.strip() or None

    @property
    def program_name(self) -> str | None:
        """The ``name:`` field of the program date line, case-insensitively."""
        for written_field in self.program_date_line.split(","):
            name, separator, value = written_field.partition(":")
            if separator and name.strip().casefold() == "name":
                return value.strip() or None
        return None
