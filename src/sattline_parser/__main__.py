"""``python -m sattline_parser`` — the same entry point as the ``sattline`` script."""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":  # pragma: no cover - exercised as a subprocess
    sys.exit(main())
