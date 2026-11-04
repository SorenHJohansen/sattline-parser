"""Benchmarks for the public parse and traversal entry points."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sattline_parser import parse_and_validate, parse_source_text, walk

_CORPUS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "corpus" / "valid"
_SOURCE = (_CORPUS / "UnCompressedFullGrammar.s").read_bytes().decode("cp1252")
_PICTURE = parse_source_text(_SOURCE)


def test_bench_parse_source_text(benchmark: Any) -> None:
    benchmark(parse_source_text, _SOURCE)


def test_bench_parse_and_validate(benchmark: Any) -> None:
    benchmark(parse_and_validate, _SOURCE)


def test_bench_walk(benchmark: Any) -> None:
    benchmark(lambda: sum(1 for _event in walk(_PICTURE)))
