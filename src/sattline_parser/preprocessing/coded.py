"""Binary framing and stream decoding for ABB coded SattLine sources.

A coded file is a binary stream:

* a 5-byte header ``\x80 3.1`` followed by CRLF;
* then 100-byte blocks, each terminated by CRLF;
* inside a block, every byte ``b`` stores a plain byte ``p`` (0..127) xored
  with a stream key: ``p = (b & 0x7F) ^ key[n]`` with ``key[n] = (7*n + 8) % 128``;
* a stored ``0x01`` is a sync byte: it is skipped and does not advance ``n``.

The decoded payload is the original SattLine text (CR-only line endings).
A coded stream may carry a short non-text trailer after its final ``\r``
(file-format residue); decoding drops everything after the last ``\r``.
"""

from __future__ import annotations

from .compressed import PreprocessError

__all__ = [
    "decode_coded_stream",
    "is_coded",
]

_HEADER = b"\x80 3.1"
_BLOCK_BYTES = 100
_FRAME_BYTES = _BLOCK_BYTES + 2
_SYNC_BYTE = 0x01


def is_coded(data: bytes) -> bool:
    """True when *data* starts with the coded-stream header."""
    return data.startswith(_HEADER)


def decode_coded_stream(data: bytes) -> str:
    """Decode a coded stream into the embedded SattLine text.

    Raises :class:`PreprocessError` when the framing is malformed (missing
    header, payload not an exact multiple of the block frame, or a block
    without its CRLF terminator).
    """
    if not data.startswith(_HEADER):
        raise PreprocessError("coded stream: missing '\\x80 3.1' header")
    payload = data[len(_HEADER) + 2 :]
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
    last_cr = decoded.rfind("\r")
    if last_cr < 0:
        return decoded
    return decoded[:last_cr]
