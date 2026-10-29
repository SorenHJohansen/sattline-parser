"""The ``sattline`` command line: a JSON-first wrapper over the parser library.

The CLI adds no semantics. Every command maps onto a documented library call
(``parse_and_validate``, ``parse_source_text``) and emits one shape of finding,
so an agent needs neither Python glue nor a lookup table:

* ``sattline check`` — decode, parse and validate; findings are sentences with a
  location and an optional ``help:`` line.
* ``sattline parse`` — the structure of one unit (summary, or the AST as JSON).
* ``sattline query`` — one structural question (symbols, references, writers,
  callers, graph/interact objects, sequences).
* ``sattline project`` — load a tree: programs, artifacts and dependency edges.
* ``sattline graphics`` — a graphics companion's records, paths and correlation.
* ``sattline decode`` — a compact/coded source as plain text.
* ``sattline diff`` — the findings and structural counts that moved between two
  versions of a unit.
* ``sattline corpus`` — batch triage over a source tree.
* ``sattline version`` — tool and JSON schema versions.

Exit codes are the contract: ``0`` clean, ``1`` findings, ``2`` usage/input,
``3`` internal error. Output is plain text unless ``--json``/``--jsonl`` is
given, and a traceback is only printed under ``--debug``. Every command is
read-only: there is no ``--fix``, no network access and no watch mode.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from collections.abc import Sequence
from typing import NoReturn

from ._errors import CliError
from ._exit import ExitCode
from .cmds import check, corpus, decode, diff, graphics, parse, project, query, version

__all__ = ["build_parser", "main"]

_PROGRAM = "sattline"
_DESCRIPTION = "Parse, validate and inspect SattLine sources (JSON-first)."


class _UsageError(Exception):
    """Raised instead of ``argparse``'s ``SystemExit`` so ``main`` owns the exit code."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:  # pragma: no cover - argparse plumbing
        raise _UsageError(message)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser (also the ``--help`` surface)."""
    parser = _Parser(prog=_PROGRAM, description=_DESCRIPTION)
    parser.add_argument(
        "--debug",
        action="store_true",
        help="print a traceback for internal errors instead of a one-line message",
    )
    subparsers = parser.add_subparsers(dest="command", metavar="<command>", required=True)
    for module in (check, parse, query, project, graphics, decode, diff, corpus, version):
        module.register(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        args = parser.parse_args(arguments)
    except _UsageError as exc:
        print(f"{_PROGRAM}: {exc}", file=sys.stderr)
        print(f"try '{_PROGRAM} --help'", file=sys.stderr)
        return int(ExitCode.USAGE)
    try:
        return int(args.handler(args))
    except CliError as exc:
        print(f"{_PROGRAM}: {exc}", file=sys.stderr)
        return int(ExitCode.USAGE)
    except KeyboardInterrupt:  # pragma: no cover - interactive only
        print(f"{_PROGRAM}: interrupted", file=sys.stderr)
        return int(ExitCode.USAGE)
    except Exception as exc:  # noqa: BLE001 - the CLI must never leak a traceback by default
        if args.debug:
            traceback.print_exc()
        print(f"{_PROGRAM}: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return int(ExitCode.INTERNAL)
