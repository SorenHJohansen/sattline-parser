"""``sattline version`` — tool and JSON schema versions."""

from __future__ import annotations

import argparse

from sattline_parser import __version__

from .._exit import ExitCode
from .._json import SCHEMA_PREFIX
from ._common import emit_payload

__all__ = ["COMMANDS", "register", "run"]

COMMANDS = ("check", "parse", "query", "project", "graphics", "decode", "diff", "corpus", "version")

SCHEMAS = {
    "version": f"{SCHEMA_PREFIX}.version",
    "check": f"{SCHEMA_PREFIX}.check",
    "parse": f"{SCHEMA_PREFIX}.parse",
    "query": f"{SCHEMA_PREFIX}.query",
    "project": f"{SCHEMA_PREFIX}.project",
    "graphics": f"{SCHEMA_PREFIX}.graphics",
    "decode": f"{SCHEMA_PREFIX}.decode",
    "diff": f"{SCHEMA_PREFIX}.diff",
    "corpus": f"{SCHEMA_PREFIX}.corpus",
}


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser("version", help="print the tool and JSON schema versions")
    parser.add_argument("--json", action="store_true", help="emit a JSON document")
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    if args.json:
        emit_payload(
            {"tool": "sattline", "version": __version__, "commands": list(COMMANDS), "schemas": SCHEMAS},
            args=args,
            schema="version",
        )
    else:
        print(f"sattline {__version__}")
    return int(ExitCode.OK)
