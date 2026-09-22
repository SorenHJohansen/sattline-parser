"""SattLine artifact format rules: preferred extensions and per-mode candidates.

The parser owns SattLine file formats (plan §4). These helpers are the moved
source of truth for the draft/official selection and the per-artifact
draft→official fallback that lives in ``LoaderLookup`` logic (`core/syntax.py`).
"""

from __future__ import annotations

from enum import Enum

from .models import LoadMode


class ArtifactKind(Enum):
    """A distinct SattLine artifact type resolved for a program."""

    CODE = "code"
    GRAPHICS = "graphics"
    DEPS = "deps"


def code_ext(mode: LoadMode) -> str:
    """Preferred code extension for ``mode``: ``.s`` (draft) or ``.x`` (official)."""
    return ".x" if mode is LoadMode.OFFICIAL else ".s"


def deps_ext(mode: LoadMode) -> str:
    """Preferred dependency-file extension: ``.l`` (draft) or ``.z`` (official)."""
    return ".z" if mode is LoadMode.OFFICIAL else ".l"


def graphics_ext(mode: LoadMode) -> str:
    """Preferred graphics companion extension: ``.g`` (draft) or ``.y`` (official)."""
    return ".y" if mode is LoadMode.OFFICIAL else ".g"


def code_ext_candidates(mode: LoadMode) -> tuple[str, ...]:
    """Candidate code extensions, most preferred first.

    Draft falls back from ``.s`` to ``.x``; official only accepts ``.x``.
    """
    return (code_ext(mode),) if mode is LoadMode.OFFICIAL else (code_ext(mode), ".x")


def deps_ext_candidates(mode: LoadMode) -> tuple[str, ...]:
    """Candidate dependency-file extensions: draft falls back ``.l`` → ``.z``."""
    return (deps_ext(mode),) if mode is LoadMode.OFFICIAL else (deps_ext(mode), ".z")


def graphics_ext_candidates(mode: LoadMode) -> tuple[str, ...]:
    """Candidate graphics companion extensions: draft falls back ``.g`` → ``.y``."""
    return (".y",) if mode is LoadMode.OFFICIAL else (".g", ".y")


def preferred_extension(kind: ArtifactKind, mode: LoadMode) -> str:
    """The first/most-preferred extension for ``kind`` in ``mode``."""
    if kind is ArtifactKind.CODE:
        return code_ext(mode)
    if kind is ArtifactKind.GRAPHICS:
        return graphics_ext(mode)
    return deps_ext(mode)


def candidate_extensions(kind: ArtifactKind, mode: LoadMode) -> tuple[str, ...]:
    """Candidate extensions for ``kind`` in ``mode``, most preferred first."""
    if kind is ArtifactKind.CODE:
        return code_ext_candidates(mode)
    if kind is ArtifactKind.GRAPHICS:
        return graphics_ext_candidates(mode)
    return deps_ext_candidates(mode)


__all__ = [
    "ArtifactKind",
    "candidate_extensions",
    "code_ext",
    "code_ext_candidates",
    "deps_ext",
    "deps_ext_candidates",
    "graphics_ext",
    "graphics_ext_candidates",
    "preferred_extension",
]
