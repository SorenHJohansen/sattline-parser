"""Unit tests for the artifact format rules (``project/formats.py``)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path

import pytest

from sattline_parser.project import (
    ArtifactKind,
    LoadDiagnosticKind,
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
from sattline_parser.project.formats import CompanionIndex


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


def test_find_companion_beside_does_not_pair_across_language_identities(tmp_path: Path) -> None:
    """``Straße`` and ``STRASSE`` are different units, however ``casefold`` reads."""
    body = tmp_path / "Straße.s"
    body.write_text("", encoding="utf-8")
    (tmp_path / "STRASSE.p").write_text("", encoding="utf-8")

    assert find_companion_beside(body, (".p",)) is None


def test_find_companion_beside_prefers_the_exact_stem_before_a_case_variant(tmp_path: Path) -> None:
    body = tmp_path / "Main.s"
    body.write_text("", encoding="utf-8")
    exact = tmp_path / "Main.p"
    exact.write_text("", encoding="utf-8")
    (tmp_path / "MAIN.P").write_text("", encoding="utf-8")

    assert find_companion_beside(body, (".p",)) == exact


def test_find_companion_beside_chooses_a_case_variant_by_sorted_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The winner is the alphabetically first file, not the first listed."""
    body = tmp_path / "main.s"
    body.write_text("", encoding="utf-8")
    first = tmp_path / "MAIN.P"
    first.write_text("", encoding="utf-8")
    second = tmp_path / "Main.p"
    second.write_text("", encoding="utf-8")

    original = Path.iterdir

    def reversed_entries(self: Path) -> list[Path]:
        return sorted(original(self), key=lambda entry: entry.name, reverse=True)

    monkeypatch.setattr(Path, "iterdir", reversed_entries)

    assert find_companion_beside(body, (".p",)) == first
    assert second.exists()


def test_a_companion_collision_is_reported_once_with_the_winner(tmp_path: Path, case_sensitive_fs: None) -> None:
    body = tmp_path / "main.s"
    body.write_text("", encoding="utf-8")
    winner = tmp_path / "MAIN.P"
    winner.write_text("", encoding="utf-8")
    loser = tmp_path / "Main.p"
    loser.write_text("", encoding="utf-8")
    reported: list[tuple[LoadDiagnosticKind, str, str, Path | None]] = []
    index = CompanionIndex(lambda kind, program, detail, path: reported.append((kind, program, detail, path)))

    assert index.find(body, (".p",)) == winner
    assert index.find(body, (".p",)) == winner

    assert len(reported) == 1
    kind, program, detail, path = reported[0]
    assert kind is LoadDiagnosticKind.FOLDED_NAME_COLLISION
    assert program == "MAIN"
    assert "MAIN.P" in detail
    assert "Main.p" in detail
    assert path == winner


def test_a_companion_collision_is_silent_without_a_reporting_callback(tmp_path: Path) -> None:
    body = tmp_path / "main.s"
    body.write_text("", encoding="utf-8")
    (tmp_path / "MAIN.P").write_text("", encoding="utf-8")
    (tmp_path / "Main.p").write_text("", encoding="utf-8")

    assert find_companion_beside(body, (".p",)) == tmp_path / "MAIN.P"
