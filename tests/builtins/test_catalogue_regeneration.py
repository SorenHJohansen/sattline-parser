"""The committed catalogue must match the generator output."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

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


def test_committed_catalogue_matches_the_generator() -> None:
    generator = _load_generator()
    source = json.loads(_SOURCE_PATH.read_text(encoding="utf-8"))
    rendered = generator._render(generator.build(source))
    assert rendered == _CATALOGUE_PATH.read_text(encoding="utf-8")


def test_check_mode_passes_on_the_committed_catalogue() -> None:
    generator = _load_generator()
    assert generator.main(["--check"]) == 0


def test_source_and_catalogue_carry_the_same_names() -> None:
    source = json.loads(_SOURCE_PATH.read_text(encoding="utf-8"))
    assert set(source["functions"]) == set(BUILTIN_FUNCTIONS)
