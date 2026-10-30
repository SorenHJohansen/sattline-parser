"""Flag groups and output helpers shared by the subcommands."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from .._errors import CliError
from .._findings import Finding
from .._json import SCHEMA_PREFIX, dumps

__all__ = [
    "add_finding_filters",
    "add_output_flags",
    "add_source_flags",
    "emit_findings",
    "emit_payload",
    "reject_companion",
    "selected_findings",
]


#: Companion extensions hold graphics records, not SattLine source.
_COMPANION_SUFFIXES = frozenset({".g", ".y"})


def reject_companion(target: str) -> None:
    """Refuse a graphics companion before it is mis-reported as broken source."""
    suffix = Path(target).suffix.lower()
    if suffix in _COMPANION_SUFFIXES:
        raise CliError(f"{target} is a graphics companion ({suffix}); check and parse read SattLine source units")


def add_source_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--stdin-name",
        dest="stdin_name",
        metavar="PATH",
        help="display name for stdin input ('-')",
    )
    # ``dest`` is not ``paths``: ``check`` already uses that name for its
    # positional file list.
    parser.add_argument(
        "--paths",
        dest="path_style",
        choices=("given", "absolute"),
        default="given",
        help="how to render source paths in findings (default: as given)",
    )


def add_output_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", action="store_true", help="emit one JSON document")
    group.add_argument("--jsonl", action="store_true", help="emit one JSON object per line")


def add_finding_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--severity",
        choices=("all", "error", "warning"),
        default="all",
        help="only report findings of this severity (default: all)",
    )
    parser.add_argument(
        "--rule",
        action="append",
        metavar="RULE",
        help="only report this rule id (repeatable; machine ids from --json output)",
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        metavar="N",
        help="stop after printing N findings (the exit code still reflects them all)",
    )


def selected_findings(findings: Sequence[Finding], args: argparse.Namespace) -> list[Finding]:
    """Apply ``--severity`` / ``--rule`` filters."""
    selected = list(findings)
    if args.severity != "all":
        selected = [finding for finding in selected if finding.severity == args.severity]
    if args.rule:
        wanted = set(args.rule)
        selected = [finding for finding in selected if finding.rule in wanted]
    return selected


def emit_findings(
    findings: Sequence[Finding],
    *,
    args: argparse.Namespace,
    schema: str,
    extra: Mapping[str, object] | None = None,
) -> None:
    """Write findings as text, one JSON document, or JSON lines."""
    limited = _limited(findings, args)
    if args.json:
        payload: dict[str, object] = {
            "schema": f"{SCHEMA_PREFIX}.{schema}",
            "ok": not any(finding.is_error for finding in findings),
            "counts": _counts(findings),
            "findings": [finding.to_json() for finding in limited],
        }
        payload.update(extra or {})
        print(dumps(payload))
        return
    if args.jsonl:
        for finding in limited:
            print(dumps(finding.to_json(), compact=True))
        print(
            dumps({"schema": f"{SCHEMA_PREFIX}.{schema}", "summary": True, "counts": _counts(findings)}, compact=True)
        )
        return
    for finding in limited:
        _print_finding_text(finding)


def emit_payload(
    payload: Mapping[str, object], *, args: argparse.Namespace, schema: str, compact: bool = False
) -> None:
    """Write a JSON document unless the caller asked for text (handled before this)."""
    document = {"schema": f"{SCHEMA_PREFIX}.{schema}", **payload}
    print(dumps(document, compact=compact or bool(getattr(args, "jsonl", False))))


def _limited(findings: Sequence[Finding], args: argparse.Namespace) -> list[Finding]:
    limit = getattr(args, "max_findings", None)
    if limit is None or limit < 0 or limit >= len(findings):
        return list(findings)
    withheld = len(findings) - limit
    print(f"note: {withheld} more finding(s) not shown", file=sys.stderr)
    return list(findings[:limit])


def _counts(findings: Sequence[Finding]) -> dict[str, int]:
    return {
        "error": sum(1 for finding in findings if finding.severity == "error"),
        "warning": sum(1 for finding in findings if finding.severity == "warning"),
    }


def _print_finding_text(finding: Finding) -> None:
    print(f"{finding.location()}{finding.message}")
    if finding.hint is not None:
        print(f"    help: {finding.hint}")
    if finding.source_line is not None:
        print(f"    {finding.source_line.strip()}")
        if finding.column is not None:
            offset = max(0, finding.column - 1 - (len(finding.source_line) - len(finding.source_line.lstrip())))
            print(f"    {' ' * offset}^")
