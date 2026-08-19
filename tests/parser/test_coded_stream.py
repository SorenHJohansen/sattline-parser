# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportCallIssue=false, reportPrivateUsage=false

"""Coverage for the coded-stream binary decode layer.

A coded file is a 5-byte header (``\x80 3.1``) + CRLF followed by 100-byte
blocks, each terminated by CRLF. Bytes are xored with ``key[n] = (7n + 8) %
128``; a stored ``0x01`` is a sync byte that is skipped without advancing
``n``. A short non-text trailer may follow the final ``\r`` and is dropped.
"""

import pytest
from lark.exceptions import UnexpectedToken

from sattline_parser import api as parser_api
from sattline_parser.api import load_source_text
from sattline_parser.preprocessing.coded import decode_coded_stream, is_coded
from sattline_parser.preprocessing.compressed import PreprocessError

_HEADER = b"\x80 3.1"


def _encode(text: str, *, block_bytes: int = 100, sync_after: int | None = None) -> bytes:
    """Encode *text* into a coded stream (round-trip helper).

    Short blocks are padded with sync bytes (``0x01``), which the decoder
    skips without advancing the key. ``sync_after`` optionally injects an
    extra sync byte right after the *n*-th output character.
    """
    raw = bytearray()
    key_index = 0
    for key_index, ch in enumerate(text):
        if sync_after is not None and key_index == sync_after:
            raw.append(0x01)
        plain = ord(ch) & 0x7F
        key = (7 * key_index + 8) % 128
        raw.append(((plain ^ key) & 0x7F) | 0x80)
        key_index += 1
    payload = bytearray()
    for start in range(0, len(raw), block_bytes):
        block = raw[start : start + block_bytes]
        block += b"\x01" * (block_bytes - len(block))
        payload.extend(block)
        payload.extend(b"\r\n")
    return _HEADER + b"\r\n" + bytes(payload)


def test_is_coded_detects_header() -> None:
    assert is_coded(_HEADER + b"\r\n" + b"\x80" * 102)
    assert is_coded(b"") is False
    assert is_coded(b"\x80 3.0\r\n" + b"a" * 102) is False
    assert is_coded(b"Syntax version 2.23" * 10) is False


def test_decode_coded_stream_roundtrip() -> None:
    text = "\nA = 1;\nB = 2;\nC = 3;"
    assert decode_coded_stream(_encode(text)) == text


def test_decode_coded_stream_handles_sync_bytes() -> None:
    assert decode_coded_stream(_encode("AB\nC", sync_after=1)) == "AB\nC"


def test_decode_coded_stream_empty_payload() -> None:
    assert decode_coded_stream(_HEADER + b"\r\n") == ""


def test_decode_coded_stream_strips_trailer_after_last_cr() -> None:
    buried = _encode("\rbody\rline\r\x04\x7fgarbage")
    assert decode_coded_stream(buried) == "\rbody\rline"


def test_decode_coded_stream_no_cr_returns_all() -> None:
    assert decode_coded_stream(_encode("wholething")) == "wholething"


def test_decode_coded_stream_rejects_missing_header() -> None:
    with pytest.raises(PreprocessError, match="header"):
        decode_coded_stream(b"\x80 3.0\r\n")
    with pytest.raises(PreprocessError, match="header"):
        decode_coded_stream(b"plain text")


def test_decode_coded_stream_rejects_payload_misalignment() -> None:
    with pytest.raises(PreprocessError, match="multiple of"):
        decode_coded_stream(_HEADER + b"\r\n" + b"A" * 101)


def test_decode_coded_stream_rejects_bad_terminator() -> None:
    with pytest.raises(PreprocessError, match="CRLF"):
        decode_coded_stream(_HEADER + b"\r\n" + b"\x80" * 100 + b"\n\n")


def test_api_load_source_text_decodes_coded_file(tmp_path) -> None:
    path = tmp_path / "coded.sl"
    path.write_bytes(_encode("Coded := 1;\nMore := 2;"))
    assert load_source_text(path) == "Coded := 1;\nMore := 2;"


def test_decode_coded_file_bytes_direct() -> None:
    assert parser_api._decode_coded_file_bytes(_encode("text")) == "text"
    with pytest.raises(ValueError, match="not a coded stream"):
        parser_api._decode_coded_file_bytes(b"plain")
    events: list[str] = []
    parser_api._decode_coded_file_bytes(_encode("x"), debug=events.append)
    assert events == ["Coded format detected; decoding binary stream"]
    with pytest.raises(PreprocessError, match="multiple of"):
        parser_api._decode_coded_file_bytes(_HEADER + b"\r\n" + b"A" * 101)


def test_parse_source_file_decodes_coded_before_parsing(tmp_path) -> None:

    path = tmp_path / "coded.x"
    path.write_bytes(_encode("\nInvalid SattLine = ;"))
    with pytest.raises(UnexpectedToken):  # lark parse error: decode succeeded first
        parser_api.parse_source_file(path)
