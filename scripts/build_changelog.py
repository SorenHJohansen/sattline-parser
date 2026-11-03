"""Assemble ``changelog.d`` fragments into ``CHANGELOG.md``.

A pull request adds one fragment per user-visible change, named
``<slug>.<type>.md``, where ``type`` is one of the Keep a Changelog headings.
The fragment holds the bullet text only. Because every PR creates its own
file, two open PRs never edit the same changelog lines.

Usage::

    python scripts/build_changelog.py --check
    python scripts/build_changelog.py
    python scripts/build_changelog.py --release 2026.12.0 --date 2026-12-01
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CHANGELOG_PATH = REPO_ROOT / "CHANGELOG.md"
FRAGMENT_DIR = REPO_ROOT / "changelog.d"

UNRELEASED_HEADING = "## [Unreleased]"
UNRELEASED_ERROR = "CHANGELOG.md [Unreleased] must stay empty; add a changelog.d fragment instead"

#: Heading order from Keep a Changelog.
SECTION_TITLES: dict[str, str] = {
    "added": "Added",
    "changed": "Changed",
    "deprecated": "Deprecated",
    "removed": "Removed",
    "fixed": "Fixed",
    "security": "Security",
}

_FRAGMENT_NAME = re.compile(r"^(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.(?P<kind>[a-z]+)$")
_VERSION = re.compile(r"^\d{4}\.\d{1,2}\.\d{1,2}$")
_NEXT_SECTION = "\n## "


@dataclass(frozen=True)
class Fragment:
    """One pending changelog entry read from ``changelog.d``."""

    path: Path
    kind: str
    body: str


class ChangelogError(Exception):
    """A fragment or the changelog does not follow the convention."""


def load_fragments(fragment_dir: Path) -> list[Fragment]:
    """Read and validate every fragment, sorted by file name for determinism."""
    fragments: list[Fragment] = []
    for path in sorted(fragment_dir.glob("*.md")):
        if path.name == "README.md":
            continue
        match = _FRAGMENT_NAME.fullmatch(path.stem)
        if match is None:
            raise ChangelogError(f"{path.name}: expected <slug>.<type>.md")
        kind = match["kind"]
        if kind not in SECTION_TITLES:
            allowed = ", ".join(SECTION_TITLES)
            raise ChangelogError(f"{path.name}: unknown type {kind!r}; expected one of {allowed}")
        body = path.read_text(encoding="utf-8").strip()
        if not body:
            raise ChangelogError(f"{path.name}: fragment is empty")
        if not body.startswith("- "):
            raise ChangelogError(f"{path.name}: fragment must start with a Markdown bullet")
        fragments.append(Fragment(path=path, kind=kind, body=body))
    return fragments


def render_section(fragments: list[Fragment]) -> str:
    """Render fragments grouped under their Keep a Changelog headings."""
    blocks: list[str] = []
    for kind, title in SECTION_TITLES.items():
        bodies = [fragment.body for fragment in fragments if fragment.kind == kind]
        if not bodies:
            continue
        blocks.append(f"### {title}\n\n" + "\n\n".join(bodies))
    return "\n\n".join(blocks)


def unreleased_body(text: str) -> str:
    """Return the current text between ``[Unreleased]`` and the next section."""
    start = text.find(UNRELEASED_HEADING)
    if start == -1:
        raise ChangelogError(f"CHANGELOG.md is missing {UNRELEASED_HEADING}")
    body_start = start + len(UNRELEASED_HEADING)
    next_section = text.find(_NEXT_SECTION, body_start)
    if next_section == -1:
        return text[body_start:]
    return text[body_start:next_section]


def replace_unreleased(text: str, section: str) -> str:
    """Replace the ``[Unreleased]`` body with ``section``."""
    start = text.find(UNRELEASED_HEADING)
    if start == -1:
        raise ChangelogError(f"CHANGELOG.md is missing {UNRELEASED_HEADING}")
    body_start = start + len(UNRELEASED_HEADING)
    next_section = text.find(_NEXT_SECTION, body_start)
    if next_section == -1:
        raise ChangelogError(f"CHANGELOG.md has no section after {UNRELEASED_HEADING}")
    body = f"\n\n{section}\n" if section else "\n"
    return text[:body_start] + body + text[next_section:]


def release_unreleased(text: str, version: str, date: str, section: str) -> str:
    """Move ``section`` under a version heading and reopen an empty ``[Unreleased]``."""
    start = text.find(UNRELEASED_HEADING)
    if start == -1:
        raise ChangelogError(f"CHANGELOG.md is missing {UNRELEASED_HEADING}")
    body_start = start + len(UNRELEASED_HEADING)
    next_section = text.find(_NEXT_SECTION, body_start)
    if next_section == -1:
        raise ChangelogError(f"CHANGELOG.md has no section after {UNRELEASED_HEADING}")
    release_block = f"{UNRELEASED_HEADING}\n\n## [{version}] - {date}\n\n{section}\n"
    return text[:start] + release_block + text[next_section:]


def check(fragment_dir: Path, changelog_path: Path) -> None:
    """Validate fragments and enforce that ``[Unreleased]`` is not hand-edited."""
    fragments = load_fragments(fragment_dir)
    text = changelog_path.read_text(encoding="utf-8")
    if unreleased_body(text).strip():
        raise ChangelogError(UNRELEASED_ERROR)
    print(f"changelog fragments OK ({len(fragments)} pending)")


def build(fragment_dir: Path, changelog_path: Path) -> None:
    """Preview the pending release by filling the ``[Unreleased]`` section."""
    fragments = load_fragments(fragment_dir)
    text = changelog_path.read_text(encoding="utf-8")
    changelog_path.write_text(replace_unreleased(text, render_section(fragments)), encoding="utf-8")
    print(f"assembled {len(fragments)} fragments into {changelog_path.name}")


def release(fragment_dir: Path, changelog_path: Path, version: str, date: str) -> None:
    """Move every fragment into a dated version section and delete the fragments."""
    if _VERSION.fullmatch(version) is None:
        raise ChangelogError(f"invalid version {version!r}; expected YYYY.M.D")
    fragments = load_fragments(fragment_dir)
    if not fragments:
        raise ChangelogError("no fragments to release")
    text = changelog_path.read_text(encoding="utf-8")
    changelog_path.write_text(release_unreleased(text, version, date, render_section(fragments)), encoding="utf-8")
    for fragment in fragments:
        fragment.path.unlink()
    print(f"released {version} with {len(fragments)} fragments")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate fragments and the [Unreleased] section")
    parser.add_argument("--release", metavar="VERSION", help="move fragments into a version section")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="release date (default: today)")
    parser.add_argument("--fragment-dir", type=Path, default=FRAGMENT_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--changelog", type=Path, default=CHANGELOG_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    try:
        if args.release:
            release(args.fragment_dir, args.changelog, args.release, args.date)
        elif args.check:
            check(args.fragment_dir, args.changelog)
        else:
            build(args.fragment_dir, args.changelog)
    except ChangelogError as exc:
        print(f"changelog: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
