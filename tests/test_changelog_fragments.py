# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false
"""Tests for the ``changelog.d`` fragment assembler."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, cast

import pytest

_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_changelog.py"
_SPEC = importlib.util.spec_from_file_location("build_changelog", _SCRIPT_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load {_SCRIPT_PATH}")
changelog = cast(Any, importlib.util.module_from_spec(_SPEC))
sys.modules[_SPEC.name] = changelog
_SPEC.loader.exec_module(changelog)

_MINIMAL = "# Changelog\n\n## [Unreleased]\n\n## [2026.1.1] - 2026-01-01\n"


def test_render_section_groups_in_keep_a_changelog_order(tmp_path: Path) -> None:
    fragments = [
        changelog.Fragment(tmp_path / "b.fixed.md", "fixed", "- **Fix.** b"),
        changelog.Fragment(tmp_path / "a.removed.md", "removed", "- **Remove.** a"),
        changelog.Fragment(tmp_path / "c.added.md", "added", "- **Add.** c"),
        changelog.Fragment(tmp_path / "d.fixed.md", "fixed", "- **Fix.** d"),
    ]

    section = changelog.render_section(fragments)

    assert section == (
        "### Added\n\n- **Add.** c\n\n### Removed\n\n- **Remove.** a\n\n### Fixed\n\n- **Fix.** b\n\n- **Fix.** d"
    )


@pytest.mark.parametrize(
    ("name", "body", "message"),
    [
        ("bad-name.md", "- **X.** y", "expected <slug>.<type>.md"),
        ("slug.unknown.md", "- **X.** y", "unknown type"),
        ("slug.changed.md", "  ", "fragment is empty"),
        ("slug.changed.md", "not a bullet", "must start with a Markdown bullet"),
    ],
)
def test_load_fragments_rejects_malformed_files(tmp_path: Path, name: str, body: str, message: str) -> None:
    (tmp_path / name).write_text(body, encoding="utf-8")
    with pytest.raises(changelog.ChangelogError, match=message):
        changelog.load_fragments(tmp_path)


def test_load_fragments_skips_the_readme(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("not a fragment", encoding="utf-8")
    (tmp_path / "slug.added.md").write_text("- **Add.** x\n", encoding="utf-8")

    fragments = changelog.load_fragments(tmp_path)

    assert [fragment.body for fragment in fragments] == ["- **Add.** x"]


def test_replace_and_release_keep_the_layout(tmp_path: Path) -> None:
    assert (
        changelog.replace_unreleased(_MINIMAL, "") == "# Changelog\n\n## [Unreleased]\n\n## [2026.1.1] - 2026-01-01\n"
    )

    filled = changelog.replace_unreleased(_MINIMAL, "### Added\n\n- **Add.** x")
    assert filled == ("# Changelog\n\n## [Unreleased]\n\n### Added\n\n- **Add.** x\n\n## [2026.1.1] - 2026-01-01\n")

    released = changelog.release_unreleased(_MINIMAL, "2026.12.0", "2026-12-01", "### Added\n\n- **Add.** x")
    assert released == (
        "# Changelog\n\n## [Unreleased]\n\n## [2026.12.0] - 2026-12-01\n\n"
        "### Added\n\n- **Add.** x\n\n## [2026.1.1] - 2026-01-01\n"
    )


def test_unreleased_helpers_reject_a_missing_section() -> None:
    with pytest.raises(changelog.ChangelogError, match="missing ## \\[Unreleased\\]"):
        changelog.unreleased_body("# Changelog\n")
    with pytest.raises(changelog.ChangelogError, match="missing ## \\[Unreleased\\]"):
        changelog.replace_unreleased("# Changelog\n", "")
    with pytest.raises(changelog.ChangelogError, match="no section after"):
        changelog.replace_unreleased("## [Unreleased]\n\n", "")
    with pytest.raises(changelog.ChangelogError, match="no section after"):
        changelog.release_unreleased("## [Unreleased]\n\n", "2026.12.0", "2026-12-01", "")


def test_main_checks_builds_and_releases(tmp_path: Path) -> None:
    fragment_dir = tmp_path / "changelog.d"
    fragment_dir.mkdir()
    (fragment_dir / "one.added.md").write_text("- **One.** body\n", encoding="utf-8")
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(_MINIMAL, encoding="utf-8")
    common = ["--fragment-dir", str(fragment_dir), "--changelog", str(changelog_path)]

    assert changelog.main(["--check", *common]) == 0

    changelog_path.write_text(changelog.replace_unreleased(_MINIMAL, "- **Hand.** edit"), encoding="utf-8")
    assert changelog.main(["--check", *common]) == 1

    assert changelog.main(common) == 0
    assert "### Added\n\n- **One.** body" in changelog_path.read_text(encoding="utf-8")

    assert changelog.main(["--release", "2026.12.0", "--date", "2026-12-01", *common]) == 0
    released = changelog_path.read_text(encoding="utf-8")
    assert "## [2026.12.0] - 2026-12-01" in released
    assert "### Added\n\n- **One.** body" in released
    assert not (fragment_dir / "one.added.md").exists()


def test_main_rejects_invalid_release_input(tmp_path: Path) -> None:
    fragment_dir = tmp_path / "changelog.d"
    fragment_dir.mkdir()
    changelog_path = tmp_path / "CHANGELOG.md"
    changelog_path.write_text(_MINIMAL, encoding="utf-8")
    common = ["--fragment-dir", str(fragment_dir), "--changelog", str(changelog_path)]

    assert changelog.main(["--release", "bad", *common]) == 1
    assert changelog.main(["--release", "2026.12.0", *common]) == 1
