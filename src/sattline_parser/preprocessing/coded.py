"""Binary framing and stream decoding for ABB coded SattLine sources.

A coded file is a binary stream:

* a 5-byte header ``\x80 3.1`` followed by CRLF;
* then 100-byte blocks, each terminated by CRLF;
* inside a block, every byte ``b`` stores a plain byte ``p`` (0..127) xored
  with a stream key: ``p = (b & 0x7F) ^ key[n]`` with ``key[n] = (7*n + 8) % 128``;
* a stored ``0x01`` is a sync byte: it is skipped and does not advance ``n``.

The decoded payload is the original SattLine text with CRLF line endings:
stored lone ``\r`` terminators are normalized to ``\r\n``, and genuine
``\r\n`` pairs pass through untouched. The text always ends with a line
terminator, matching native SattLine sources.
A coded stream may carry a short non-text trailer after its final ``\r``
(file-format residue); decoding drops the trailer but keeps that ``\r``.
"""

from __future__ import annotations

import re

from .compressed import PreprocessError

__all__ = [
    "decode_coded_stream",
    "is_coded",
]

_HEADER = b"\x80 3.1"
_HEADER_LINE = _HEADER + b"\r\n"
_BLOCK_BYTES = 100
_FRAME_BYTES = _BLOCK_BYTES + 2
_SYNC_BYTE = 0x01
_LONE_CR_RE = re.compile(r"\r(?!\n)")
# The ``(b & 0x7F) ^ key`` decode mask destroys bit 7, so cp1252 curly
# quotes (0x93/0x94) surface as the control characters DC3/DC4. Those can
# never occur in legitimate SattLine source, so restoring them is unambiguous.
_BIT7_REPAIRS = {"\x13": "“", "\x14": "”"}


def is_coded(data: bytes) -> bool:
    """True when *data* starts with the complete coded-stream header (``\\x80 3.1\\r\\n``)."""
    return data.startswith(_HEADER_LINE)


def decode_coded_stream(data: bytes) -> str:
    """Decode a coded stream into the embedded SattLine text.

    Raises :class:`PreprocessError` when the framing is malformed (missing
    header, header missing its CRLF terminator, payload not an exact multiple
    of the block frame, or a block without its CRLF terminator).
    """
    if not data.startswith(_HEADER):
        raise PreprocessError("coded stream: missing '\\x80 3.1' header")
    if not data.startswith(_HEADER_LINE):
        raise PreprocessError("coded stream: header missing CRLF terminator")
    payload = data[len(_HEADER_LINE) :]
    block_count, remainder = divmod(len(payload), _FRAME_BYTES)
    if remainder:
        raise PreprocessError(f"coded stream: payload is not a multiple of {_FRAME_BYTES} bytes")

    decoded_parts: list[str] = []
    key_index = 0
    for block_num in range(block_count):
        start = block_num * _FRAME_BYTES
        block = payload[start : start + _BLOCK_BYTES]
        terminator = payload[start + _BLOCK_BYTES : start + _FRAME_BYTES]
        if terminator != b"\r\n":
            raise PreprocessError(f"coded stream: block {block_num} missing CRLF terminator")
        for byte_value in block:
            if byte_value == _SYNC_BYTE:
                continue
            key = (7 * key_index + 8) % 128
            decoded_parts.append(chr((byte_value & 0x7F) ^ key))
            key_index += 1

    decoded = "".join(decoded_parts)
    for stray, repaired in _BIT7_REPAIRS.items():
        if stray in decoded:
            decoded = decoded.replace(stray, repaired)
    last_cr = decoded.rfind("\r")
    if last_cr < 0:
        return decoded
    decoded = decoded[: last_cr + 1]
    return _LONE_CR_RE.sub("\r\n", decoded)
