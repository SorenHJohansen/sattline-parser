"""``sattline decode`` — turn a compact/coded source into plain text."""

from __future__ import annotations

import argparse
import sys

from sattline_parser.preprocessing import PreprocessError, is_compressed, preprocess_source

from .._errors import CliError
from .._exit import ExitCode
from .._io import read_source
from .._json import SCHEMA_PREFIX, dumps
from ._common import add_source_flags, reject_companion

__all__ = ["register", "run"]


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "decode", help="decode a compact/coded source into plain text"
    )
    parser.add_argument("path", metavar="PATH", help="source file, or '-' for stdin")
    add_source_flags(parser)
    report = parser.add_mutually_exclusive_group()
    report.add_argument("--report", action="store_true", help="emit a JSON report instead of the text")
    report.add_argument("--json", action="store_true", help="emit the text inside a JSON document")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    reject_companion(args.path)
    name, text = read_source(args.path, name=args.stdin_name)
    try:
        document = preprocess_source(text)
    except PreprocessError as exc:
        raise CliError(f"{name}: {exc}") from exc
    report = {
        "schema": f"{SCHEMA_PREFIX}.decode",
        "file": name,
        "coded": is_compressed(text) and not document.is_identity(),
        "original_length": len(text),
        "decoded_length": len(document.normalized_text),
    }
    if args.report:
        print(dumps(report))
    elif args.json:
        print(dumps({**report, "decoded": document.normalized_text}))
    else:
        sys.stdout.write(document.normalized_text)
    return int(ExitCode.OK)
