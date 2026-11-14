"""Tests for the helper scripts that gate documentation and coverage."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any, cast

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {_SCRIPTS / name}.py")
    module = cast(Any, importlib.util.module_from_spec(spec))
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


check_docs = _load("check_docs")
check_branch_coverage = _load("check_branch_coverage")


def test_slug_matches_github_heading_anchors() -> None:
    assert check_docs._slug("Artifact formats") == "artifact-formats"
    assert check_docs._slug("`rules`") == "rules"
    assert check_docs._slug("[Distribution](x.md) companion") == "distribution-companion"
    assert check_docs._slug("Strict versus lenient: a/b") == "strict-versus-lenient-ab"


def test_anchors_suffix_repeated_headings(tmp_path: Path) -> None:
    page = tmp_path / "page.md"
    page.write_text(
        "# Title\n\n## Artifact formats\n\n## Artifact formats\n\n```\n## Not a heading\n```\n",
        encoding="utf-8",
    )

    assert check_docs._anchors(page) == {"title", "artifact-formats", "artifact-formats-1"}


def test_check_links_validates_relative_links_and_anchors(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    target = docs / "target.md"
    target.write_text("# Target page\n\n## Detail\n", encoding="utf-8")
    page = docs / "page.md"
    page.write_text("# Page\n\n[ok](target.md#detail)\n[self](#page)\n[web](https://example.com/x)\n", encoding="utf-8")

    assert check_docs._check_links(page, tmp_path) == []

    page.write_text("[missing file](gone.md)\n[missing anchor](target.md#nope)\n", encoding="utf-8")

    assert check_docs._check_links(page, tmp_path) == [
        "docs/page.md: missing link target gone.md",
        "docs/page.md: missing anchor #nope in target.md#nope",
    ]


def test_markdown_files_covers_nested_docs_fragments_and_root_files(tmp_path: Path) -> None:
    (tmp_path / "docs" / "sub").mkdir(parents=True)
    (tmp_path / "docs" / "sub" / "nested.md").write_text("# Nested\n", encoding="utf-8")
    (tmp_path / "changelog.d").mkdir()
    (tmp_path / "changelog.d" / "slug.added.md").write_text("- **Add.** x\n", encoding="utf-8")
    for name in ("README.md", "AGENTS.md", "CHANGELOG.md", "SECURITY.md"):
        (tmp_path / name).write_text(f"# {name}\n", encoding="utf-8")

    files = check_docs._markdown_files(tmp_path)

    assert tmp_path / "docs" / "sub" / "nested.md" in files
    assert tmp_path / "changelog.d" / "slug.added.md" in files
    assert tmp_path / "SECURITY.md" in files
    assert tmp_path / "README.md" in files


def test_scrubbed_env_drops_pytest_overrides(monkeypatch: Any) -> None:
    monkeypatch.setenv("PYTEST_ADDOPTS", "-k narrow")
    monkeypatch.setenv("PYTEST_PLUGINS", "some_plugin")
    monkeypatch.setenv("SATT_LINE_KEEP", "1")

    env = check_branch_coverage._scrubbed_env()

    assert "PYTEST_ADDOPTS" not in env
    assert "PYTEST_PLUGINS" not in env
    assert env["SATT_LINE_KEEP"] == "1"
