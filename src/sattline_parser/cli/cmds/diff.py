"""``sattline diff`` — what changed between two versions of a unit."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from typing import cast

from .._exit import ExitCode
from .._io import read_source
from .._json import SCHEMA_PREFIX, dumps
from .._validate import Analysis, analyse
from ._common import add_output_flags, add_source_flags, reject_companion

__all__ = ["DiffResult", "FindingDelta", "register", "run"]


@dataclass(frozen=True, slots=True)
class FindingDelta:
    """One rule+message pair whose occurrence count changed."""

    rule: str
    message: str
    count: int

    def to_json(self) -> dict[str, object]:
        return {"rule": self.rule, "message": self.message, "count": self.count}


@dataclass(frozen=True, slots=True)
class DiffResult:
    """Findings and structural counts added/removed between two units."""

    old_file: str
    new_file: str
    old_parsed: bool
    new_parsed: bool
    added: tuple[FindingDelta, ...]
    removed: tuple[FindingDelta, ...]
    #: ``(count name, old value, new value)`` for every summary count that moved.
    counts_changed: tuple[tuple[str, object, object], ...]

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.counts_changed)

    def to_json(self) -> dict[str, object]:
        return {
            "old": {"file": self.old_file, "parsed": self.old_parsed},
            "new": {"file": self.new_file, "parsed": self.new_parsed},
            "findings": {
                "added": [delta.to_json() for delta in self.added],
                "removed": [delta.to_json() for delta in self.removed],
            },
            "counts": {
                "changed": {name: {"old": old, "new": new} for name, old, new in self.counts_changed},
            },
        }


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser("diff", help="compare findings and structure of two units")
    parser.add_argument("old", metavar="OLD", help="the previous source")
    parser.add_argument("new", metavar="NEW", help="the current source")
    add_source_flags(parser)
    add_output_flags(parser)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    reject_companion(args.old)
    reject_companion(args.new)
    old_source = read_source(args.old, name=args.stdin_name)
    new_source = read_source(args.new, name=args.stdin_name)
    old_name, old_text = old_source.name, old_source.text
    new_name, new_text = new_source.name, new_source.text
    result = compare(
        analyse(old_name, old_text, absolute=False),
        analyse(new_name, new_text, absolute=False),
        old_name=old_name,
        new_name=new_name,
    )
    if args.json or args.jsonl:
        print(dumps({"schema": f"{SCHEMA_PREFIX}.diff", **result.to_json()}, compact=bool(args.jsonl)))
    else:
        _print_text(result)
    return int(ExitCode.FINDINGS if result.changed else ExitCode.OK)


def compare(old: Analysis, new: Analysis, *, old_name: str, new_name: str) -> DiffResult:
    """Compare two analyses: findings by rule+message, plus structural count deltas."""
    old_counts = Counter((finding.rule, finding.message) for finding in old.findings)
    new_counts = Counter((finding.rule, finding.message) for finding in new.findings)
    added = tuple(
        FindingDelta(rule=rule, message=message, count=count)
        for (rule, message), count in sorted((new_counts - old_counts).items())
    )
    removed = tuple(
        FindingDelta(rule=rule, message=message, count=count)
        for (rule, message), count in sorted((old_counts - new_counts).items())
    )
    old_map = _counts(old)
    new_map = _counts(new)
    counts_changed = tuple(
        (key, old_map.get(key), new_map.get(key))
        for key in sorted({*old_map, *new_map})
        if old_map.get(key) != new_map.get(key)
    )
    return DiffResult(
        old_file=old_name,
        new_file=new_name,
        old_parsed=old.summary is not None,
        new_parsed=new.summary is not None,
        added=added,
        removed=removed,
        counts_changed=counts_changed,
    )


def _counts(analysis: Analysis) -> dict[str, object]:
    if analysis.summary is None:
        return {}
    counts = analysis.summary.get("counts")
    return cast("dict[str, object]", counts) if isinstance(counts, dict) else {}


def _print_text(result: DiffResult) -> None:
    if not result.changed:
        print("no differences")
        return
    if not result.old_parsed:
        print(f"- {result.old_file}: does not parse")
    if not result.new_parsed:
        print(f"+ {result.new_file}: does not parse")
    for delta in result.added:
        suffix = f" (x{delta.count})" if delta.count > 1 else ""
        print(f"+ {delta.rule}: {delta.message}{suffix}")
    for delta in result.removed:
        suffix = f" (x{delta.count})" if delta.count > 1 else ""
        print(f"- {delta.rule}: {delta.message}{suffix}")
    for name, old_value, new_value in result.counts_changed:
        print(f"~ {name}: {old_value} -> {new_value}")
