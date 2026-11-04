"""``sattline check`` — decode, parse and validate; the workhorse command."""

from __future__ import annotations

import argparse

from .._exit import ExitCode
from .._findings import Finding
from .._io import read_source
from .._validate import analyse
from ._common import (
    add_fail_on,
    add_finding_filters,
    add_output_flags,
    add_source_flags,
    emit_findings,
    fails_on,
    reject_companion,
    resolve_rule_filters,
    selected_findings,
)

__all__ = ["register", "run"]


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser("check", help="decode, parse and validate sources")
    parser.add_argument("paths", nargs="+", metavar="PATH", help="source files, or '-' for stdin")
    add_source_flags(parser)
    add_output_flags(parser)
    add_finding_filters(parser)
    add_fail_on(parser)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    absolute = args.path_style == "absolute"
    # Reject an unknown or inactive --rule before reading any source.
    resolve_rule_filters(args.rule or ())
    findings: list[Finding] = []
    for target in args.paths:
        reject_companion(target)
        source = read_source(target, name=args.stdin_name)
        findings.extend(analyse(source.name, source.text, absolute=absolute).findings)
    reported = selected_findings(findings, args)
    emit_findings(
        reported,
        args=args,
        schema="check",
        extra={"files": list(args.paths)},
    )
    return int(
        ExitCode.FINDINGS if fails_on(sum(1 for finding in reported if finding.is_error), args.fail_on) else ExitCode.OK
    )
