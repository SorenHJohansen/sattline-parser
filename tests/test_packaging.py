# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false
"""Packaging and installed-package smoke tests.

These tests live outside ``tests/parser`` on purpose: they verify the package
works when imported as an installed artifact (wheel/sdist), that grammar
resources ship with the package, and that the public API is intact. They also
prove that the full CI suite (``pytest``) runs tests beyond ``tests/parser``.
"""

from __future__ import annotations

import importlib.metadata
import importlib.resources
import re
from pathlib import Path

from sattline_parser import (
    __version__,
    create_parser,
    describe_parse_error,
    parse_source_file,
    parse_source_text,
    preprocess_source,
)
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


def test_package_imports_and_version_metadata() -> None:
    assert isinstance(__version__, str)
    assert re.fullmatch(r"\d{4}\.\d{1,2}\.\d{1,2}", __version__), __version__
    assert importlib.metadata.version("sattline-parser") == __version__


def test_grammar_resources_are_packaged() -> None:
    grammar_path = importlib.resources.files("sattline_parser").joinpath("grammar", "sattline.lark")
    assert grammar_path.is_file()
    content = grammar_path.read_text(encoding="utf-8")
    assert "start:" in content


def test_installed_package_parses_small_valid_program() -> None:
    parser = create_parser()
    bp = parse_source_text(_SMALL_PROGRAM, parser=parser)
    assert isinstance(bp, BasePicture)
    assert bp.name == "BasePicture"
    assert bp.moduledef is not None
    assert bp.moduledef.clipping_bounds == ((-1.0, -1.0), (1.0, 1.0))


def test_installed_package_transforms_and_attaches_parse_tree() -> None:
    bp = parse_source_text(_SMALL_PROGRAM)
    assert bp.parse_tree is not None
    assert bp.parse_tree.data == "start"


def test_public_api_surface_is_available() -> None:
    assert callable(create_parser)
    assert callable(parse_source_text)
    assert callable(parse_source_file)
    assert callable(describe_parse_error)
    assert callable(preprocess_source)
    assert isinstance(parse_source_text(_SMALL_PROGRAM), BasePicture)


def test_parse_source_file_against_installed_package(tmp_path: Path) -> None:
    program = tmp_path / "Program.s"
    program.write_text(_SMALL_PROGRAM, encoding="utf-8")
    bp = parse_source_file(program)
    assert isinstance(bp, BasePicture)


def test_installed_lark_version_satisfies_declared_range() -> None:
    import lark  # noqa: PLC0415

    version = tuple(int(part) for part in lark.__version__.split("."))
    assert version >= (1, 3, 1), f"lark {lark.__version__} is below the declared minimum"
    # The declared range excludes lark 2.x; if a future lark 2.x is installed
    # the range must be re-evaluated, not silently accepted.
    assert version < (2, 0, 0), f"lark {lark.__version__} is outside the declared range <2"
