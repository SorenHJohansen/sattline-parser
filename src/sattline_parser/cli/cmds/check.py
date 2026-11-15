"""``sattline check`` — decode, parse and validate; the workhorse command."""

from __future__ import annotations

import argparse

from sattline_parser.__version__ import __version__

from .._exit import ExitCode
from .._findings import CHECK_RULE_IDS, Finding
from .._io import read_source
from .._validate import analyse
from ._common import (
    add_fail_on,
    add_finding_filters,
    add_output_flags,
    add_sarif_flag,
    add_source_flags,
    emit_findings,
    emit_sarif,
    fails_on,
    reject_companion,
    require_plain_output,
    resolve_rule_filters,
    selected_findings,
)

__all__ = ["register", "run"]


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser("check", help="decode, parse and validate sources")
    parser.add_argument("paths", nargs="+", metavar="PATH", help="source files, or '-' for stdin")
    add_source_flags(parser)
    add_output_flags(parser)
    add_sarif_flag(parser)
    add_finding_filters(parser)
    add_fail_on(parser)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    require_plain_output(args)
    absolute = args.path_style == "absolute"
    # Reject an unknown or inactive --rule before reading any source.
    resolve_rule_filters(args.rule or (), synthetic=CHECK_RULE_IDS)
    findings: list[Finding] = []
    for target in args.paths:
        reject_companion(target, stdin_name=args.stdin_name)
        source = read_source(target, name=args.stdin_name)
        findings.extend(analyse(source.name, source.text, absolute=absolute).findings)
    reported = selected_findings(findings, args, synthetic=CHECK_RULE_IDS)
    if args.sarif:
        emit_sarif(reported, version=__version__)
    else:
        emit_findings(
            reported,
            args=args,
            schema="check",
            extra={"files": list(args.paths)},
        )
    return int(
        ExitCode.FINDINGS if fails_on(sum(1 for finding in reported if finding.is_error), args.fail_on) else ExitCode.OK
    )
