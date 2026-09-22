"""Unit tests for the Phase 2 artifact format rules (``project/formats.py``)."""

from __future__ import annotations

from enum import Enum

import pytest

from sattline_parser.project import (
    ArtifactKind,
    LoadMode,
    candidate_extensions,
    code_ext,
    code_ext_candidates,
    deps_ext,
    deps_ext_candidates,
    graphics_ext,
    graphics_ext_candidates,
    preferred_extension,
)


def test_artifact_kind_is_enum() -> None:
    assert issubclass(ArtifactKind, Enum)
    assert set(ArtifactKind) == {ArtifactKind.CODE, ArtifactKind.GRAPHICS, ArtifactKind.DEPS}
    assert (ArtifactKind.CODE.value, ArtifactKind.GRAPHICS.value, ArtifactKind.DEPS.value) == (
        "code",
        "graphics",
        "deps",
    )


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(LoadMode.DRAFT, ".s"), (LoadMode.OFFICIAL, ".x")],
)
def test_code_ext(mode: LoadMode, expected: str) -> None:
    assert code_ext(mode) == expected


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(LoadMode.DRAFT, ".l"), (LoadMode.OFFICIAL, ".z")],
)
def test_deps_ext(mode: LoadMode, expected: str) -> None:
    assert deps_ext(mode) == expected


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(LoadMode.DRAFT, ".g"), (LoadMode.OFFICIAL, ".y")],
)
def test_graphics_ext(mode: LoadMode, expected: str) -> None:
    assert graphics_ext(mode) == expected


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(LoadMode.DRAFT, (".s", ".x")), (LoadMode.OFFICIAL, (".x",))],
)
def test_code_ext_candidates(mode: LoadMode, expected: tuple[str, ...]) -> None:
    assert code_ext_candidates(mode) == expected


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(LoadMode.DRAFT, (".l", ".z")), (LoadMode.OFFICIAL, (".z",))],
)
def test_deps_ext_candidates(mode: LoadMode, expected: tuple[str, ...]) -> None:
    assert deps_ext_candidates(mode) == expected


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(LoadMode.DRAFT, (".g", ".y")), (LoadMode.OFFICIAL, (".y",))],
)
def test_graphics_ext_candidates(mode: LoadMode, expected: tuple[str, ...]) -> None:
    assert graphics_ext_candidates(mode) == expected


@pytest.mark.parametrize(
    ("kind", "mode", "expected"),
    [
        (ArtifactKind.CODE, LoadMode.DRAFT, ".s"),
        (ArtifactKind.CODE, LoadMode.OFFICIAL, ".x"),
        (ArtifactKind.GRAPHICS, LoadMode.DRAFT, ".g"),
        (ArtifactKind.GRAPHICS, LoadMode.OFFICIAL, ".y"),
        (ArtifactKind.DEPS, LoadMode.DRAFT, ".l"),
        (ArtifactKind.DEPS, LoadMode.OFFICIAL, ".z"),
    ],
)
def test_preferred_extension(kind: ArtifactKind, mode: LoadMode, expected: str) -> None:
    assert preferred_extension(kind, mode) == expected


@pytest.mark.parametrize(
    ("kind", "mode", "expected"),
    [
        (ArtifactKind.CODE, LoadMode.DRAFT, (".s", ".x")),
        (ArtifactKind.CODE, LoadMode.OFFICIAL, (".x",)),
        (ArtifactKind.GRAPHICS, LoadMode.DRAFT, (".g", ".y")),
        (ArtifactKind.GRAPHICS, LoadMode.OFFICIAL, (".y",)),
        (ArtifactKind.DEPS, LoadMode.DRAFT, (".l", ".z")),
        (ArtifactKind.DEPS, LoadMode.OFFICIAL, (".z",)),
    ],
)
def test_candidate_extensions(kind: ArtifactKind, mode: LoadMode, expected: tuple[str, ...]) -> None:
    assert candidate_extensions(kind, mode) == expected
