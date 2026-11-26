# pyright: reportPrivateUsage=false
"""Branch coverage for conditional arcs the project layer tests do not reach.

Every test here targets one existing decision in the project layer, not a new
behaviour. The fixtures stay synthetic and small, and a filesystem refusal is
injected with ``monkeypatch`` instead of being staged on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sattline_parser.api import parse_source_bytes, parse_source_file, parse_source_text
from sattline_parser.models.ast_model import BasePicture
from sattline_parser.project import (
    LOOKUP_CACHE_VERSION,
    DistributionTarget,
    FileASTCache,
    FileLookupCache,
    LoadMode,
    LoadValidation,
    ModuleTypeCycleError,
    SattLineProgram,
    SattLineProject,
    _atomic,
    graphics_parsing,
)
from sattline_parser.project import executor as executor_module
from sattline_parser.project._atomic import PrivateDirectory
from sattline_parser.project.ast_cache import source_snapshot
from sattline_parser.project.executor import parse_code_file
from sattline_parser.project.graphics_bindings import parse_graphics_binding_line
from sattline_parser.project.scope import ProjectValidator

from ._support import write_file

_HEADER = """\"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N\"
\"Original file date: ---\"
\"Program date: 2026-04-23-12:00:00.000, name: {name}\"
"""

_CODE = (
    _HEADER.format(name="Prog")
    + """
BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
"""
)

_PLAIN_TYPEDEFS = """TYPEDEFINITIONS
   PlainType = MODULEDEFINITION
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*PlainType*);
"""

_LOOP_TYPEDEFS = """TYPEDEFINITIONS
   LoopType = MODULEDEFINITION DateCode_ 1
   LOCALVARIABLES
      Value: integer := 0;
   SUBMODULES
      Child Invocation
         ( 0.0 , 0.0 , 0.0 , 0.4 , 0.4
          ) : LoopType;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*LoopType*);
"""


def _source(
    name: str,
    *,
    typedefs: str = "",
    locals_block: str = "",
    body: str = "",
) -> str:
    return (
        _HEADER.format(name=name)
        + f"""
BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1
{typedefs}{locals_block}{body}
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ENDDEF (*BasePicture*);
"""
    )


def _write_code(tmp_path: Path, name: str = "Prog.s") -> Path:
    return write_file(tmp_path, name, _CODE)


def _picture(code_path: Path) -> BasePicture:
    return parse_source_file(code_path)


def _never_unlink(_self: PrivateDirectory, _name: str) -> bool:
    return False


def test_read_prefix_with_a_zero_limit_reads_nothing(tmp_path: Path) -> None:
    handle = PrivateDirectory.open(tmp_path, create=True)
    assert handle is not None
    handle.write_atomic("entry", b"payload")
    try:
        assert handle.read_prefix("entry", 0) == b""
    finally:
        handle.close()


def test_child_returns_none_for_a_missing_level_without_a_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_atomic, "_USES_DIRECTORY_DESCRIPTOR", False)
    parent = PrivateDirectory.open(tmp_path, create=True)
    assert parent is not None
    try:
        assert parent._descriptor is None
        assert PrivateDirectory.child(parent, "missing", create=False) is None
    finally:
        parent.close()


def test_disable_tolerates_a_missing_directory_then_a_missing_root(tmp_path: Path) -> None:
    cache = FileASTCache(tmp_path)
    directory = cache._directory
    root = cache._root
    assert directory is not None
    assert root is not None

    cache._directory = None
    directory.close()
    cache._disable()
    assert not cache.enabled

    cache._root = None
    cache._disable()


def test_prune_vanished_sources_keeps_an_entry_when_unlink_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code_path = _write_code(tmp_path)
    cache = FileASTCache(tmp_path)
    cache.save(code_path, "draft", _picture(code_path))
    code_path.unlink()
    monkeypatch.setattr(PrivateDirectory, "unlink", _never_unlink)

    assert cache._prune_vanished_sources() == 0
    assert len(list(cache.cache_dir.glob("*.pickle"))) == 1


def test_prune_stale_entries_keeps_a_foreign_entry_when_unlink_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache = FileASTCache(tmp_path)
    foreign = cache.cache_dir / "foreign.pickle"
    foreign.write_bytes(b"not a cache envelope")
    monkeypatch.setattr(PrivateDirectory, "unlink", _never_unlink)

    assert cache.prune_stale_entries() == 0
    assert foreign.exists()


def test_parse_code_file_uses_an_explicit_parser_and_snapshot(tmp_path: Path) -> None:
    code_path = _write_code(tmp_path)

    outcome = parse_code_file(
        (str(code_path), LoadMode.DRAFT.value, None, False, False),
        parse_bytes=parse_source_bytes,
        snapshot=source_snapshot,
    )

    assert outcome.ast is not None
    assert outcome.failure is None
    assert outcome.snapshot is None


def test_parse_code_file_misses_an_enabled_worker_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(executor_module, "_WORKER_CACHES", {})
    code_path = _write_code(tmp_path)
    cache_root = tmp_path / "cache"
    parent = FileASTCache(cache_root)
    assert parent.enabled

    outcome = parse_code_file((str(code_path), LoadMode.DRAFT.value, str(cache_root), False, False))

    assert outcome.ast is not None
    assert not outcome.cached
    assert outcome.snapshot is not None


def test_binding_line_skips_a_negative_length_match() -> None:
    bindings, messages = parse_graphics_binding_line("Var X -1 ", line=1, line_start_offset=0)

    assert bindings == ()
    assert messages == ()


def test_literal_path_keeps_a_non_numeric_nested_prefix() -> None:
    assert graphics_parsing._extract_literal_path("1 ABC DEF") == "ABC DEF"


def test_defined_names_keeps_the_first_spelling_on_a_tie() -> None:
    first = SattLineProgram(
        name="A", code=parse_source_text(_source("A", locals_block="LOCALVARIABLES\n   Shared: real;\n"))
    )
    second = SattLineProgram(
        name="B", code=parse_source_text(_source("B", locals_block="LOCALVARIABLES\n   Shared: real;\n"))
    )

    project = SattLineProject.from_programs({"A": first, "B": second})

    assert "Shared" in project.index.defined_names()


def test_lookup_load_keeps_the_table_when_an_entry_has_the_wrong_shape(tmp_path: Path) -> None:
    cache = FileLookupCache(tmp_path)
    payload = {"version": LOOKUP_CACHE_VERSION, "entries": {"k": {"base_dir": 1}}}
    cache.path.write_text(json.dumps(payload), encoding="utf-8")

    cache._load()

    assert cache.get("unit", "anything", "draft") is None


def test_distribution_download_reads_an_attribute_after_the_first() -> None:
    target = DistributionTarget(
        kind="Controller",
        name="Target",
        attributes=(("Name", "Target"), ("Download", "yes")),
    )

    assert target.download == "yes"


def test_cycle_search_skips_a_clean_visible_set_before_the_recursive_one() -> None:
    clean = SattLineProgram(name="Clean", code=parse_source_text(_source("Clean")))
    loopy = SattLineProgram(name="Loopy", code=parse_source_text(_source("Loopy", typedefs=_LOOP_TYPEDEFS)))
    validator = ProjectValidator(
        validate=LoadValidation.INVOKED,
        registry={"clean": clean, "loopy": loopy},
        resolved_dependencies={"clean": (), "loopy": ()},
        target_plan_keys={"clean", "loopy"},
    )

    with pytest.raises(ModuleTypeCycleError) as excinfo:
        validator.assert_no_moduletype_cycles()

    assert excinfo.value.cycle == ("LoopType", "LoopType")


def test_datecode_conflicts_skip_a_moduletype_without_a_datecode() -> None:
    code = parse_source_text(_source("Plain", typedefs=_PLAIN_TYPEDEFS))
    validator = ProjectValidator(
        validate=LoadValidation.NONE,
        registry={},
        resolved_dependencies={},
        target_plan_keys=set(),
    )

    assert validator._datecode_conflicts(code, library="libs", file_name="Plain.s") == []
