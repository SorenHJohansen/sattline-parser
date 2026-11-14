"""Check documentation links, prose punctuation, and Mermaid blocks.

The docs set is part of the product. This script keeps it honest:

* every relative Markdown link resolves, including its ``#anchor``;
* no em dash or en dash is used as punctuation outside a code fence;
* Mermaid blocks can be extracted for rendering by the Docs workflow.

Usage::

    python scripts/check_docs.py
    python scripts/check_docs.py --mermaid-dir /tmp/sattline-mermaid
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT_FILES = ("README.md", "AGENTS.md", "CHANGELOG.md", "SECURITY.md")
_DASHES = ("\u2014", "\u2013")
_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
_MERMAID_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)
_LINK_TEXT_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_SLUG_STRIP_RE = re.compile(r"[^\w\- ]", re.UNICODE)


def _markdown_files(root: Path) -> list[Path]:
    """Every Markdown file the documentation gate owns."""
    files = sorted((root / "docs").rglob("*.md"))
    files.extend(sorted((root / ".opencode").rglob("*.md")))
    files.extend(sorted((root / "changelog.d").glob("*.md")))
    template = root / ".github" / "pull_request_template.md"
    if template.is_file():
        files.append(template)
    files.extend(root / name for name in _ROOT_FILES if (root / name).is_file())
    return files


def _without_fences(text: str) -> str:
    """Remove fenced code blocks so examples are not treated as prose."""
    return re.sub(r"```.*?```", "", text, flags=re.DOTALL)


def _slug(heading: str) -> str:
    """Approximate the anchor GitHub generates for a heading.

    Inline links keep their text, inline code keeps its content, and every
    character outside ``[\\w\\- ]`` is dropped before spaces become hyphens.
    """
    text = _LINK_TEXT_RE.sub(r"\1", heading.strip())
    text = text.replace("`", "").lower()
    text = _SLUG_STRIP_RE.sub("", text)
    return text.replace(" ", "-")


def _anchors(path: Path) -> set[str]:
    """The anchors GitHub generates for every heading in *path*.

    A repeated heading gets the ``-1``, ``-2`` suffix GitHub appends, so a link
    to a later duplicate still resolves.
    """
    seen: dict[str, int] = {}
    anchors: set[str] = set()
    for heading in _HEADING_RE.findall(_without_fences(path.read_text(encoding="utf-8"))):
        slug = _slug(heading)
        count = seen.get(slug, 0)
        anchors.add(slug if count == 0 else f"{slug}-{count}")
        seen[slug] = count + 1
    return anchors


def _check_links(path: Path, root: Path) -> list[str]:
    errors: list[str] = []
    text = _without_fences(path.read_text(encoding="utf-8"))
    for target in _LINK_RE.findall(text):
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        relative, _, fragment = target.partition("#")
        if relative:
            resolved = (path.parent / relative).resolve()
            if not resolved.exists():
                errors.append(f"{path.relative_to(root)}: missing link target {target}")
                continue
        else:
            resolved = path
        if fragment and resolved.suffix == ".md" and resolved.is_file() and fragment not in _anchors(resolved):
            errors.append(f"{path.relative_to(root)}: missing anchor #{fragment} in {target}")
    return errors


def _check_dashes(path: Path, root: Path) -> list[str]:
    errors: list[str] = []
    in_fence = False
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence and any(dash in line for dash in _DASHES):
            errors.append(f"{path.relative_to(root)}:{line_number}: dash punctuation")
    return errors


def _extract_mermaid(path: Path, destination: Path, root: Path) -> int:
    prefix = "-".join(path.relative_to(root).with_suffix("").parts)
    blocks = _MERMAID_RE.findall(path.read_text(encoding="utf-8"))
    for index, block in enumerate(blocks, 1):
        (destination / f"{prefix}-{index}.mmd").write_text(block, encoding="utf-8")
    return len(blocks)


def main(argv: list[str] | None = None) -> int:
    """Run the documentation checks and return a process exit code."""
    parser = argparse.ArgumentParser(description="Check links, anchors, prose punctuation, and Mermaid blocks.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: the checkout containing this script)",
    )
    parser.add_argument(
        "--mermaid-dir",
        type=Path,
        help="extract every Mermaid block into this directory for rendering",
    )
    args = parser.parse_args(argv)

    root = args.root.resolve()
    files = _markdown_files(root)
    errors: list[str] = []
    diagrams = 0
    if args.mermaid_dir is not None:
        args.mermaid_dir.mkdir(parents=True, exist_ok=True)
    for path in files:
        errors.extend(_check_links(path, root))
        errors.extend(_check_dashes(path, root))
        if args.mermaid_dir is not None:
            diagrams += _extract_mermaid(path, args.mermaid_dir, root)

    print(f"checked {len(files)} Markdown files")
    if args.mermaid_dir is not None:
        print(f"extracted {diagrams} Mermaid diagrams to {args.mermaid_dir}")
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("documentation checks OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
