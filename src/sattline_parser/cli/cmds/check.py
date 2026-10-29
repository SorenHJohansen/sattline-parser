"""``sattline check`` — decode, parse and validate; the workhorse command."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .._exit import ExitCode
from .._findings import Finding
from .._io import read_source
from .._validate import analyse
from ._common import (
    add_finding_filters,
    add_output_flags,
    add_source_flags,
    emit_findings,
    reject_companion,
    selected_findings,
)

__all__ = ["register", "run"]


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser("check", help="decode, parse and validate sources")
    parser.add_argument("paths", nargs="+", metavar="PATH", help="source files, or '-' for stdin")
    add_source_flags(parser)
    add_output_flags(parser)
    add_finding_filters(parser)
    parser.add_argument(
        "--fail-on",
        choices=("error", "any", "never"),
        default="error",
        help="which reported findings make the exit code 1 (default: error)",
    )
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    absolute = args.path_style == "absolute"
    findings: list[Finding] = []
    for target in args.paths:
        reject_companion(target)
        name, text = read_source(target, name=args.stdin_name)
        findings.extend(analyse(name, text, absolute=absolute).findings)
    reported = selected_findings(findings, args)
    emit_findings(
        reported,
        args=args,
        schema="check",
        extra={"files": list(args.paths)},
    )
    return int(_exit_code(reported, fail_on=args.fail_on))


def _exit_code(findings: Sequence[Finding], *, fail_on: str) -> ExitCode:
    if fail_on == "never":
        return ExitCode.OK
    if fail_on == "any":
        return ExitCode.FINDINGS if findings else ExitCode.OK
    return ExitCode.FINDINGS if any(finding.is_error for finding in findings) else ExitCode.OK
