"""Flag groups and output helpers shared by the subcommands."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from ...project.formats import ALL_DISTRIBUTION_EXTENSIONS, ALL_GRAPHICS_EXTENSIONS
from ...validation.rules import RuleStatus, UnknownRuleError, require_rule
from .._errors import CliError
from .._findings import Finding
from .._json import SCHEMA_PREFIX, dumps
from .._sarif import sarif_json

__all__ = [
    "FAIL_ON_CHOICES",
    "add_fail_on",
    "add_finding_filters",
    "add_output_flags",
    "add_sarif_flag",
    "add_source_flags",
    "bounded_positive_int",
    "emit_findings",
    "emit_payload",
    "emit_sarif",
    "fail_on_value",
    "fails_on",
    "finding_fields",
    "positive_int",
    "reject_companion",
    "require_companion",
    "require_plain_output",
    "resolve_rule_filters",
    "selected_findings",
]


#: Companion extensions hold graphics records or distribution data, not SattLine source.
#:
#: Each family is checked by its own set, so adding a companion kind never
#: mislabels an existing one.


def reject_companion(target: str, *, stdin_name: str | None = None) -> None:
    """Refuse a companion before it is mis-reported as broken source.

    The name that decides the artifact family is the path itself, or
    ``--stdin-name`` when the input is stdin, so piped companion content is
    refused exactly like a companion path.
    """
    name = stdin_name if target == "-" and stdin_name is not None else target
    suffix = Path(name).suffix.lower()
    if suffix in ALL_DISTRIBUTION_EXTENSIONS:
        raise CliError(f"{name} is a distribution companion ({suffix}); this command reads SattLine source units")
    if suffix in ALL_GRAPHICS_EXTENSIONS:
        raise CliError(f"{name} is a graphics companion ({suffix}); this command reads SattLine source units")


def require_companion(target: str) -> None:
    """Refuse source input for a command that only reads graphics companions."""
    if target == "-":
        return
    suffix = Path(target).suffix.lower()
    if suffix not in ALL_GRAPHICS_EXTENSIONS:
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


def bounded_positive_int(maximum: int) -> Callable[[str], int]:
    """An argparse type for a count in ``1..maximum``.

    A process or thread count is a resource request, so a value far past the
    machine's capacity is a usage error rather than a load that exhausts memory.
    """

    def parse(value: str) -> int:
        number = positive_int(value)
        if number > maximum:
            raise argparse.ArgumentTypeError(f"must be {maximum} or less")
        return number

    return parse


#: Canonical values for ``--fail-on``, shared by every command that reports
#: findings so one spelling does not mean different things per subcommand.
FAIL_ON_CHOICES: tuple[str, ...] = ("none", "error")


def fail_on_value(value: str) -> str:
    """argparse type that accepts only the canonical ``--fail-on`` values."""
    if value not in FAIL_ON_CHOICES:
        raise argparse.ArgumentTypeError(f"expected one of {', '.join(FAIL_ON_CHOICES)}, got {value!r}")
    return value


def add_fail_on(parser: argparse.ArgumentParser) -> None:
    """Register the shared ``--fail-on`` flag."""
    parser.add_argument(
        "--fail-on",
        type=fail_on_value,
        choices=FAIL_ON_CHOICES,
        default="error",
        metavar="WHEN",
        help="which findings make the exit code 1: none or error (default: error)",
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
        help="how to render source paths in findings and document-level file keys (default: as given)",
    )


def add_output_flags(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--json", action="store_true", help="emit one JSON document")
    group.add_argument("--jsonl", action="store_true", help="emit one JSON object per line")


def add_sarif_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--sarif",
        action="store_true",
        help="emit a SARIF 2.1.0 log for code scanning instead of text or JSON",
    )


def require_plain_output(args: argparse.Namespace) -> None:
    """Refuse ``--sarif`` combined with the tool's own JSON output.

    SARIF is a complete document of its own, so mixing the two would leave one
    silently ignored. The combination is a usage error instead.
    """
    if getattr(args, "sarif", False) and (getattr(args, "json", False) or getattr(args, "jsonl", False)):
        raise CliError("--sarif cannot be combined with --json or --jsonl")


def emit_sarif(findings: Sequence[Finding], *, version: str) -> None:
    """Write a SARIF log for *findings* to stdout."""
    print(sarif_json(findings, version=version))


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


def resolve_rule_filters(values: Sequence[str], *, synthetic: frozenset[str]) -> tuple[str, ...]:
    """Resolve ``--rule`` values to canonical finding rule ids.

    Both the ``SL-V###`` id and the enum name are accepted, case-insensitively.
    *synthetic* is the set of non-registry finding ids the calling command can
    actually emit, such as ``PARSE_ERROR``. An unknown value, a rule that can
    never produce a finding, or another command's synthetic id is a usage error,
    so a typo cannot silently pass with an empty report.
    """
    names: list[str] = []
    for value in values:
        candidate = value.upper()
        if candidate in synthetic:
            names.append(candidate)
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


def selected_findings(
    findings: Sequence[Finding], args: argparse.Namespace, *, synthetic: frozenset[str]
) -> list[Finding]:
    """Apply the ``--rule`` filter."""
    selected = list(findings)
    if args.rule:
        wanted = set(resolve_rule_filters(args.rule, synthetic=synthetic))
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
