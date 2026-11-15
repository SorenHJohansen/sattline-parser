"""On-disk companion fixtures: one synthetic file per artifact kind.

Every other project test writes companion text into ``tmp_path``. These
fixtures keep one small, synthetically written file per extension in the
repository, so the resolver and both parsers are exercised against an actual
file and an actual encoding path.
"""

from __future__ import annotations

from pathlib import Path

from sattline_parser.project import LoadMode, SattLineProject, read_dependency_names

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "project" / "companions"


def test_draft_body_pairs_with_l_g_and_p() -> None:
    project = SattLineProject.load(
        [_FIXTURES],
        LoadMode.DRAFT,
        targets=("DraftBody",),
        cache_dir=None,
    )
    program = project.get("DraftBody")

    assert program.format.code_ext == ".s"
    assert program.format.deps_ext == ".l"
    assert program.format.graphics_ext == ".g"
    assert program.format.distribution_ext == ".p"
    assert program.dependencies == ("Lib",)
    assert program.graphics is not None
    assert program.graphics.bindings
    assert program.distribution is not None
    assert program.distribution.version == "Distributiondata version 1.0"


def test_sidecar_is_decoded_as_cp1252() -> None:
    assert read_dependency_names(_FIXTURES / "Encoded.l") == ("Café",)


def test_official_body_pairs_with_z_y_and_q() -> None:
    project = SattLineProject.load(
        [_FIXTURES],
        LoadMode.OFFICIAL,
        targets=("OfficialBody",),
        cache_dir=None,
    )
    program = project.get("OfficialBody")

    assert program.format.code_ext == ".x"
    assert program.format.deps_ext == ".z"
    assert program.format.graphics_ext == ".y"
    assert program.format.distribution_ext == ".q"
    assert program.dependencies == ("Lib",)
    assert program.graphics is not None
    assert program.graphics.bindings
    assert program.distribution is not None
    assert program.distribution.version == "Distributiondata version 1.0"
