from __future__ import annotations

import json as _json
import pathlib
import re

import pytest

from sattline_parser.preprocessing.compressed import (
    _MARKER_RE,  # pyright: ignore[reportPrivateUsage]
    SCANNER_TOKENS,
    SEED_MAPPING,
    PreprocessError,
    decode_compressed,
    is_compressed,
    preprocess_sl_text,
    preprocess_source,
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CORPUS = _REPO_ROOT / "tests" / "fixtures" / "corpus" / "valid"
_TOKEN_DATA = _REPO_ROOT / "src" / "sattline_parser" / "preprocessing" / "scanner_tokens.json"
_HANDOFF_TOKENS = (
    _REPO_ROOT / "SattLine_Parser_AI_Handoff" / "references" / "simulator_v0_8" / "sattlint_sim" / "tokens.json"
)

#: Source hash of the recovered `.SCANNER` table. Changing this means re-pinning
#: the evidence, not editing the JSON by hand.
_TOKENS_SHA256 = "edf254ac3e39093ae56e8fa91fc68d7fee88291386fb1ea4103c29d941bb4b8a"


def test_scanner_token_table_is_the_recovered_scanner_enum() -> None:
    rows = _json.loads(_TOKEN_DATA.read_text(encoding="utf-8"))
    assert len(rows) == 206
    # Scanner ordinals are dense: id = ordinal + 8, ordinal 1..206 maps to a
    # three-character `#` code over the contiguous ASCII run '0'..'?'.
    assert [row["id"] for row in rows] == list(range(9, 215))
    for row in rows:
        ordinal = row["id"] - 8
        assert row["code"] == "#" + chr(48 + ordinal // 16) + chr(48 + ordinal % 16)
    assert {row["code"] for row in rows} == set(SCANNER_TOKENS)
    assert SEED_MAPPING is SCANNER_TOKENS


def test_scanner_token_table_pins_words_the_old_seed_table_got_wrong() -> None:
    # Recovered codes #1=, #1>, #9<, #:=: the earlier sample-derived table
    # conflated the On/Off literals with True/False and shifted two property
    # keywords.
    assert SCANNER_TOKENS["#1="] == "On"
    assert SCANNER_TOKENS["#1>"] == "Off"
    assert SCANNER_TOKENS["#1;"] == "True"
    assert SCANNER_TOKENS["#1<"] == "False"
    assert SCANNER_TOKENS["#9<"] == "Module_In_View"
    assert SCANNER_TOKENS["#:="] == "Relative_"
    assert SCANNER_TOKENS["#:<"] == "Abs_"
    assert SCANNER_TOKENS["#64"] == "Enable_"


def test_decode_compressed_expands_markers_without_prefix_repair() -> None:
    decoded = decode_compressed(" ".join(["#01Tail", "#0<", "#0<Remark", "#1="]), SCANNER_TOKENS)

    assert decoded == "(Tail * *Remark On"


def test_decode_compressed_rejects_unknown_marker() -> None:
    with pytest.raises(PreprocessError, match="Unknown compressed marker '#02'"):
        decode_compressed("#02", {"#01": "("})


def test_preprocess_sl_text_preserves_existing_modulecode() -> None:
    decoded, _mapping = preprocess_sl_text(
        "MODULEDEFINITION Demo ModuleCode EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :"
    )

    assert decoded.count("ModuleCode EQUATIONBLOCK") == 1


def test_every_marker_used_by_the_corpus_is_tabled() -> None:
    corpus_text = "\n".join(path.read_text(encoding="cp1252", errors="replace") for path in sorted(_CORPUS.glob("*.s")))
    present = set(_MARKER_RE.findall(corpus_text))
    assert present, "the corpus should exercise the compact form"
    missing = sorted(present - set(SCANNER_TOKENS))
    assert not missing, f"corpus uses compact codes absent from the scanner table: {missing}"


def _strip_comments(text: str) -> str:
    out: list[str] = []
    depth = 0
    index = 0
    while index < len(text):
        if text.startswith("(*", index):
            depth += 1
            index += 2
            continue
        if text.startswith("*)", index) and depth:
            depth -= 1
            index += 2
            continue
        if depth == 0:
            out.append(text[index])
        index += 1
    return "".join(out)


def _normalize(text: str) -> str:
    """Drop comments, layout and the compression flag: those legitimately differ."""
    text = _strip_comments(text)
    text = re.sub(r'"Syntax version [^"]*"', '"header"', text)
    return re.sub(r"\s+", "", text)


def test_compressed_and_uncompressed_full_grammar_twins_are_equivalent() -> None:
    """The compact golden must decode to its plain twin, token for token.

    This is the regression guard for the scanner table: with the sample-derived
    seed mapping it drifted at `On`/`Off`, `Module_In_View` and `Relative_`.
    """
    compressed = (_CORPUS / "CompressedFullGrammar.s").read_text(encoding="cp1252")
    uncompressed = (_CORPUS / "UnCompressedFullGrammar.s").read_text(encoding="cp1252")

    decoded = decode_compressed(compressed, SCANNER_TOKENS)

    assert _normalize(decoded) == _normalize(uncompressed)


def test_is_compressed_covers_false_and_true_heuristics() -> None:
    assert is_compressed("MODULEDEFINITION Demo EQUATIONBLOCK Main") is False
    assert is_compressed(" ".join(["#01X"] * 10)) is True


def test_undefined_byte_inside_an_unterminated_comment_still_fails(tmp_path: pathlib.Path) -> None:
    """Tolerant decoding is scoped to *closed* comments (HighByteInvalid.x).

    An undefined CP1252 byte inside an unterminated comment cannot be repaired,
    so the strict decode error survives instead of the file being guessed at.
    """
    from sattline_parser.api import parse_source_file  # noqa: PLC0415

    source = tmp_path / "Broken.s"
    source.write_bytes(b'"Syntax version 2.23, date: 2026-10-26-12:00:00.000 N"\n(* \x81')
    with pytest.raises(UnicodeDecodeError):
        parse_source_file(source)


def test_raw_keyword_in_a_coded_file_is_refused_with_a_clear_message() -> None:
    """Coded mode never reclassifies a raw word (0062cbc0).

    A raw ``SeqControl`` is an identifier there, not the keyword, so promoting it
    (what expanding codes and re-lexing would do) would accept a unit the real
    tool rejects. We refuse it explicitly instead.
    """
    source = (
        '"Syntax version 2.23, date: 2026-10-27-12:00:00.000 C"\n#22 MainSeq #01SeqControl, SeqTimer) #88 0.0, 0.0\n'
    )
    with pytest.raises(PreprocessError, match="Raw keyword 'SeqControl'"):
        preprocess_source(source)


def test_raw_keyword_inside_a_string_or_comment_is_left_alone() -> None:
    source = (
        '"Syntax version 2.23, date: 2026-10-27-12:00:00.000 C"\n#84 (* SeqControl WAIT_FOR *) X #8? "SeqControl";\n'
    )
    document = preprocess_source(source)
    assert "SeqControl" in document.normalized_text


def test_coded_golden_with_raw_identifiers_still_decodes() -> None:
    """Editor output never spells keywords raw, so real compact files stay valid."""
    compressed = (_CORPUS / "CompressedFullGrammar.s").read_text(encoding="cp1252")
    document = preprocess_source(compressed)
    assert "MODULEDEFINITION" in document.normalized_text
