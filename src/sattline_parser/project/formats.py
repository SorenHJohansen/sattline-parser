"""SattLine artifact format rules: preferred extensions and per-mode candidates.

The draft/official selection and the per-artifact fallback are decided here.
Discovery and the project loader read this table instead of carrying their own
extension lists.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .identity import UnitIdentity
from .models import LoadDiagnosticKind, LoadMode


class ArtifactKind(Enum):
    """A distinct SattLine artifact type resolved for a program."""

    CODE = "code"
    GRAPHICS = "graphics"
    DEPS = "deps"
    DISTRIBUTION = "distribution"


#: Every extension an artifact kind may use, in any load mode. Callers that only
#: need to classify a path derive their sets from these instead of re-spelling
#: the literals.
ALL_CODE_EXTENSIONS: frozenset[str] = frozenset({".s", ".x"})
ALL_DEPS_EXTENSIONS: frozenset[str] = frozenset({".l", ".z"})
ALL_GRAPHICS_EXTENSIONS: frozenset[str] = frozenset({".g", ".y"})
ALL_DISTRIBUTION_EXTENSIONS: frozenset[str] = frozenset({".p", ".q"})


def code_ext(mode: LoadMode) -> str:
    """Preferred code extension for ``mode``: ``.s`` (draft) or ``.x`` (official)."""
    return ".x" if mode is LoadMode.OFFICIAL else ".s"


def deps_ext(mode: LoadMode) -> str:
    """Preferred dependency-file extension: ``.l`` (draft) or ``.z`` (official)."""
    return ".z" if mode is LoadMode.OFFICIAL else ".l"


def graphics_ext(mode: LoadMode) -> str:
    """Preferred graphics companion extension: ``.g`` (draft) or ``.y`` (official)."""
    return ".y" if mode is LoadMode.OFFICIAL else ".g"


def distribution_ext(mode: LoadMode) -> str:
    """Preferred distribution companion extension: ``.p`` (draft) or ``.q`` (official)."""
    return ".q" if mode is LoadMode.OFFICIAL else ".p"


def code_ext_candidates(mode: LoadMode) -> tuple[str, ...]:
    """Candidate code extensions, most preferred first.

    Draft falls back from ``.s`` to ``.x``; official only accepts ``.x``.
    """
    return (code_ext(mode),) if mode is LoadMode.OFFICIAL else (code_ext(mode), ".x")


def deps_ext_candidates(mode: LoadMode) -> tuple[str, ...]:
    """Candidate dependency-file extensions: draft falls back ``.l`` → ``.z``."""
    return (deps_ext(mode),) if mode is LoadMode.OFFICIAL else (deps_ext(mode), ".z")


def graphics_ext_candidates(mode: LoadMode) -> tuple[str, ...]:
    """Candidate graphics companion extensions for ``mode``.

    A companion never crosses families, so the mode's own extension is the only
    candidate; the body's suffix selects the family through
    :func:`companion_extensions_for_code`.
    """
    return (graphics_ext(mode),)


def distribution_ext_candidates(mode: LoadMode) -> tuple[str, ...]:
    """Candidate distribution companion extensions for ``mode``.

    A companion never crosses families, so the mode's own extension is the only
    candidate; the body's suffix selects the family through
    :func:`distribution_extensions_for_code`.
    """
    return (distribution_ext(mode),)


def body_mode(code_suffix: str, mode: LoadMode) -> LoadMode:
    """The artifact family a resolved code body implies.

    The body's own suffix decides: ``.x`` is the official body format and ``.s``
    is the draft one, whatever mode the caller asked for. Any other suffix keeps
    the requested mode. The body is the anchor: sidecars and companions resolve
    only within the family it selects, so a draft body never pairs with an
    official artifact and an official body never pairs with a draft one.
    """
    lowered = code_suffix.lower()
    if lowered == code_ext(LoadMode.OFFICIAL):
        return LoadMode.OFFICIAL
    if lowered == code_ext(LoadMode.DRAFT):
        return LoadMode.DRAFT
    return mode


def find_companion_beside(
    code_path: Path,
    extensions: Sequence[str],
    *,
    index: CompanionIndex | None = None,
) -> Path | None:
    """The first companion beside *code_path* whose extension is in *extensions*.

    A companion is anchored to the body it belongs to: the name must match the
    body's stem under the language name table, exactly as code and sidecar
    lookup does, so a companion copied from a case-insensitive filesystem still
    pairs on Linux while ``Straße`` never pairs with ``STRASSE``. *extensions* is
    ordered by preference.

    The exact stem and extension are checked first, which is one ``stat`` and
    needs no directory scan. A case-variant file is found through *index*, a
    per-load :class:`CompanionIndex`; without one, a local index scans this
    directory once for the call. A directory that holds two case variants of one
    companion is ambiguous: the alphabetically first file wins and the index
    reports the collision when it has somewhere to report it.
    """
    scanner = index if index is not None else CompanionIndex()
    return scanner.find(code_path, extensions)


#: Extensions a companion index tracks. It serves graphics, distribution, and
#: the sidecar family probe, so every artifact resolved beside a body is in one
#: directory scan.
_COMPANION_EXTENSIONS: frozenset[str] = ALL_DEPS_EXTENSIONS | ALL_GRAPHICS_EXTENSIONS | ALL_DISTRIBUTION_EXTENSIONS

#: A callback a companion scan uses to report an ambiguity it found.
CompanionDiagnose = Callable[[LoadDiagnosticKind, str, str, Path | None], None]


@dataclass(frozen=True, slots=True)
class CompanionCollision:
    """Two or more files in one directory that the language considers one name.

    ``paths`` is in sorted file-name order, so ``paths[0]`` is the file that
    pairs and the rest are unreachable through the index.
    """

    base: Path
    folded: str
    extension: str
    paths: tuple[Path, ...]

    @property
    def winner(self) -> Path:
        """The file the index pairs for this name."""
        return self.paths[0]


class CompanionIndex:
    """Lazy per-directory companion lookup for one load.

    One directory is listed once, in sorted file-name order, and indexed by
    language identity and extension. Graphics, distribution, and the sidecar
    family probe share the index, so a tree of units in one directory costs one
    scan rather than one scan per unit per role. The index belongs to a load, so
    a second load sees a changed directory instead of a stale one.
    """

    def __init__(self, diagnose: CompanionDiagnose | None = None) -> None:
        self._diagnose = diagnose
        self._entries: dict[Path, dict[tuple[str, str], tuple[Path, ...]]] = {}
        self._reported: set[tuple[Path, str, str]] = set()

    def _scan(self, base: Path) -> dict[tuple[str, str], tuple[Path, ...]]:
        cached = self._entries.get(base)
        if cached is not None:
            return cached
        entries: dict[tuple[str, str], tuple[Path, ...]] = {}
        try:
            candidates = sorted(base.iterdir(), key=lambda entry: entry.name)
        except OSError:
            candidates = []
        for entry in candidates:
            extension = entry.suffix.lower()
            if extension not in _COMPANION_EXTENSIONS:
                continue
            if not entry.is_file():
                continue
            key = (UnitIdentity.of(entry.stem).key, extension)
            entries[key] = (*entries.get(key, ()), entry)
        self._entries[base] = entries
        return entries

    def find(self, code_path: Path, extensions: Sequence[str]) -> Path | None:
        """The companion of *code_path* among *extensions*, or ``None``.

        An exact stem-and-extension file wins without a directory scan. A
        case-variant file is resolved through the index by the body's language
        identity, so the winner is the alphabetically first file and does not
        depend on directory order. A directory read failure reports no companion,
        never an exception: companion data is optional.
        """
        wanted = tuple(extension.lower() for extension in extensions)
        for extension in wanted:
            exact = code_path.with_suffix(extension)
            if exact.is_file():
                return exact
        entries = self._scan(code_path.parent)
        folded = UnitIdentity.of(code_path.stem).key
        for extension in wanted:
            paths = entries.get((folded, extension))
            if not paths:
                continue
            self._report_collision(CompanionCollision(code_path.parent, folded, extension, paths))
            return paths[0]
        return None

    def _report_collision(self, collision: CompanionCollision) -> None:
        """Report one ambiguous companion name once per load."""
        if len(collision.paths) < 2:
            return
        key = (collision.base, collision.folded, collision.extension)
        if key in self._reported:
            return
        self._reported.add(key)
        if self._diagnose is None:
            return
        names = ", ".join(repr(path.name) for path in collision.paths)
        self._diagnose(
            LoadDiagnosticKind.FOLDED_NAME_COLLISION,
            collision.winner.stem,
            f"{names} fold to one unit name; using {collision.winner.name!r}",
            collision.winner,
        )


def preferred_extension(kind: ArtifactKind, mode: LoadMode) -> str:
    """The first/most-preferred extension for ``kind`` in ``mode``."""
    if kind is ArtifactKind.CODE:
        return code_ext(mode)
    if kind is ArtifactKind.GRAPHICS:
        return graphics_ext(mode)
    if kind is ArtifactKind.DISTRIBUTION:
        return distribution_ext(mode)
    return deps_ext(mode)


def candidate_extensions(kind: ArtifactKind, mode: LoadMode) -> tuple[str, ...]:
    """Candidate extensions for ``kind`` in ``mode``, most preferred first."""
    if kind is ArtifactKind.CODE:
        return code_ext_candidates(mode)
    if kind is ArtifactKind.GRAPHICS:
        return graphics_ext_candidates(mode)
    if kind is ArtifactKind.DISTRIBUTION:
        return distribution_ext_candidates(mode)
    return deps_ext_candidates(mode)


__all__ = [
    "ALL_CODE_EXTENSIONS",
    "ALL_DEPS_EXTENSIONS",
    "ALL_DISTRIBUTION_EXTENSIONS",
    "ALL_GRAPHICS_EXTENSIONS",
    "ArtifactKind",
    "CompanionCollision",
    "CompanionIndex",
    "body_mode",
    "candidate_extensions",
    "code_ext",
    "code_ext_candidates",
    "companion_extensions_for_code",
    "deps_ext",
    "deps_ext_candidates",
    "deps_extensions_for_code",
    "distribution_ext",
    "distribution_ext_candidates",
    "distribution_extensions_for_code",
    "find_companion_beside",
    "graphics_ext",
    "graphics_ext_candidates",
    "preferred_extension",
]


def companion_extensions_for_code(code_suffix: str, mode: LoadMode) -> tuple[str, ...]:
    """Graphics companion candidates for a code file's own suffix.

    The body's suffix decides the artifact family, so a body never pairs with a
    companion from the other family: an official ``.x`` body pairs only with
    ``.y``, and a draft body pairs only with ``.g``.
    """
    return (graphics_ext(body_mode(code_suffix, mode)),)


def deps_extensions_for_code(code_suffix: str, mode: LoadMode) -> tuple[str, ...]:
    """Dependency sidecar candidates for a code file's own suffix.

    The body's suffix decides the artifact family, so a draft body never pairs
    with the official ``.z`` sidecar and an official body never pairs with
    ``.l``.
    """
    return (deps_ext(body_mode(code_suffix, mode)),)


def distribution_extensions_for_code(code_suffix: str, mode: LoadMode) -> tuple[str, ...]:
    """Distribution companion candidates for a code file's own suffix.

    The body's suffix decides the artifact family, so an official ``.x`` body
    pairs only with ``.q`` and a draft body pairs only with ``.p``.
    """
    return (distribution_ext(body_mode(code_suffix, mode)),)
