# pyright: reportArgumentType=false
"""Layout metadata classification for spans and geometry fields."""

from __future__ import annotations

import dataclasses
import types
import typing

from sattline_parser.models import ast_model, clauses, expressions, tails

_MODEL_MODULES = (ast_model, expressions, clauses, tails)

#: Non-span fields that describe presentation rather than program meaning.
#: The test compares this set with the fields marked ``layout`` so a new
#: geometry field forces a decision.
_LAYOUT_GEOMETRY = {
    (ast_model.BasePicture, "position"),
    (ast_model.Equation, "position"),
    (ast_model.Equation, "size"),
    (ast_model.Sequence, "position"),
    (ast_model.Sequence, "size"),
    (ast_model.ModuleHeader, "invoke_coord"),
    (clauses.ClippingClause, "bounds"),
}


def _model_dataclasses() -> list[type[object]]:
    found: list[type[object]] = []
    for module in _MODEL_MODULES:
        for name in module.__all__:
            value = getattr(module, name)
            if isinstance(value, type) and dataclasses.is_dataclass(value):
                found.append(value)
    return found


def _is_span_annotation(annotation: object) -> bool:
    if annotation is ast_model.SourceSpan:
        return True
    return isinstance(annotation, types.UnionType) and ast_model.SourceSpan in typing.get_args(annotation)


def _span_fields() -> set[tuple[type[object], str]]:
    spans: set[tuple[type[object], str]] = set()
    for cls in _model_dataclasses():
        hints = typing.get_type_hints(cls, localns={"SourceSpan": ast_model.SourceSpan})
        for field in dataclasses.fields(cls):
            if _is_span_annotation(hints[field.name]):
                spans.add((cls, field.name))
    return spans


def _layout_fields() -> set[tuple[type[object], str]]:
    marked: set[tuple[type[object], str]] = set()
    for cls in _model_dataclasses():
        for field in dataclasses.fields(cls):
            if field.metadata.get("layout") is True:
                marked.add((cls, field.name))
    return marked


def test_every_source_span_field_is_layout_metadata() -> None:
    for cls in _model_dataclasses():
        hints = typing.get_type_hints(cls, localns={"SourceSpan": ast_model.SourceSpan})
        for field in dataclasses.fields(cls):
            if not _is_span_annotation(hints[field.name]):
                continue
            assert field.metadata.get("layout") is True, (cls.__name__, field.name)
            assert field.compare is False, (cls.__name__, field.name)


def test_layout_marked_fields_are_spans_or_declared_geometry() -> None:
    assert _layout_fields() - _span_fields() == _LAYOUT_GEOMETRY


def test_layout_geometry_fields_are_excluded_from_equality() -> None:
    for cls, name in _LAYOUT_GEOMETRY:
        field = next(field for field in dataclasses.fields(cls) if field.name == name)
        assert field.metadata.get("layout") is True, (cls.__name__, name)
        assert field.compare is False, (cls.__name__, name)


def test_span_annotation_detection_accepts_bare_and_optional_forms() -> None:
    assert _is_span_annotation(ast_model.SourceSpan)
    assert _is_span_annotation(ast_model.SourceSpan | None)
    assert not _is_span_annotation(int)
