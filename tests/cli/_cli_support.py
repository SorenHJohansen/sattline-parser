"""Shared fixtures for the ``sattline`` CLI tests."""

from __future__ import annotations

from pathlib import Path

#: A valid unit: one sequence, one equation, one local variable.
VALID_SOURCE = (
    '"Syntax version 2.23, date: 2026-10-28-00:00:00.000 N"\n'
    '"Original file date: ---"\n'
    '"Program date: 2026-10-28-00:00:00.000, name: Sample"\n'
    "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1\n"
    "LOCALVARIABLES\n"
    "   Flag: boolean := False;\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ModuleCode\n"
    "SEQUENCE Demo COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
    "   SEQINITSTEP Init\n"
    "   SEQTRANSITION Tr WAIT_FOR Flag\n"
    "ENDSEQUENCE\n"
    "ENDDEF (*BasePicture*);\n"
)

#: Two adjacent steps: CONSECUTIVE_SEQUENCE_STEPS, located on the second step.
CONSECUTIVE_STEPS_SOURCE = VALID_SOURCE.replace(
    "   SEQINITSTEP Init\n   SEQTRANSITION Tr WAIT_FOR Flag\n",
    "   SEQINITSTEP Init\n   SEQSTEP Second\n   SEQTRANSITION Tr WAIT_FOR Flag\n",
)

#: `ENDDEF` without its terminating semicolon: a parse error with a hint.
PARSE_ERROR_SOURCE = (
    '"Syntax version 2.23, date: 2026-10-28-00:00:00.000 N"\n'
    '"Original file date: ---"\n'
    '"Program date: 2026-10-28-00:00:00.000, name: Broken"\n'
    "BasePicture Invocation ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0 ) : MODULEDEFINITION DateCode_ 1\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ENDDEF (*BasePicture*)\n"
)

#: A compact source with an unknown marker: the decoder refuses it.
DECODE_ERROR_SOURCE = '"Syntax version 2.23, date: 2026-10-28-00:00:00.000 C"\n#ZZ\n'


def write_source(directory: Path, name: str, text: str) -> Path:
    path = directory / name
    path.write_bytes(text.encode("cp1252"))
    return path


_CODED_HEADER = b"\x80 3.1\r\n"
_CODED_BLOCK_BYTES = 100


def encode_coded(text: str) -> bytes:
    """Encode *text* as a byte-coded stream (the binary framing some ``.x`` use).

    Stored bytes are ``((plain ^ key) | 0x80)`` with ``key[n] = (7n + 8) % 128``;
    short blocks are padded with sync bytes (``0x01``), which the decoder skips.
    """
    payload = bytearray()
    block = bytearray()
    for key_index, character in enumerate(text):
        key = (7 * key_index + 8) % 128
        block.append(((ord(character) & 0x7F) ^ key) | 0x80)
        if len(block) == _CODED_BLOCK_BYTES:
            payload.extend(block + b"\r\n")
            block.clear()
    block.extend(b"\x01" * (_CODED_BLOCK_BYTES - len(block)))
    payload.extend(block + b"\r\n")
    return _CODED_HEADER + bytes(payload)


def write_coded(directory: Path, name: str, text: str) -> Path:
    """Write *text* as a byte-coded stream, the way the workstation stores ``.x``."""
    path = directory / name
    path.write_bytes(encode_coded(text))
    return path
