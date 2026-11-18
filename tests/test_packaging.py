# pyright: reportArgumentType=false
"""Packaging and installed-package smoke tests.

These tests live outside ``tests/parser`` on purpose: they verify the package
works when imported as an installed artifact (wheel/sdist), that grammar
resources ship with the package, and that the public API is intact. They also
prove that the full CI suite (``pytest``) runs tests beyond ``tests/parser``.
"""

from __future__ import annotations

import importlib.metadata
import importlib.resources
import importlib.util
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from lark.exceptions import UnexpectedInput

import sattline_parser
from sattline_parser import (
    SourceTooDeepError,
    __version__,
    create_parser,
    describe_parse_error,
    parse_source_bytes,
    parse_source_file,
    parse_source_text,
    preprocess_source,
)
from sattline_parser.api import parse_source_bytes as api_parse_source_bytes
from sattline_parser.models.ast_model import BasePicture

_SMALL_PROGRAM = (
    '"SyntaxVersion"\n'
    '"OriginalFileDate"\n'
    '"ProgramDate"\n'
    "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ENDDEF (*BasePicture*);\n"
)

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src"


def _installed_distribution() -> importlib.metadata.Distribution | None:
    """The ``sattline-parser`` distribution when it is installed, else ``None``.

    A gitignored ``src/sattline_parser.egg-info`` beside the checkout also
    satisfies ``importlib.metadata``, so a resolvable distribution is not
    evidence that the package is installed. Installed-artifact evidence belongs
    to ``scripts/smoke_installed.py``; here the metadata checks run only against
    a distribution located outside this checkout.
    """
    try:
        distribution = importlib.metadata.distribution("sattline-parser")
    except importlib.metadata.PackageNotFoundError:
        return None
    location = Path(distribution.locate_file("")).resolve()
    if location.is_relative_to(_SRC):
        return None
    return distribution


def test_package_version_is_calver() -> None:
    assert isinstance(__version__, str)
    assert re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}", __version__), __version__


def test_grammar_resources_are_packaged() -> None:
    grammar_path = importlib.resources.files("sattline_parser").joinpath("grammar", "sattline.lark")
    assert grammar_path.is_file()
    content = grammar_path.read_text(encoding="utf-8")
    assert "start:" in content


def test_scanner_token_resource_is_packaged() -> None:
    token_path = importlib.resources.files("sattline_parser").joinpath("preprocessing", "scanner_tokens.json")
    assert token_path.is_file()
    rows = json.loads(token_path.read_text(encoding="utf-8"))
    assert len(rows) == 174
    assert rows[0]["code"] == "#01"


def test_installed_package_parses_small_valid_program() -> None:
    parser = create_parser()
    bp = parse_source_text(_SMALL_PROGRAM, parser=parser)
    assert isinstance(bp, BasePicture)
    assert bp.name == "BasePicture"
    assert bp.moduledef is not None
    assert bp.moduledef.clipping_bounds == ((-1.0, -1.0), (1.0, 1.0))


def test_public_api_surface_is_available() -> None:
    assert callable(create_parser)
    assert callable(parse_source_text)
    assert callable(parse_source_file)
    assert callable(parse_source_bytes)
    assert callable(describe_parse_error)
    assert callable(preprocess_source)
    assert issubclass(SourceTooDeepError, UnexpectedInput)
    assert isinstance(parse_source_text(_SMALL_PROGRAM), BasePicture)


def test_parse_source_bytes_is_exported_from_the_package_root() -> None:
    """The documented top-level door resolves to the façade's own function."""
    assert "parse_source_bytes" in sattline_parser.__all__
    assert parse_source_bytes is api_parse_source_bytes
    picture = parse_source_bytes(_SMALL_PROGRAM.encode("cp1252"))
    assert isinstance(picture, BasePicture)
    assert picture.name == "BasePicture"


def test_parse_source_file_against_installed_package(tmp_path: Path) -> None:
    program = tmp_path / "Program.s"
    program.write_text(_SMALL_PROGRAM, encoding="utf-8")
    bp = parse_source_file(program)
    assert isinstance(bp, BasePicture)


_REQUIREMENT_BOUNDS = re.compile(r">=(?P<lower>[\d.]+),<(?P<upper>[\d.]+)")


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value.split("+", 1)[0]))


def _declared_lark_requirement() -> str:
    """The ``lark`` requirement string from ``pyproject.toml``."""
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = data["project"]["dependencies"]
    return next(entry for entry in dependencies if entry.startswith("lark"))


def test_installed_lark_version_satisfies_declared_range() -> None:
    import lark  # noqa: PLC0415

    requirement = _declared_lark_requirement()
    match = _REQUIREMENT_BOUNDS.search(requirement)
    assert match is not None, requirement
    lower = _version_tuple(match["lower"])
    upper = _version_tuple(match["upper"])
    version = _version_tuple(lark.__version__)
    assert version >= lower, f"lark {lark.__version__} is below the declared {requirement}"
    # The declaration is the source of truth: a bound change is a packaging
    # decision and must be re-evaluated, not silently accepted.
    assert version < upper, f"lark {lark.__version__} is outside the declared {requirement}"


def test_pep561_marker_is_packaged() -> None:
    marker = importlib.resources.files("sattline_parser").joinpath("py.typed")
    assert marker.is_file()


def test_fuzz_tooling_is_not_part_of_the_parser_package() -> None:
    assert importlib.util.find_spec("sattline_parser.fuzz_harness") is None
    assert importlib.util.find_spec("sattline_parser.parser_fuzzer") is None
    assert importlib.util.find_spec("sattline_parser.decode_fuzzer") is None


def test_console_script_is_registered() -> None:
    if _installed_distribution() is None:
        pytest.skip(
            "sattline-parser is not installed in this interpreter; scripts/smoke_installed.py owns that evidence"
        )
    scripts = {
        entry.name: entry.value
        for entry in importlib.metadata.entry_points(group="console_scripts")
        if entry.name == "sattline"
    }
    assert scripts == {"sattline": "sattline_parser.cli:main"}


def test_module_entry_point_reaches_the_cli() -> None:
    # The child must import *this* checkout, not whatever happens to be
    # installed in the interpreter. ``PYTHONPATH`` is pinned to ``src`` so the
    # test proves the checkout's module entry point, and CI's build-package job
    # proves the installed artifact through scripts/smoke_installed.py.
    completed = subprocess.run(
        [sys.executable, "-m", "sattline_parser", "version", "--json"],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONPATH": str(_SRC)},
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["schema"] == "sattline.v1.version"
    assert payload["version"] == __version__
    assert "check" in payload["commands"]
