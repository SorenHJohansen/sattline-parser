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
* ``sattline graphics`` — a graphics companion's bindings and scan messages.
* ``sattline decode`` — a compact/coded source as plain text.
* ``sattline diff`` — the findings and structural counts that moved between two
  versions of a unit.
* ``sattline corpus`` — batch triage over a source tree.
* ``sattline rules``: the validation rule registry, with id, name, status, summary.
* ``sattline version`` — tool and JSON schema versions.

Exit codes are the contract: ``0`` clean, ``1`` findings, ``2`` usage/input,
``3`` internal error, ``130`` interrupted. A consumer that closes the output
pipe early (``sattline check ... | head``) stops the report and exits ``2``:
the stream that would carry an explanation is the one that closed. Output is
plain text unless ``--json``, ``--jsonl``, or ``--sarif`` is given, and a
traceback is only printed under ``--debug``. No command edits a
source tree: there is no ``--fix``, no network access and no watch mode. The
``project`` command does write its parser cache unless ``--no-cache`` is given.
"""

from __future__ import annotations

import argparse
import contextlib
import errno
import logging
import os
import sys
import traceback
from collections.abc import Sequence
from typing import NoReturn

from ._errors import CliError
from ._exit import ExitCode
from .cmds import check, corpus, decode, diff, graphics, parse, project, query, rules, version

__all__ = ["build_parser", "main"]

_PROGRAM = "sattline"
_DESCRIPTION = "Parse, validate and inspect SattLine sources (JSON-first)."
_LIBRARY_LOGGER = "sattline_parser"
_DEBUG_LOG_FORMAT = "debug: %(message)s"


class _UsageError(Exception):
    """Raised instead of ``argparse``'s ``SystemExit`` so ``main`` owns the exit code."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
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
    for module in (check, parse, query, project, graphics, decode, diff, corpus, rules, version):
        module.register(subparsers)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code."""
    _make_output_encoding_safe()
    code = _dispatch(argv)
    # A short report fits the buffer, so its EPIPE or ENOSPC can surface only
    # during the interpreter's exit flush. Flush here, where the exit code can
    # still be the documented output-problem code instead of 120.
    try:
        sys.stdout.flush()
    except Exception as exc:
        if _is_output_stream_error(exc):
            _discard_stdout()
            return int(ExitCode.USAGE)
        raise
    return code


def _is_output_stream_error(exc: BaseException) -> bool:
    """Whether *exc* means the output stream could not accept the report.

    POSIX reports a closed pipe as ``BrokenPipeError``, Windows as a generic
    ``OSError`` with ``EINVAL``, and a full device as ``ENOSPC``. All three are
    output problems, which the CLI contract reports as exit 2.
    """
    if isinstance(exc, BrokenPipeError):
        return True
    return isinstance(exc, OSError) and exc.errno in {
        errno.EPIPE,
        errno.EINVAL,
        errno.ENOSPC,
        getattr(errno, "EDQUOT", errno.ENOSPC),
    }


def _make_output_encoding_safe() -> None:
    """Stop a character the stream cannot encode from becoming an internal error.

    The library represents an undefined byte inside a comment as U+FFFD, which
    a cp1252 stream cannot encode. ``backslashreplace`` keeps the report intact:
    for JSON a replaced character is written as ``\\ufffd``, which parses back to
    the same character, and for text it stays readable instead of raising.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            # A caller that embeds the CLI may pass a stream without a codec.
            continue
        with contextlib.suppress(OSError, ValueError):
            reconfigure(errors="backslashreplace")


def _install_parser_log_handler() -> logging.Handler:
    """Send the library's parser-failure log to stderr, for ``--debug`` only.

    Without a handler the package logger falls back to ``logging.lastResort``,
    which writes the same record (and its traceback) whether or not the caller
    asked for it. The CLI owns logging, so it installs a handler under
    ``--debug`` and removes it afterwards.
    """
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_DEBUG_LOG_FORMAT))
    logging.getLogger(_LIBRARY_LOGGER).addHandler(handler)
    return handler


def _dispatch(argv: Sequence[str] | None) -> int:
    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        args = parser.parse_args(arguments)
    except _UsageError as exc:
        print(f"{_PROGRAM}: {exc}", file=sys.stderr)
        print(f"try '{_PROGRAM} --help'", file=sys.stderr)
        return int(ExitCode.USAGE)
    handler = _install_parser_log_handler() if args.debug else None
    try:
        return int(args.handler(args))
    except CliError as exc:
        print(f"{_PROGRAM}: {exc}", file=sys.stderr)
        return int(ExitCode.USAGE)
    except KeyboardInterrupt:
        print(f"{_PROGRAM}: interrupted", file=sys.stderr)
        return int(ExitCode.INTERRUPTED)
    except Exception as exc:  # noqa: BLE001 - the CLI must never leak a traceback by default
        if _is_output_stream_error(exc):
            # The consumer closed the pipe. Point stdout at the null device so
            # the interpreter's exit flush cannot fail a second time and turn a
            # stopped report into exit 120.
            _discard_stdout()
            return int(ExitCode.USAGE)
        if args.debug:
            traceback.print_exc()
        print(f"{_PROGRAM}: internal error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return int(ExitCode.INTERNAL)
    finally:
        if handler is not None:
            logging.getLogger(_LIBRARY_LOGGER).removeHandler(handler)


def _discard_stdout() -> None:
    """Point the process stdout at the null device, ignoring a stream without a descriptor."""
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
    except OSError:  # pragma: no cover - the null device is always available
        return
    try:
        os.dup2(devnull, sys.stdout.fileno())
    except (AttributeError, OSError, ValueError):
        pass
    finally:
        os.close(devnull)
