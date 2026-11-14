"""SattLine artifact format rules: preferred extensions and per-mode candidates.

The parser owns SattLine file formats (plan §4). These helpers are the moved
source of truth for the draft/official selection and the per-artifact
draft→official fallback that lives in ``LoaderLookup`` logic (`core/syntax.py`).
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import Enum
from pathlib import Path

from .models import LoadMode


class ArtifactKind(Enum):
    """A distinct SattLine artifact type resolved for a program."""

    CODE = "code"
    GRAPHICS = "graphics"
    DEPS = "deps"
    DISTRIBUTION = "distribution"


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


def find_companion_beside(code_path: Path, extensions: Sequence[str]) -> Path | None:
    """The first companion beside *code_path* whose extension is in *extensions*.

    A companion is anchored to the body it belongs to: the name must match the
    body's stem ignoring case, exactly as code and sidecar lookup does, so a
    companion copied from a case-insensitive filesystem still pairs on Linux.
    *extensions* is ordered by preference.
    """
    wanted = [extension.lower() for extension in extensions]
    exact: dict[str, Path] = {}
    for extension in wanted:
        candidate = code_path.with_suffix(extension)
        if candidate.exists():
            exact.setdefault(extension, candidate)
    if exact:
        return next(exact[extension] for extension in wanted if extension in exact)
    stem = code_path.stem.casefold()
    folded: dict[str, Path] = {}
    try:
        entries = list(code_path.parent.iterdir())
    except OSError:
        return None
    for entry in entries:
        extension = entry.suffix.lower()
        if extension not in wanted or entry.stem.casefold() != stem:
            continue
        folded.setdefault(extension, entry)
    for extension in wanted:
        found = folded.get(extension)
        if found is not None:
            return found
    return None


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

#: Every extension an artifact kind may use, in any load mode. Callers that only
#: need to classify a path derive their sets from these instead of re-spelling
#: the literals.
ALL_CODE_EXTENSIONS: frozenset[str] = frozenset({".s", ".x"})
ALL_DEPS_EXTENSIONS: frozenset[str] = frozenset({".l", ".z"})
ALL_GRAPHICS_EXTENSIONS: frozenset[str] = frozenset({".g", ".y"})
ALL_DISTRIBUTION_EXTENSIONS: frozenset[str] = frozenset({".p", ".q"})


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
