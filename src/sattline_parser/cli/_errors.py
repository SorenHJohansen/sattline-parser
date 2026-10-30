"""User-facing CLI failures (never a traceback, always a message + exit code)."""

from __future__ import annotations

__all__ = ["CliError"]


class CliError(Exception):
    """A problem with the request itself: unreadable path, undecodable input, bad flags."""
