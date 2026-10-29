"""``sattline query`` — answer one structural question about a unit."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from lark.exceptions import UnexpectedInput

from sattline_parser.api import parse_source_text
from sattline_parser.preprocessing import PreprocessError

from .._ast_walk import QUERY_KINDS, QueryRow, iter_rows
from .._exit import ExitCode
from .._findings import finding_from_parse_error
from .._io import read_source
from .._json import SCHEMA_PREFIX, dumps
from ._common import add_output_flags, add_source_flags, emit_findings, reject_companion

__all__ = ["KINDS", "register", "run"]

#: ``--what`` values, including the ``definitions`` alias for symbols.
KINDS: tuple[str, ...] = ("definitions", *QUERY_KINDS)


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser("query", help="answer one structural question about a unit")
    parser.add_argument("path", metavar="PATH", help="source file, or '-' for stdin")
    add_source_flags(parser)
    add_output_flags(parser)
    parser.add_argument(
        "--what",
        choices=KINDS,
        default="symbols",
        help="what to look for (default: symbols)",
    )
    parser.add_argument("--name", dest="subject", metavar="NAME", help="only rows with this name (case-insensitive)")
    parser.add_argument(
        "--module",
        metavar="PATH",
        help="only rows in this module path, e.g. 'StartMaster/Changelog'",
    )
    parser.add_argument("--limit", type=_positive_int, metavar="N", help="stop after N rows")
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
    name, text = read_source(args.path, name=args.stdin_name)
    absolute = args.path_style == "absolute"
    try:
        picture = parse_source_text(text, log_failures=False)
    except (UnexpectedInput, PreprocessError) as exc:
        finding = finding_from_parse_error(exc, text, file=name, absolute_paths=absolute)
        emit_findings([finding], args=args, schema="query", extra={"file": name})
        return int(ExitCode.FINDINGS)
    rows = _collect(picture, args, name=name)
    _emit(rows, args=args, file=name)
    return int(ExitCode.OK if rows else ExitCode.FINDINGS)


def _collect(picture: object, args: argparse.Namespace, *, name: str) -> list[QueryRow]:
    kinds = QUERY_KINDS if args.what == "definitions" else (args.what,)
    rows: list[QueryRow] = []
    for row in iter_rows(picture, kinds=kinds, name=args.subject, module=args.module):  # pyright: ignore[reportArgumentType]
        rows.append(row)
        if args.limit is not None and len(rows) >= args.limit:
            break
    return rows


def _emit(rows: Sequence[QueryRow], *, args: argparse.Namespace, file: str) -> None:
    if args.json:
        print(dumps({"schema": f"{SCHEMA_PREFIX}.query", "file": file, "rows": [row.to_json() for row in rows]}))
        return
    if args.jsonl:
        for row in rows:
            print(dumps(row.to_json(), compact=True))
        return
    for row in rows:
        location = f"{file}:{row.line}:{row.column}: " if row.line is not None else f"{file}: "
        module = f" [{row.module}]" if row.module else ""
        # A symbol row's detail is its kind (variable, step, module_type, ...), which
        # reads better than repeating "symbols".
        label = row.detail if row.kind == "symbols" and row.detail else row.kind
        detail = f" ({row.detail})" if row.detail and row.kind != "symbols" else ""
        print(f"{location}{label} {row.name}{detail}{module}")
