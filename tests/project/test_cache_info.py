"""Public cache diagnostics (``SattLineProject.cache_info``)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sattline_parser.api import parse_source_file, parse_source_text
from sattline_parser.project import (
    CacheDisabledReason,
    FileASTCache,
    FileLookupCache,
    LoadMode,
    SattLineProgram,
    SattLineProject,
)
from sattline_parser.project import ast_cache as ast_cache_module
from sattline_parser.project import loader as loader_module

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


def _load(root: Path, *, cache_dir: Path | None) -> SattLineProject:
    return SattLineProject.load([root], LoadMode.DRAFT, ["Main"], cache_dir=cache_dir)


def _write_tree(tmp_path: Path) -> None:
    write_file(tmp_path, "Main.s", _CODE)
    write_file(tmp_path, "Main.l", "Lib\n")
    write_file(tmp_path, "Lib.s", _CODE)


def _reject_private(path: Path, *, create: bool = True) -> Path | None:
    del path, create
    return None


def test_no_cache_is_reported_as_not_configured(tmp_path: Path) -> None:
    _write_tree(tmp_path)

    project = _load(tmp_path, cache_dir=None)

    info = project.cache_info
    assert info.enabled is False
    assert info.disabled_reason is CacheDisabledReason.NOT_CONFIGURED
    assert (info.ast_hits, info.ast_misses, info.lookup_hits, info.lookup_misses) == (0, 0, 0, 0)


def test_a_cold_then_warm_load_reports_hits_and_misses(tmp_path: Path) -> None:
    _write_tree(tmp_path)
    cache_dir = tmp_path / "cache"

    cold = _load(tmp_path, cache_dir=cache_dir).cache_info
    warm = _load(tmp_path, cache_dir=cache_dir).cache_info

    assert cold.enabled is True
    assert cold.disabled_reason is None
    assert cold.ast_misses == 2
    assert cold.ast_hits == 0
    assert cold.lookup_misses >= 1
    assert warm.enabled is True
    assert warm.ast_hits == 2
    assert warm.ast_misses == 0
    assert warm.lookup_hits >= 1


def test_a_rejected_cache_directory_reports_privacy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_tree(tmp_path)
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    monkeypatch.setattr(loader_module, "private_cache_dir", _reject_private)

    info = _load(tmp_path, cache_dir=cache_dir).cache_info

    assert info.enabled is False
    assert info.disabled_reason is CacheDisabledReason.PRIVACY


def test_a_missing_cache_directory_reports_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_tree(tmp_path)
    monkeypatch.setattr(loader_module, "private_cache_dir", _reject_private)

    info = _load(tmp_path, cache_dir=tmp_path / "missing").cache_info

    assert info.enabled is False
    assert info.disabled_reason is CacheDisabledReason.UNAVAILABLE


def test_a_file_at_the_cache_path_reports_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_tree(tmp_path)
    cache_path = write_file(tmp_path, "cache", "not a directory")
    monkeypatch.setattr(loader_module, "private_cache_dir", _reject_private)

    info = _load(tmp_path, cache_dir=cache_path).cache_info

    assert info.enabled is False
    assert info.disabled_reason is CacheDisabledReason.UNAVAILABLE


def test_a_lookup_cache_that_lost_its_root_disables_the_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_tree(tmp_path)
    monkeypatch.setattr(FileLookupCache, "enabled", property(lambda _self: False))

    info = _load(tmp_path, cache_dir=tmp_path / "cache").cache_info

    assert info.enabled is False
    assert info.disabled_reason is CacheDisabledReason.UNAVAILABLE


def test_a_handle_disabled_after_construction_reports_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_tree(tmp_path)

    def failing_fingerprint() -> str:
        raise OSError("package files unavailable")

    monkeypatch.setattr(ast_cache_module, "_code_fingerprint", failing_fingerprint)

    info = _load(tmp_path, cache_dir=tmp_path / "cache").cache_info

    assert info.enabled is False
    assert info.disabled_reason is CacheDisabledReason.UNAVAILABLE


def test_from_programs_reports_no_cache() -> None:
    program = SattLineProgram(name="Main", code=parse_source_text(_CODE))

    project = SattLineProject.from_programs({"Main": program})

    assert project.cache_info.enabled is False
    assert project.cache_info.disabled_reason is CacheDisabledReason.NOT_CONFIGURED


def test_ast_cache_exposes_hits_and_misses(tmp_path: Path) -> None:
    code_path = write_file(tmp_path, "Main.s", _CODE)
    cache = FileASTCache(tmp_path / "cache")
    assert (cache.hits, cache.misses) == (0, 0)

    assert cache.load(code_path, "draft") is None
    cache.save(code_path, "draft", parse_source_file(code_path))
    assert cache.load(code_path, "draft") is not None

    assert (cache.hits, cache.misses) == (1, 1)


def test_a_parallel_warm_load_counts_worker_cache_reads(tmp_path: Path) -> None:
    _write_tree(tmp_path)
    cache_dir = tmp_path / "cache"
    _load(tmp_path, cache_dir=cache_dir)

    project = SattLineProject.load([tmp_path], LoadMode.DRAFT, ["Main"], cache_dir=cache_dir, workers=2)

    info = project.cache_info
    assert info.enabled is True
    assert info.ast_hits == 2
    assert info.ast_misses == 0
