"""The three identities the project layer keeps apart.

A consumer may compare the same words in three different ways, and conflating
them has already produced two bugs: a case-folded filesystem path collapsed two
distinct roots, and cycle detection compared logical names while the planner
compared resolved paths.

* :class:`UnitIdentity` is **language identity**: the name a unit is spelled
  with, folded by the CP1252 name table. ``Library`` and ``library`` are one
  unit.
* :class:`ArtifactIdentity` is **filesystem identity**: the resolved path,
  compared with the platform's own rule. On a case-sensitive filesystem
  ``/lib`` and ``/Lib`` are two artifacts; on Windows they are one file.
* A **logical project identity** is the spelling a consumer passes to
  :meth:`SattLineProject.get`. It is preserved on ``SattLineProgram.name`` and
  is only ever folded when it is looked up.

The classes here make the first two explicit and give each one key. Equality and
hashing use the key, so two spellings of one identity are equal and one object
can be used in a set or as a dict key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from sattline_parser.names import fold_identifier

__all__ = ["ArtifactIdentity", "UnitIdentity"]


@dataclass(frozen=True, slots=True)
class UnitIdentity:
    """A unit name for language comparison.

    ``spelling`` is what the source or the caller wrote; it is kept for a
    diagnostic and never compared. ``key`` is the folded identity, and equality
    and hashing use it, so ``UnitIdentity.of("Library") == UnitIdentity.of("library")``.
    """

    key: str
    spelling: str = field(compare=False)

    @classmethod
    def of(cls, name: str) -> UnitIdentity:
        """The identity of *name*, folded by the language name table."""
        return cls(key=fold_identifier(name), spelling=name)


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    """A filesystem path for artifact comparison.

    ``path`` is the path as resolved; it is kept for reading and never
    compared. ``key`` is the platform comparison key, so equality and hashing
    answer "is this the same file", not "is this the same spelling".
    """

    key: str
    path: Path = field(compare=False)

    @classmethod
    def of(cls, path: Path) -> ArtifactIdentity:
        """The identity of *path*, resolved and normalised for this platform."""
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        return cls(key=os.path.normcase(str(resolved)), path=resolved)
