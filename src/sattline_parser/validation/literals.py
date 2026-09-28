"""Format validation for ``Duration_Value`` / ``Time_Value`` literal initializers.

Duration grammar (from ``DurationVariousFormats.s``): an optional leading
``-`` followed by either a plain seconds value (``10``, ``12.345``) or a
component form composed of the ordered units day/hour/minute/second/millisecond
(``0d0h5m0s0ms``, ``2h15m30s``). At least one component/value is required.

Time grammar (from ``TimeValueInit.s``): ``YYYY-MM-DD-hh:mm:ss.ttt``.
"""

from __future__ import annotations

import re
from typing import Final

_DURATION_COMPONENT: Final[str] = r"(?:\d+d)?(?:\d+h)?(?:\d+m)?(?:\d+(?:\.\d+)?s)?(?:\d+ms)?"
_PLAIN_SECONDS: Final[str] = r"\d+(?:\.\d+)?"
_DURATION_RE: Final[re.Pattern[str]] = re.compile(rf"^-?(?:{_DURATION_COMPONENT}|{_PLAIN_SECONDS})$")
_TIME_RE: Final[re.Pattern[str]] = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{2}:\d{2}:\d{2}\.\d{3}$")


def is_valid_duration(value: str) -> bool:
    if not value:
        return False
    body = value[1:] if value.startswith("-") else value
    if not any(char.isdigit() for char in body):
        return False
    return _DURATION_RE.fullmatch(value) is not None


def is_valid_time(value: str) -> bool:
    return _TIME_RE.fullmatch(value) is not None
