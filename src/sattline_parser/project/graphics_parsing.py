"""Graphics companion parsing and companion-path resolution (plan §3.5, Phase 4).

Extracted from SattLint's ``graphics/validation.py`` into the parser: the
line/record scanner that reads ``.g`` / ``.y`` companion files into a
``GraphicsModel`` (bindings, messages, composite records, picture-display
records). Only the pure parse moves here; correlation
(``correlate_composite_records`` / ``correlate_picture_display_records``) and
asset-path warnings stay in the consumer.
"""

from __future__ import annotations

from pathlib import Path

from sattline_parser.api import read_text_with_fallback
from sattline_parser.models.ast_model import GraphicsBinding, SourceSpan

from .formats import graphics_ext_candidates
from .graphics_bindings import _BINDING_LINE_RE, _parse_graphics_binding_line, _parse_graphics_binding_match
from .models import (
    GraphicsCompositeRecord,
    GraphicsMessage,
    GraphicsModel,
    GraphicsPictureDisplayPathRow,
    GraphicsPictureDisplayRecord,
    LoadMode,
)

_RECORD_FAMILY_CODE = "5"
_PICTURE_DISPLAY_SUBTYPE = "2"
_RECORD_TERMINATOR = "0"
_COMPOSITE_RECORD_FAMILIES = frozenset({"1", "2", "4", "5"})
_KEEP_SHAPE_VALUES = {"t", "f"}


def _nonempty_record_lines(lines: list[str], start_index: int, end_index: int) -> list[tuple[int, str]]:
    return [
        (line_index, lines[line_index]) for line_index in range(start_index, end_index) if lines[line_index].strip()
    ]


def _find_record_end(lines: list[str], start_index: int) -> int | None:
    for line_index in range(start_index + 1, len(lines)):
        if lines[line_index].strip() != _RECORD_TERMINATOR:
            continue
        if line_index + 1 >= len(lines) or not lines[line_index + 1].strip():
            return line_index
    return None


def _extract_literal_path(row_text: str) -> str | None:
    parts = row_text.strip().split(None, 1)
    if len(parts) != 2:
        return None

    payload = parts[1].strip()
    if not payload or payload.startswith(("Var ", "Lit ", "None ")):
        return None

    nested_parts = payload.split(None, 1)
    if len(nested_parts) == 2 and nested_parts[0].lstrip("+-").isdigit():
        payload = nested_parts[1].strip()

    return payload or None


def _split_nested_picture_display_payload(payload: str) -> tuple[str | None, str]:
    nested_parts = payload.split(None, 1)
    if len(nested_parts) != 2:
        return None, payload
    nested_index_token, nested_payload = nested_parts
    if not nested_index_token.lstrip("+-").isdigit():
        return None, payload
    return nested_index_token, nested_payload.strip()


def _parse_picture_display_row(
    row_text: str,
    *,
    record_index: int,
    line: int,
) -> GraphicsPictureDisplayPathRow | None:
    stripped = row_text.strip()
    if not stripped:
        return None

    parts = stripped.split(None, 1)
    if len(parts) != 2:
        return None

    index_token, payload = parts
    index_value = int(index_token) if index_token.lstrip("+-").isdigit() else None
    payload = payload.strip()
    if not payload:  # pragma: no cover - split(None, 1) never yields an empty second token
        return None

    binding_payload = payload
    nested_index_token: str | None = None
    binding_match = _BINDING_LINE_RE.match(binding_payload)
    if binding_match is None:
        nested_index_token, binding_payload = _split_nested_picture_display_payload(payload)
        binding_match = _BINDING_LINE_RE.match(binding_payload)
    if binding_match is not None:
        binding_meta = binding_match.group(2).casefold()
        if binding_meta == "invalid":
            if nested_index_token is None:
                return None
            row_kind = "variable_invalid"
        elif binding_meta not in {"true", "false"} and not binding_meta.lstrip("+-").isdigit():
            return None
        else:
            row_kind = "variable"
        binding, _binding_messages = _parse_graphics_binding_match(binding_payload, line=line, match=binding_match)
        if binding is None or binding.kind != "var":
            return None
        column = row_text.find(binding.raw_text)
        span = SourceSpan(start=0, end=0, line=line, column=(column + 1) if column >= 0 else 1)
        return GraphicsPictureDisplayPathRow(
            record_index=record_index,
            index_token=index_token,
            index_value=index_value,
            kind=row_kind,
            raw_text=binding.raw_text,
            span=span,
        )

    literal_path = _extract_literal_path(row_text)
    if literal_path is None:
        return None
    column = row_text.find(literal_path)
    return GraphicsPictureDisplayPathRow(
        record_index=record_index,
        index_token=index_token,
        index_value=index_value,
        kind="literal",
        raw_text=literal_path,
        span=SourceSpan(start=0, end=0, line=line, column=(column + 1) if column >= 0 else 1),
    )


def _extract_picture_display_record(
    record_lines: list[tuple[int, str]],
    *,
    record_index: int,
    record_start_line: int,
    record_end_line: int,
) -> GraphicsPictureDisplayRecord:
    path_row_lines = tuple(row_line_index + 1 for row_line_index, _row_line in record_lines[5:-2])
    path_rows = tuple(
        row
        for row_line_index, row_line in record_lines[5:-2]
        if (row := _parse_picture_display_row(row_line, record_index=record_index, line=row_line_index + 1)) is not None
    )
    return GraphicsPictureDisplayRecord(
        record_index=record_index,
        record_start_line=record_start_line,
        record_end_line=record_end_line,
        path_row_lines=path_row_lines,
        path_rows=path_rows,
    )


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


def parse_graphics_text(text: str) -> GraphicsModel:
    """Parse ``.g`` / ``.y`` companion text into a ``GraphicsModel``.

    Bindings and structural problems surface as ``GraphicsMessage`` values
    (never raised); asset-path warnings are a consumer responsibility and are
    not computed here.
    """
    lines = text.splitlines()
    messages: list[GraphicsMessage] = []
    bindings: list[GraphicsBinding] = []
    composite_records: list[GraphicsCompositeRecord] = []
    picture_display_records: list[GraphicsPictureDisplayRecord] = []

    for line_number, line_text in enumerate(lines, start=1):
        row_bindings, binding_messages = _parse_graphics_binding_line(line_text, line=line_number)
        bindings.extend(row_bindings)
        messages.extend(binding_messages)

    line_index = 0
    record_index = 0

    while line_index < len(lines):
        family_code = lines[line_index].strip()
        if family_code not in _COMPOSITE_RECORD_FAMILIES:
            line_index += 1
            continue

        record_end = _find_record_end(lines, line_index)
        if record_end is None:
            messages.append(
                GraphicsMessage(
                    severity="error",
                    message="Unterminated graphics record; expected trailing '0' line",
                    line=line_index + 1,
                    column=1,
                )
            )
            break

        record_index += 1
        composite_records.append(
            GraphicsCompositeRecord(
                record_index=record_index,
                record_start_line=line_index + 1,
                record_end_line=record_end + 1,
                family_code=family_code,
            )
        )

        if family_code != _RECORD_FAMILY_CODE:
            line_index = record_end + 1
            continue

        record_lines = _nonempty_record_lines(lines, line_index + 1, record_end)
        if len(record_lines) < 6:
            line_index = record_end + 1
            continue

        subtype_line_index, subtype_line = record_lines[3]
        if subtype_line.strip() != _PICTURE_DISPLAY_SUBTYPE:
            line_index = record_end + 1
            continue

        keep_shape_line_index, keep_shape_line = record_lines[-1]
        if keep_shape_line.strip().casefold() not in _KEEP_SHAPE_VALUES:
            messages.append(
                GraphicsMessage(
                    severity="error",
                    message="PictureDisplay record is missing the trailing KeepPictureShape flag",
                    line=subtype_line_index + 1,
                    column=1,
                )
            )
            line_index = record_end + 1
            continue

        picture_display_record = _extract_picture_display_record(
            record_lines,
            record_index=record_index,
            record_start_line=line_index + 1,
            record_end_line=record_end + 1,
        )
        picture_display_records.append(picture_display_record)
        line_index = keep_shape_line_index + 1

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
    text = read_text_with_fallback(file_path)
    return parse_graphics_text(text)


__all__ = ["parse_graphics_file", "parse_graphics_text", "resolve_graphics_companion_path"]
