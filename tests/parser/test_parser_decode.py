from __future__ import annotations

import pathlib

from sattline_parser.preprocessing.compressed import (
    SEED_MAPPING,
    _MARKER_RE,
    decode_compressed,
    is_compressed,
    preprocess_sl_text,
)


def test_decode_compressed_normalizes_marker_prefixes_and_common_quirks() -> None:
    decoded = decode_compressed(
        " ".join(
            [
                "#01Tail",
                "#0<",
                "#0<Remark",
                "ENDDEF;",
                "; :=",
                "ENDIF; ,",
                "ENDIF; )",
                ":= ;",
                "GraphObjects : InteractObjects",
                'duration := "5s"',
                'time OpSave := "6s"',
                '=> "2024-01-02-03:04:05.678"',
                "ExecuteLocalOld = ExecuteLocal:Old ENDDEF",
                "ExecuteState:Old IF",
                "integer ENDDEF",
                "Enable_ = Flag : OutVar_",
                "TrueVar",
            ]
        ),
        SEED_MAPPING,
    )

    assert "(Tail" in decoded
    assert "*" in decoded
    assert "* Remark" in decoded
    assert "ENDDEF" in decoded and "ENDDEF;" not in decoded
    assert " :=" in decoded
    assert "ENDIF," in decoded
    assert "ENDIF)" in decoded
    assert ":= Default;" in decoded
    assert "InteractObjects" in decoded
    assert 'Duration_Value "5s"' in decoded
    assert 'Time_Value "6s"' in decoded
    assert '=> Time_Value "2024-01-02-03:04:05.678"' in decoded
    assert "ExecuteLocalOld = ExecuteLocal:Old; ENDDEF" in decoded
    assert "ExecuteState:Old; IF" in decoded
    assert "integer ; ENDDEF" in decoded
    assert "Enable_ = Flag : InVar_" in decoded
    assert "TTrueVar" in decoded


def test_preprocess_sl_text_keeps_existing_modulecode_and_fills_empty_trailing_args() -> None:
    decoded, _mapping = preprocess_sl_text(
        "MODULEDEFINITION Demo ModuleCode EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 : Func(a, )"
    )

    assert decoded.count("ModuleCode EQUATIONBLOCK") == 1
    assert "Func(a, 0)" in decoded


def test_decode_compressed_covers_marker_and_cleanup_quirks() -> None:
    decoded = decode_compressed(
        "#01Tail #0< #0<Flag #99 ENDIF GraphObjects : ENDDEF boolean ENDDEF Enable_ = Demo: OutVar_",
        {"#99": "Token"},
    )

    assert "(Tail" in decoded
    assert "*" in decoded
    assert "* Flag" in decoded
    assert "Token" in decoded
    assert "ENDIF;" in decoded
    assert "boolean ; ENDDEF" in decoded
    assert "Enable_ = Demo: InVar_" in decoded
    assert "GraphObjects : ENDDEF" not in decoded


def test_is_compressed_covers_false_and_true_heuristics() -> None:
    assert is_compressed("MODULEDEFINITION Demo EQUATIONBLOCK Main") is False
    assert is_compressed(" ".join(["#01X"] * 10)) is True


def test_seed_mapping_markers_all_exercised_by_corpus() -> None:
    corpus_dir = pathlib.Path(__file__).resolve().parents[2] / "tests" / "fixtures"
    corpus_text = "\n".join(
        f.read_text(encoding="utf-8", errors="replace")
        for f in sorted(corpus_dir.glob("CompressedFullGrammar.s"))
    )
    present = set(_MARKER_RE.findall(corpus_text))
    missing = sorted(set(SEED_MAPPING) - present)
    assert not missing, f"SEED_MAPPING markers not found in corpus: {missing}"


def test_seed_mapping_decoded_matches_uncompressed_golden() -> None:
    import json as _json

    snapshot_path = pathlib.Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "seed_mapping_snapshot.json"
    current = dict(sorted(SEED_MAPPING.items()))
    if snapshot_path.exists():
        stored = _json.loads(snapshot_path.read_text())
        assert current == stored, (
            "SEED_MAPPING has changed since the snapshot was taken.\n"
            "If the change is intentional, update the snapshot by running:\n"
            "  python -c \"import json; from sattline_parser.preprocessing.compressed import SEED_MAPPING; "
            "json.dump(dict(sorted(SEED_MAPPING.items())), open('tests/fixtures/seed_mapping_snapshot.json', 'w'), indent=2)\""
        )
    else:
        snapshot_path.write_text(_json.dumps(current, indent=2) + "\n")
