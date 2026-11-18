"""``sattline graphics`` — inspect a graphics companion (.g / .y)."""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from sattline_parser.project import GraphicsModel, parse_graphics_text

from .._exit import ExitCode
from .._findings import GRAPHICS_SCAN_RULE, Finding
from .._io import display_path, read_source
from .._json import SCHEMA_PREFIX, dumps
from ._common import add_output_flags, add_source_flags, emit_findings, finding_fields, require_companion

__all__ = ["register", "run"]

#: Leading words of the expression parser's exception text, which the graphics
#: scanner appends to its message. A finding carries the source position and the
#: raw expression already, so the dump behind these words is not repeated.
_PARSER_DETAIL_PREFIXES: tuple[str, ...] = (
    "Unexpected",
    "No terminal",
    "Expected",
    "Parse",
    "VisitError",
    "Error",
    "Token",
)


def _normalize_scan_message(message: str) -> str:
    """Reduce a scan message to one sentence without the parser's token dump."""
    line = next((part.strip() for part in message.splitlines() if part.strip()), "")
    head, separator, detail = line.rpartition(": ")
    if separator and detail.startswith(_PARSER_DETAIL_PREFIXES):
        line = head
    return line


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
    file = display_path(name, absolute=args.path_style == "absolute")
    findings = _findings(model, name=file)
    _emit_document(model, args=args, name=file, findings=findings)
    return int(ExitCode.FINDINGS if findings else ExitCode.OK)


def _load_model(args: argparse.Namespace) -> tuple[GraphicsModel, str]:
    require_companion(args.path, stdin_name=args.stdin_name)
    source = read_source(args.path, name=args.stdin_name)
    return parse_graphics_text(source.text), source.name


def _findings(model: GraphicsModel, *, name: str) -> list[Finding]:
    return [
        Finding(
            severity=message.severity,
            message=_normalize_scan_message(message.message),
            rule=GRAPHICS_SCAN_RULE,
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
            "message": _normalize_scan_message(message.message),
            "line": message.line,
            "column": message.column,
        }
        for message in model.messages
    ]


def _emit_document(
    model: GraphicsModel,
    *,
    args: argparse.Namespace,
    name: str,
    findings: Sequence[Finding],
) -> None:
    """Write the model and its findings as exactly one document.

    ``--json``/``--jsonl`` must stay parseable: findings ride inside the same
    object as the bindings instead of being printed as a second document.
    """
    rows = _binding_rows(model)
    messages = _message_rows(model)
    if args.json or args.jsonl:
        payload = {
            "schema": f"{SCHEMA_PREFIX}.graphics",
            "file": name,
            "bindings": rows,
            "messages": messages,
            **finding_fields(findings, args=args, include_warnings=True),
        }
        print(dumps(payload, compact=bool(args.jsonl)))
        return
    print(f"bindings: {len(rows)}")
    for row in rows:
        print(f"  {row['line']}:{row['column']} [{row['kind']}] {row['text']}")
    emit_findings(findings, args=args, schema="graphics", extra={"file": name})
