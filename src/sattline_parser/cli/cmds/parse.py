"""``sattline parse`` — the structure of one unit, without validation noise."""

from __future__ import annotations

import argparse
from typing import cast

from lark.exceptions import UnexpectedInput

from sattline_parser.api import parse_source_text
from sattline_parser.preprocessing import PreprocessError

from .._exit import ExitCode
from .._findings import finding_from_parse_error
from .._io import read_source
from .._json import to_jsonable
from .._validate import summarise
from ._common import add_output_flags, add_source_flags, emit_findings, emit_payload, reject_companion

__all__ = ["DEFAULT_DEPTH", "register", "run"]

DEFAULT_DEPTH = 5


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser("parse", help="show the structure of one unit")
    parser.add_argument("path", metavar="PATH", help="source file, or '-' for stdin")
    add_source_flags(parser)
    add_output_flags(parser)
    parser.add_argument("--tree", action="store_true", help="emit the AST as JSON instead of a summary")
    parser.add_argument(
        "--depth",
        type=_positive_int,
        default=DEFAULT_DEPTH,
        metavar="N",
        help=f"how deep to serialise with --tree (default: {DEFAULT_DEPTH})",
    )
    parser.add_argument("--compact", action="store_true", help="emit JSON on one line")
    parser.set_defaults(handler=run)


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"expected an integer, got {value!r}") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or greater")
    return number


def run(args: argparse.Namespace) -> int:
    reject_companion(args.path)
    source = read_source(args.path, name=args.stdin_name)
    name, text = source.name, source.text
    absolute = args.path_style == "absolute"
    try:
        picture = parse_source_text(text, log_failures=False)
    except (UnexpectedInput, PreprocessError) as exc:
        finding = finding_from_parse_error(exc, text, file=name, absolute_paths=absolute)
        emit_findings([finding], args=args, schema="parse", extra={"file": name})
        return int(ExitCode.FINDINGS)
    if args.tree:
        emit_payload(
            {"file": name, "tree": to_jsonable(picture, depth=args.depth)},
            args=args,
            schema="parse",
            compact=args.compact,
        )
        return int(ExitCode.OK)
    summary = summarise(name, text, picture, coded=source.coded)
    if args.json or args.jsonl:
        emit_payload(summary, args=args, schema="parse")
        return int(ExitCode.OK)
    for label, value in summary.items():
        if isinstance(value, dict):
            counts = cast("dict[str, object]", value)
            print(f"{label}:")
            for key, item in counts.items():
                print(f"  {key}: {item}")
        else:
            print(f"{label}: {value}")
    return int(ExitCode.OK)
