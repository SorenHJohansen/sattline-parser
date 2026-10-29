"""Process exit codes for the ``sattline`` CLI.

Agents branch on these instead of parsing output text: ``0`` clean, ``1``
findings, ``2`` a usage/input problem, ``3`` an internal error (a bug).
"""

from __future__ import annotations

from enum import IntEnum

__all__ = ["ExitCode"]


class ExitCode(IntEnum):
    """What the process returns to the shell."""

    OK = 0
    FINDINGS = 1
    USAGE = 2
    INTERNAL = 3
