"""The committed catalogue must match the generator output."""

from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from sattline_parser.builtins import BUILTIN_FUNCTIONS

_ROOT = Path(__file__).resolve().parents[2]
_GENERATOR_PATH = _ROOT / "scripts" / "gen_builtin_catalogue.py"
_SOURCE_PATH = _ROOT / "scripts" / "builtin_catalogue_source.json"
_CATALOGUE_PATH = _ROOT / "src" / "sattline_parser" / "builtins" / "catalogue.json"


def _load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_builtin_catalogue", _GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _source() -> dict[str, Any]:
    document: dict[str, Any] = json.loads(_SOURCE_PATH.read_text(encoding="utf-8"))
    return document


def test_committed_catalogue_matches_the_generator() -> None:
    generator = _load_generator()
    rendered = generator._render(generator.build(_source()))
    assert rendered == _CATALOGUE_PATH.read_text(encoding="utf-8")


def test_check_mode_passes_on_the_committed_catalogue() -> None:
    generator = _load_generator()
    assert generator.main(["--check"]) == 0


def test_source_and_catalogue_carry_the_same_names() -> None:
    assert set(_source()["functions"]) == set(BUILTIN_FUNCTIONS)


def test_generator_rejects_an_unknown_parameter_datatype() -> None:
    """A parameter datatype must be a scalar, a declared record, or AnyType."""
    generator = _load_generator()
    source = deepcopy(_source())
    source["functions"]["pid"]["parameters"][0]["datatype"] = "PidTypo"

    with pytest.raises(SystemExit) as exc_info:
        generator.build(source)

    assert "PidTypo" in str(exc_info.value)


def test_generator_rejects_an_unknown_return_datatype() -> None:
    generator = _load_generator()
    source = deepcopy(_source())
    source["functions"]["abs"]["return_type"] = "NoSuchType"

    with pytest.raises(SystemExit) as exc_info:
        generator.build(source)

    assert "NoSuchType" in str(exc_info.value)
