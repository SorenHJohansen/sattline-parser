"""Flag groups and output helpers shared by the subcommands."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from ...project.formats import ALL_GRAPHICS_EXTENSIONS
from ...validation.rules import RuleStatus, UnknownRuleError, require_rule
from .._errors import CliError
from .._findings import CLI_RULE_IDS, Finding
from .._json import SCHEMA_PREFIX, dumps

__all__ = [
    "FAIL_ON_CHOICES",
    "add_fail_on",
    "add_finding_filters",
    "add_output_flags",
    "add_source_flags",
    "emit_findings",
    "emit_payload",
    "fail_on_value",
    "fails_on",
    "finding_fields",
    "positive_int",
    "reject_companion",
    "require_companion",
    "resolve_rule_filters",
    "selected_findings",
]


#: Companion extensions hold graphics records, not SattLine source.
_COMPANION_SUFFIXES = ALL_GRAPHICS_EXTENSIONS


def reject_companion(target: str) -> None:
    """Refuse a graphics companion before it is mis-reported as broken source."""
    suffix = Path(target).suffix.lower()
    if suffix in _COMPANION_SUFFIXES:
        raise CliError(f"{target} is a graphics companion ({suffix}); check and parse read SattLine source units")


def require_companion(target: str) -> None:
    """Refuse source input for a command that only reads graphics companions."""
    if target == "-":
        return
    suffix = Path(target).suffix.lower()
    if suffix not in _COMPANION_SUFFIXES:
        raise CliError(f"{target} is not a graphics companion (.g/.y)")


def positive_int(value: str) -> int:
    """argparse type for a count that must be at least one."""
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return number


#: Canonical values for ``--fail-on``, shared by every command that reports
#: findings so one spelling does not mean different things per subcommand.
FAIL_ON_CHOICES: tuple[str, ...] = ("none", "error")

#: Spellings earlier releases accepted, mapped onto the canonical value.
_FAIL_ON_ALIASES: dict[str, str] = {"never": "none"}


def fail_on_value(value: str) -> str:
    """argparse type that normalises the historical ``--fail-on`` spellings."""
    normalized = _FAIL_ON_ALIASES.get(value, value)
    if normalized not in FAIL_ON_CHOICES:
        allowed = ", ".join((*FAIL_ON_CHOICES, *_FAIL_ON_ALIASES))
        raise argparse.ArgumentTypeError(f"expected one of {allowed}, got {value!r}")
    return normalized


def add_fail_on(parser: argparse.ArgumentParser) -> None:
    """Register the shared ``--fail-on`` flag."""
    parser.add_argument(
        "--fail-on",
        type=fail_on_value,
        choices=FAIL_ON_CHOICES,
        default="error",
        metavar="WHEN",
        help=("which findings make the exit code 1: none or error (default: error; 'never' is accepted as an alias)"),
    )


def fails_on(errors: int, fail_on: str) -> bool:
    """Whether a run with *errors* findings fails under *fail_on*."""
    if fail_on == "none":
        return False
    return errors > 0


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
        "--rule",
        action="append",
        metavar="RULE",
        help="only report this rule (SL-V### id or enum name, repeatable; see 'sattline rules')",
    )
    parser.add_argument(
        "--max-findings",
        type=int,
        metavar="N",
        help="stop after printing N findings (the exit code still reflects them all)",
    )


def resolve_rule_filters(values: Sequence[str]) -> tuple[str, ...]:
    """Resolve ``--rule`` values to canonical finding rule ids.

    Both the ``SL-V###`` id and the enum name are accepted, case-insensitively.
    Synthetic finding ids such as ``PARSE_ERROR`` are accepted too, because they
    appear in output but not in the validation registry. An unknown value or a
    rule that can never produce a finding is a usage error, so a typo cannot
    silently pass with an empty report.
    """
    names: list[str] = []
    for value in values:
        synthetic = value.upper()
        if synthetic in CLI_RULE_IDS:
            names.append(synthetic)
            continue
        try:
            rule = require_rule(value)
        except UnknownRuleError as exc:
            raise CliError(f"{exc} (run 'sattline rules' to list rule ids)") from exc
        if rule.status is not RuleStatus.ACTIVE:
            detail = rule.details or rule.summary
            raise CliError(f"rule {rule.id} ({rule.name}) is {rule.status.value}: {detail}")
        names.append(rule.name)
    return tuple(names)


def selected_findings(findings: Sequence[Finding], args: argparse.Namespace) -> list[Finding]:
    """Apply the ``--rule`` filter."""
    selected = list(findings)
    if args.rule:
        wanted = set(resolve_rule_filters(args.rule))
        selected = [finding for finding in selected if finding.rule in wanted]
    return selected


def emit_findings(
    findings: Sequence[Finding],
    *,
    args: argparse.Namespace,
    schema: str,
    extra: Mapping[str, object] | None = None,
    include_warnings: bool = False,
) -> None:
    """Write findings as text, one JSON document, or JSON lines."""
    limited = _limited(findings, args)
    if args.json:
        payload: dict[str, object] = {
            "schema": f"{SCHEMA_PREFIX}.{schema}",
            **finding_fields(findings, args=args, include_warnings=include_warnings),
        }
        payload.update(extra or {})
        print(dumps(payload))
        return
    if args.jsonl:
        for finding in limited:
            print(dumps(finding.to_json(), compact=True))
        print(
            dumps(
                {
                    "schema": f"{SCHEMA_PREFIX}.{schema}",
                    "summary": True,
                    "counts": _counts(findings, include_warnings=include_warnings),
                },
                compact=True,
            )
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


def finding_fields(
    findings: Sequence[Finding], *, args: argparse.Namespace, include_warnings: bool = False
) -> dict[str, object]:
    """The JSON fields that report *findings* inside a larger document."""
    limited = _limited(findings, args)
    return {
        "ok": not any(finding.is_error for finding in findings),
        "counts": _counts(findings, include_warnings=include_warnings),
        "findings": [finding.to_json() for finding in limited],
    }


def _limited(findings: Sequence[Finding], args: argparse.Namespace) -> list[Finding]:
    limit = getattr(args, "max_findings", None)
    if limit is None or limit < 0 or limit >= len(findings):
        return list(findings)
    withheld = len(findings) - limit
    print(f"note: {withheld} more finding(s) not shown", file=sys.stderr)
    return list(findings[:limit])


def _counts(findings: Sequence[Finding], *, include_warnings: bool = False) -> dict[str, int]:
    """Count findings, adding the warning bucket when the caller can emit one."""
    counts = {"error": sum(1 for finding in findings if finding.severity == "error")}
    if include_warnings:
        counts["warning"] = sum(1 for finding in findings if finding.severity == "warning")
    return counts


def _print_finding_text(finding: Finding) -> None:
    print(f"{finding.location()}{finding.message}")
    if finding.hint is not None:
        print(f"    help: {finding.hint}")
    if finding.source_line is not None:
        print(f"    {finding.source_line.strip()}")
        if finding.column is not None:
            offset = max(0, finding.column - 1 - (len(finding.source_line) - len(finding.source_line.lstrip())))
            print(f"    {' ' * offset}^")
