"""``sattline graphics`` — inspect a graphics companion (.g / .y)."""

from __future__ import annotations

import argparse
from pathlib import Path

from sattline_parser.project import GraphicsModel, parse_graphics_text

from .._errors import CliError
from .._exit import ExitCode
from .._findings import Finding
from .._io import read_source
from .._json import SCHEMA_PREFIX, dumps
from ._common import add_output_flags, add_source_flags, emit_findings

__all__ = ["register", "run"]


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "graphics", help="read a graphics companion: bindings and scan messages"
    )
    parser.add_argument("path", metavar="PATH", help="companion file (.g/.y), or '-' for stdin")
    add_output_flags(parser)
    add_source_flags(parser)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    model, name = _load_model(args)
    findings = _findings(model, name=name)
    _emit_document(model, args=args, name=name)
    if findings:
        emit_findings(findings, args=args, schema="graphics", extra={"file": name})
    return int(ExitCode.FINDINGS if any(finding.is_error for finding in findings) else ExitCode.OK)


def _load_model(args: argparse.Namespace) -> tuple[GraphicsModel, str]:
    if args.path != "-" and Path(args.path).suffix.lower() not in {".g", ".y"}:
        raise CliError(f"{args.path} is not a graphics companion (.g/.y)")
    source = read_source(args.path, name=args.stdin_name or "<stdin>")
    return parse_graphics_text(source.text), source.name


def _findings(model: GraphicsModel, *, name: str) -> list[Finding]:
    return [
        Finding(
            severity=message.severity,
            message=message.message,
            rule="GRAPHICS_SCAN",
            file=name,
            line=message.line,
            column=message.column,
        )
        for message in model.messages
    ]


def _binding_rows(model: GraphicsModel) -> list[dict[str, object]]:
    return [
        {
            "kind": binding.kind,
            "text": binding.raw_text,
            "line": binding.span.line if binding.span is not None else None,
            "column": binding.span.column if binding.span is not None else None,
        }
        for binding in model.bindings
    ]


def _message_rows(model: GraphicsModel) -> list[dict[str, object]]:
    return [
        {
            "severity": message.severity,
            "message": message.message,
            "line": message.line,
            "column": message.column,
        }
        for message in model.messages
    ]


def _emit_document(model: GraphicsModel, *, args: argparse.Namespace, name: str) -> None:
    rows = _binding_rows(model)
    messages = _message_rows(model)
    if args.json or args.jsonl:
        payload = {
            "schema": f"{SCHEMA_PREFIX}.graphics",
            "file": name,
            "bindings": rows,
            "messages": messages,
        }
        print(dumps(payload, compact=bool(args.jsonl)))
        return
    print(f"bindings: {len(rows)}")
    for row in rows:
        print(f"  {row['line']}:{row['column']} [{row['kind']}] {row['text']}")
