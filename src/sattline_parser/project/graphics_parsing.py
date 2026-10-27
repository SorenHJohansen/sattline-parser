"""Graphics companion parsing and companion-path resolution (plan §3.5, Phase 4).

Extracted from SattLint's ``graphics/validation.py`` into the parser: the
companion scanner that reads ``.g`` / ``.y`` files into a ``GraphicsModel``
(bindings, messages, composite records, picture-display records). Only the pure
parse moves here; correlation (``correlate_composites``) and asset-path warnings
stay in the consumer.

Record boundaries come from the per-family readers in
``sattline_parser.project.graphics_records`` (the recovered native grammar), not
from blank lines: see ``docs/graphics_parity.md``. Bindings are additionally
scanned line by line, because the consumer wants every binding in the file and
not just the ones a record reader consumes.
"""

from __future__ import annotations

from pathlib import Path

from sattline_parser.api import read_text_cp1252
from sattline_parser.models.ast_model import GraphicsBinding, SourceSpan

from .formats import graphics_ext_candidates
from .graphics_bindings import _parse_graphics_binding_line
from .graphics_records import GraphicsRecord, read_companion_records
from .models import (
    GraphicsCompositeBinding,
    GraphicsCompositeRecord,
    GraphicsMessage,
    GraphicsModel,
    GraphicsPictureDisplayPathRow,
    GraphicsPictureDisplayRecord,
    LoadMode,
)

_COMPOSITE_OBJECT_TYPE = "CompositeObject"
_PICTURE_DISPLAY_FAMILY = 5
_PICTURE_DISPLAY_SUBTYPE = "2"
_RECORD_FAMILY_CODE = "5"


def resolve_graphics_companion_path(code_path: Path, *, mode: LoadMode) -> Path | None:
    """Resolve the graphics companion file for ``code_path``.

    Mirrors SattLint's ``resolve_graphics_companion_path``: the companion always
    sits in the same directory as the code file (``with_suffix`` substitution,
    never a root-ordered lookup). ``.x`` code resolves only to ``.y``; draft
    code falls back from ``.g`` to ``.y``; a ``.g`` / ``.y`` input resolves to
    itself.
    """
    if code_path.suffix.lower() in {".g", ".y"}:
        return code_path

    candidates = (".y",) if code_path.suffix.lower() == ".x" else graphics_ext_candidates(mode)
    for extension in candidates:
        candidate = code_path.with_suffix(extension)
        if candidate.exists():
            return candidate
    return None


def _picture_display_record(record: GraphicsRecord, *, record_index: int) -> GraphicsPictureDisplayRecord:
    path_rows = tuple(
        GraphicsPictureDisplayPathRow(
            record_index=record_index,
            index_token=str(entry.index),
            index_value=entry.index,
            kind=entry.kind,
            raw_text=entry.text,
            span=SourceSpan(start=0, end=0, line=entry.line, column=entry.column),
        )
        for entry in record.entries
        if entry.kind != "other"
    )
    return GraphicsPictureDisplayRecord(
        record_index=record_index,
        record_start_line=record.start_line,
        record_end_line=record.end_line,
        subtype=_PICTURE_DISPLAY_SUBTYPE,
        path_row_lines=tuple(entry.line for entry in record.entries),
        path_rows=path_rows,
    )


def parse_graphics_text(text: str) -> GraphicsModel:
    """Parse ``.g`` / ``.y`` companion text into a ``GraphicsModel``.

    Bindings and structural problems surface as ``GraphicsMessage`` values
    (never raised); asset-path warnings are a consumer responsibility and are
    not computed here.

    The record readers follow the native byte consumption, which assumes the
    CRLF line endings the native writer emits (``read_text_cp1252`` preserves
    them). An LF-only text that ends a record field with an empty picture-display
    payload is read with the tolerant separator described in
    ``graphics_records``.
    """
    messages: list[GraphicsMessage] = []
    bindings: list[GraphicsBinding] = []
    for line_number, line_text in enumerate(text.splitlines(), start=1):
        row_bindings, binding_messages = _parse_graphics_binding_line(line_text, line=line_number)
        bindings.extend(row_bindings)
        messages.extend(binding_messages)

    companion = read_companion_records(text)
    composite_records: list[GraphicsCompositeRecord] = []
    picture_display_records: list[GraphicsPictureDisplayRecord] = []
    for record_index, record in enumerate(companion.records, start=1):
        composite_records.append(
            GraphicsCompositeRecord(
                record_index=record_index,
                ordinal=record_index,
                record_start_line=record.start_line,
                record_end_line=record.end_line,
                family_code=str(record.family_code),
            )
        )
        if record.family_code != _PICTURE_DISPLAY_FAMILY or record.subtype != 2:
            continue
        picture_display_records.append(_picture_display_record(record, record_index=record_index))

    if companion.error is not None:
        messages.append(
            GraphicsMessage(
                severity=companion.error.severity,
                message=companion.error.message,
                line=companion.error.line,
                column=1,
            )
        )

    return GraphicsModel(
        messages=tuple(messages),
        bindings=tuple(bindings),
        composite_records=tuple(composite_records),
        picture_display_records=tuple(picture_display_records),
    )


def parse_graphics_file(file_path: Path) -> GraphicsModel:
    """Read and parse a ``.g`` / ``.y`` companion file.

    ``OSError`` propagates to the caller (the loader maps it onto a load error);
    structural problems inside the file become ``GraphicsMessage`` values.
    """
    text = read_text_cp1252(file_path)
    return parse_graphics_text(text)


def correlate_composites(
    picture: object, model: GraphicsModel
) -> tuple[tuple[GraphicsCompositeBinding, ...], tuple[GraphicsMessage, ...]]:
    """Bind source ``CompositeObject`` markers to companion records by ordinal.

    Native ``00665fc0`` consumes the *next* companion record each time the source
    parser reaches a ``CompositeObject`` marker (token 0x78), in source-reading
    order across definitions - there is no name lookup. We therefore walk the
    source AST in the same order (module definitions, then nested submodules,
    then module types) and pair marker *n* with record *n*.

    Markers beyond the record list and records beyond the marker list are
    reported as ``GraphicsMessage`` values (native severity for both is not
    recovered); the pairs themselves carry the marker span so a consumer can
    point at the construct.
    """
    from sattline_parser.models.ast_model import BasePicture, GraphObject  # noqa: PLC0415

    if not isinstance(picture, BasePicture):  # pragma: no cover - defensive
        raise TypeError("correlate_composites expects a BasePicture")

    markers: list[SourceSpan | None] = []

    def walk(container: object) -> None:
        # A unit can hold several ``ModuleDef`` blocks and nested module types;
        # native order is source order, so every block contributes its markers.
        module_defs = getattr(container, "moduledefs", None) or [getattr(container, "moduledef", None)]
        for module_def in module_defs:
            for graph_object in getattr(module_def, "graph_objects", ()) or ():
                if isinstance(graph_object, GraphObject) and graph_object.type == _COMPOSITE_OBJECT_TYPE:
                    markers.append(None)
        for submodule in getattr(container, "submodules", ()) or ():
            walk(submodule)

    walk(picture)
    for module_type in picture.moduletype_defs:
        walk(module_type)

    messages = list(model.messages)
    pairs: list[GraphicsCompositeBinding] = []
    for index, record in enumerate(model.composite_records):
        if index < len(markers):
            pairs.append(GraphicsCompositeBinding(marker_ordinal=index + 1, record=record))
            continue
        messages.append(
            GraphicsMessage(
                severity="error",
                message=(
                    f"Companion record {record.ordinal} has no matching CompositeObject marker "
                    f"in the source (only {len(markers)} found)"
                ),
                line=record.record_start_line,
                column=1,
            )
        )
    if len(markers) > len(model.composite_records):  # pragma: no branch
        messages.append(
            GraphicsMessage(
                severity="error",
                message=(
                    f"{len(markers)} CompositeObject marker(s) in the source but only "
                    f"{len(model.composite_records)} companion record(s)"
                ),
                line=1,
                column=1,
            )
        )
    return tuple(pairs), tuple(messages)


__all__ = [
    "correlate_composites",
    "parse_graphics_file",
    "parse_graphics_text",
    "resolve_graphics_companion_path",
]
