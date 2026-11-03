"""Regenerate the validation rule table in ``docs/validation.md``.

The rule registry in ``validation/rules.py`` is the source of truth. This
script writes its Markdown rendering between the markers in the document, so a
new code cannot be documented in prose only.

Usage::

    python scripts/gen_rule_table.py
    python scripts/gen_rule_table.py --check
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sattline_parser.validation.rules import render_markdown_table

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCUMENT = REPO_ROOT / "docs" / "validation.md"
START = "<!-- RULE-TABLE:START -->"
END = "<!-- RULE-TABLE:END -->"


def replace_table(text: str, table: str) -> str:
    """Return ``text`` with the marked block replaced by ``table``."""
    before, separator, rest = text.partition(START)
    if not separator:
        raise ValueError(f"{DOCUMENT}: missing {START}")
    _old, separator, after = rest.partition(END)
    if not separator:
        raise ValueError(f"{DOCUMENT}: missing {END}")
    return f"{before}{START}\n{table}\n{END}{after}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate the rule table in docs/validation.md.")
    parser.add_argument("--check", action="store_true", help="report a stale table instead of writing it")
    args = parser.parse_args(argv)

    current = DOCUMENT.read_text(encoding="utf-8")
    updated = replace_table(current, render_markdown_table())
    if args.check:
        if current != updated:
            print("docs/validation.md: rule table is stale; run scripts/gen_rule_table.py", file=sys.stderr)
            return 1
        print("docs/validation.md: rule table is current")
        return 0
    if current != updated:
        DOCUMENT.write_text(updated, encoding="utf-8")
        print("docs/validation.md: rule table regenerated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
