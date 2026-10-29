"""``sattline graphics`` — inspect a graphics companion (.g / .y) and correlate it."""

from __future__ import annotations

import argparse
from pathlib import Path

from lark.exceptions import UnexpectedInput

from sattline_parser.api import parse_source_text
from sattline_parser.preprocessing import PreprocessError
from sattline_parser.project import GraphicsModel, GraphicsPictureDisplayRecord, parse_graphics_text
from sattline_parser.project.graphics_parsing import correlate_composites

from .._errors import CliError
from .._exit import ExitCode
from .._findings import Finding, finding_from_parse_error
from .._io import read_source
from .._json import SCHEMA_PREFIX, dumps
from ._common import add_output_flags, add_source_flags, emit_findings

__all__ = ["register", "run"]


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    parser: argparse.ArgumentParser = subparsers.add_parser(
        "graphics", help="read a graphics companion: records, paths, correlation"
    )
    parser.add_argument("path", metavar="PATH", help="companion file (.g/.y), or '-' for stdin")
    add_output_flags(parser)
    parser.add_argument("--source", metavar="PATH", help="source unit to correlate the records with")
    parser.add_argument("--correlate", action="store_true", help="pair markers with records (needs --source)")
    parser.add_argument("--asset-paths", action="store_true", help="only print the picture-display paths")
    add_source_flags(parser)
    parser.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    if args.correlate and args.source is None:
        raise CliError("--correlate needs --source so markers can be paired")
    model, name = _load_model(args)
    pairs, correlation_findings = _correlate(args, model)
    findings = [*_findings(model, name=name), *correlation_findings]
    if args.asset_paths:
        _emit_paths(model, args=args, name=name)
    else:
        _emit_document(model, pairs, args=args, name=name)
    if findings:
        emit_findings(findings, args=args, schema="graphics", extra={"file": name})
    return int(ExitCode.FINDINGS if any(finding.is_error for finding in findings) else ExitCode.OK)


def _load_model(args: argparse.Namespace) -> tuple[GraphicsModel, str]:
    if args.path != "-" and Path(args.path).suffix.lower() not in {".g", ".y"}:
        raise CliError(f"{args.path} is not a graphics companion (.g/.y)")
    name, text = read_source(args.path, name=args.stdin_name or "<stdin>")
    return parse_graphics_text(text), name


def _correlate(args: argparse.Namespace, model: GraphicsModel) -> tuple[list[dict[str, object]], list[Finding]]:
    if not args.correlate or args.source is None:
        return [], []
    source = Path(args.source)
    try:
        text = source.read_bytes().decode("cp1252")
    except OSError as exc:
        raise CliError(f"cannot read {source}: {exc.strerror or exc}") from exc
    try:
        picture = parse_source_text(text, log_failures=False)
    except (UnexpectedInput, PreprocessError) as exc:
        return [], [finding_from_parse_error(exc, text, file=str(source), absolute_paths=False)]
    pairs, messages = correlate_composites(picture, model)
    rows: list[dict[str, object]] = [
        {
            "marker_ordinal": pair.marker_ordinal,
            "marker_line": pair.marker_span.line if pair.marker_span is not None else None,
            "marker_column": pair.marker_span.column if pair.marker_span is not None else None,
            "record_index": pair.record.record_index,
            "family": pair.record.family_code,
            "record_start_line": pair.record.record_start_line,
        }
        for pair in pairs
    ]
    findings = [
        Finding(
            severity=message.severity,
            message=message.message,
            rule="GRAPHICS_CORRELATION",
            file=str(source),
            line=message.line,
            column=message.column,
        )
        for message in messages
    ]
    return rows, findings


def _findings(model: GraphicsModel, *, name: str) -> list[Finding]:
    return [
        Finding(
            severity=message.severity,
            message=message.message,
            rule="GRAPHICS_RECORD",
            file=name,
            line=message.line,
            column=message.column,
        )
        for message in model.messages
    ]


def _path_rows(model: GraphicsModel) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in model.picture_display_records:
        for row in record.path_rows:
            rows.append(
                {
                    "record_index": record.record_index,
                    "kind": row.kind,
                    "text": row.raw_text,
                    "line": row.span.line,
                    "column": row.span.column,
                    "is_default": record.default_path_row is row,
                }
            )
    return rows


def _record_rows(model: GraphicsModel) -> list[dict[str, object]]:
    return [
        {
            "index": record.record_index,
            "family": record.family_code,
            "start_line": record.record_start_line,
            "end_line": record.record_end_line,
        }
        for record in model.composite_records
    ]


def _display_rows(model: GraphicsModel) -> list[dict[str, object]]:
    return [_display_row(record) for record in model.picture_display_records]


def _display_row(record: GraphicsPictureDisplayRecord) -> dict[str, object]:
    return {
        "index": record.record_index,
        "subtype": record.subtype,
        "start_line": record.record_start_line,
        "end_line": record.record_end_line,
        "default": record.default_path_row.raw_text if record.default_path_row is not None else None,
    }


def _emit_document(
    model: GraphicsModel, pairs: list[dict[str, object]], *, args: argparse.Namespace, name: str
) -> None:
    records = _record_rows(model)
    displays = _display_rows(model)
    paths = _path_rows(model)
    payload = {
        "schema": f"{SCHEMA_PREFIX}.graphics",
        "file": name,
        "records": records,
        "picture_displays": displays,
        "paths": paths,
        "pairs": pairs,
    }
    if args.json or args.jsonl:
        print(dumps(payload, compact=bool(args.jsonl)))
        return
    print(f"records: {len(records)}")
    for record in records:
        print(f"  #{record['index']} family {record['family']} lines {record['start_line']}-{record['end_line']}")
    print(f"picture displays: {len(displays)}")
    for row in paths:
        suffix = " (default)" if row["is_default"] else ""
        print(f"  #{row['record_index']} [{row['kind']}] {row['text']}{suffix}")
    for pair in pairs:
        print(
            f"  marker #{pair['marker_ordinal']} at line {pair['marker_line']} "
            f"-> record #{pair['record_index']} (family {pair['family']})"
        )


def _emit_paths(model: GraphicsModel, *, args: argparse.Namespace, name: str) -> None:
    rows = _path_rows(model)
    if args.json or args.jsonl:
        print(dumps({"schema": f"{SCHEMA_PREFIX}.graphics", "file": name, "paths": rows}, compact=bool(args.jsonl)))
        return
    for row in rows:
        print(row["text"])
