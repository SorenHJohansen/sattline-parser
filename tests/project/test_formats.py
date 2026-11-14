"""Unit tests for the Phase 2 artifact format rules (``project/formats.py``)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import pytest

from sattline_parser.project import (
    ArtifactKind,
    LoadMode,
    body_mode,
    candidate_extensions,
    code_ext,
    code_ext_candidates,
    deps_ext,
    deps_ext_candidates,
    distribution_ext,
    distribution_ext_candidates,
    find_companion_beside,
    graphics_ext,
    graphics_ext_candidates,
    preferred_extension,
)


def test_artifact_kind_is_enum() -> None:
    assert issubclass(ArtifactKind, Enum)
    assert set(ArtifactKind) == {
        ArtifactKind.CODE,
        ArtifactKind.GRAPHICS,
        ArtifactKind.DEPS,
        ArtifactKind.DISTRIBUTION,
    }
    assert (ArtifactKind.CODE.value, ArtifactKind.GRAPHICS.value, ArtifactKind.DEPS.value) == (
        "code",
        "graphics",
        "deps",
    )
    assert ArtifactKind.DISTRIBUTION.value == "distribution"


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
    [(LoadMode.DRAFT, ".p"), (LoadMode.OFFICIAL, ".q")],
)
def test_distribution_ext(mode: LoadMode, expected: str) -> None:
    assert distribution_ext(mode) == expected


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
    [(LoadMode.DRAFT, (".g",)), (LoadMode.OFFICIAL, (".y",))],
)
def test_graphics_ext_candidates(mode: LoadMode, expected: tuple[str, ...]) -> None:
    assert graphics_ext_candidates(mode) == expected


@pytest.mark.parametrize(
    ("mode", "expected"),
    [(LoadMode.DRAFT, (".p",)), (LoadMode.OFFICIAL, (".q",))],
)
def test_distribution_ext_candidates(mode: LoadMode, expected: tuple[str, ...]) -> None:
    assert distribution_ext_candidates(mode) == expected


@pytest.mark.parametrize(
    ("kind", "mode", "expected"),
    [
        (ArtifactKind.CODE, LoadMode.DRAFT, ".s"),
        (ArtifactKind.CODE, LoadMode.OFFICIAL, ".x"),
        (ArtifactKind.GRAPHICS, LoadMode.DRAFT, ".g"),
        (ArtifactKind.GRAPHICS, LoadMode.OFFICIAL, ".y"),
        (ArtifactKind.DEPS, LoadMode.DRAFT, ".l"),
        (ArtifactKind.DEPS, LoadMode.OFFICIAL, ".z"),
        (ArtifactKind.DISTRIBUTION, LoadMode.DRAFT, ".p"),
        (ArtifactKind.DISTRIBUTION, LoadMode.OFFICIAL, ".q"),
    ],
)
def test_preferred_extension(kind: ArtifactKind, mode: LoadMode, expected: str) -> None:
    assert preferred_extension(kind, mode) == expected


@pytest.mark.parametrize(
    ("kind", "mode", "expected"),
    [
        (ArtifactKind.CODE, LoadMode.DRAFT, (".s", ".x")),
        (ArtifactKind.CODE, LoadMode.OFFICIAL, (".x",)),
        (ArtifactKind.GRAPHICS, LoadMode.DRAFT, (".g",)),
        (ArtifactKind.GRAPHICS, LoadMode.OFFICIAL, (".y",)),
        (ArtifactKind.DEPS, LoadMode.DRAFT, (".l", ".z")),
        (ArtifactKind.DEPS, LoadMode.OFFICIAL, (".z",)),
        (ArtifactKind.DISTRIBUTION, LoadMode.DRAFT, (".p",)),
        (ArtifactKind.DISTRIBUTION, LoadMode.OFFICIAL, (".q",)),
    ],
)
def test_candidate_extensions(kind: ArtifactKind, mode: LoadMode, expected: tuple[str, ...]) -> None:
    assert candidate_extensions(kind, mode) == expected


def test_body_mode_returns_the_requested_mode_for_a_non_body_suffix() -> None:
    assert body_mode(".h", LoadMode.DRAFT) is LoadMode.DRAFT
    assert body_mode("", LoadMode.OFFICIAL) is LoadMode.OFFICIAL


def test_body_mode_derives_the_family_from_a_body_suffix() -> None:
    assert body_mode(".s", LoadMode.OFFICIAL) is LoadMode.DRAFT
    assert body_mode(".X", LoadMode.DRAFT) is LoadMode.OFFICIAL


def test_find_companion_beside_returns_none_when_the_directory_cannot_be_read(tmp_path: Path) -> None:
    assert find_companion_beside(tmp_path / "absent" / "Main.s", (".g",)) is None


def test_find_companion_beside_ignores_a_directory_with_the_companion_name(tmp_path: Path) -> None:
    body = tmp_path / "Main.s"
    body.write_text("", encoding="utf-8")
    (tmp_path / "Main.p").mkdir()

    assert find_companion_beside(body, (".p",)) is None


def test_find_companion_beside_ignores_a_folded_directory(tmp_path: Path) -> None:
    body = tmp_path / "MAIN.s"
    body.write_text("", encoding="utf-8")
    (tmp_path / "main.p").mkdir()

    assert find_companion_beside(body, (".p",)) is None


def test_find_companion_beside_pairs_a_regular_file_with_a_folded_name(tmp_path: Path) -> None:
    body = tmp_path / "MAIN.s"
    body.write_text("", encoding="utf-8")
    companion = tmp_path / "main.p"
    companion.write_text("", encoding="utf-8")

    assert find_companion_beside(body, (".p",)) == companion
