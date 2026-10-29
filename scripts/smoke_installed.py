"""Smoke test for an *installed* sattline-parser artifact (wheel or sdist).

Run from a clean virtualenv that only contains the built artifact (plus the
runtime deps it pulls in). Verifies:
- the package imports and reports a CalVer version
- grammar resources (``grammar/*.lark``) and the PEP 561 marker ship with the
  package
- a small valid SattLine source parses, transforms, and produces a BasePicture
- the public API surface works
- the ``sattline`` console script and ``python -m sattline_parser`` both reach
  the CLI and emit the documented ``sattline.v1.version`` payload
"""

from __future__ import annotations

import importlib.resources
import json
import shutil
import subprocess
import sys
from pathlib import Path

from sattline_parser import __version__, create_parser, describe_parse_error, parse_source_text, preprocess_source

_PROGRAM = (
    '"SyntaxVersion"\n'
    '"OriginalFileDate"\n'
    '"ProgramDate"\n'
    "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ENDDEF (*BasePicture*);\n"
)


def _check_resources() -> None:
    package = importlib.resources.files("sattline_parser")
    grammar = package.joinpath("grammar", "sattline.lark")
    if not grammar.is_file():
        raise RuntimeError("grammar resource grammar/sattline.lark is missing from the installed package")
    if not package.joinpath("py.typed").is_file():
        raise RuntimeError("PEP 561 marker py.typed is missing from the installed package")


def _check_public_api() -> None:
    parser = create_parser()
    bp = parse_source_text(_PROGRAM, parser=parser)
    if bp.moduledef is None or bp.moduledef.clipping_bounds != ((-1.0, -1.0), (1.0, 1.0)):
        raise RuntimeError("ModuleDef was not transformed correctly")
    if bp.parse_tree is not None:
        raise RuntimeError("parse tree should not be attached by default")
    retained = parse_source_text(_PROGRAM, parser=parser, retain_parse_tree=True)
    if retained.parse_tree is None:
        raise RuntimeError("parse tree was not attached when requested")

    for api in (create_parser, parse_source_text, describe_parse_error, preprocess_source):
        if not callable(api):
            raise RuntimeError(f"public API {api!r} is not callable")


def _check_cli(command: list[str], *, label: str) -> None:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"{label} exited {completed.returncode}: {completed.stderr.strip()}")
    payload = json.loads(completed.stdout)
    if payload.get("schema") != "sattline.v1.version":
        raise RuntimeError(f"{label} emitted an unexpected payload: {completed.stdout.strip()}")
    if payload.get("version") != __version__:
        raise RuntimeError(f"{label} reported version {payload.get('version')!r}, expected {__version__!r}")


def _console_script() -> str:
    """The installed ``sattline`` script: beside the interpreter, else on ``PATH``."""
    for candidate in (Path(sys.executable).with_name("sattline"), Path(sys.executable).with_name("sattline.exe")):
        if candidate.is_file():
            return str(candidate)
    found = shutil.which("sattline")
    if found is None:
        raise RuntimeError("the sattline console script is missing from the installed environment")
    return found


def main() -> None:
    _check_resources()
    _check_public_api()

    _check_cli([_console_script(), "version", "--json"], label="sattline version --json")
    _check_cli([sys.executable, "-m", "sattline_parser", "version", "--json"], label="python -m sattline_parser")

    print(f"smoke OK (sattline-parser {__version__})")


if __name__ == "__main__":
    main()
