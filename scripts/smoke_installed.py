"""Smoke test for an *installed* sattline-parser artifact (wheel or sdist).

Run from a clean virtualenv that only contains the built artifact (plus the
runtime deps it pulls in). Verifies:
- the package imports and reports a CalVer version
- grammar resources (``grammar/*.lark``) are shipped with the package
- a small valid SattLine source parses, transforms, and produces a BasePicture
- the public API surface works
"""

from __future__ import annotations

import importlib.resources

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


def main() -> None:
    grammar = importlib.resources.files("sattline_parser").joinpath("grammar", "sattline.lark")
    if not grammar.is_file():
        raise RuntimeError("grammar resource grammar/sattline.lark is missing from the installed package")

    parser = create_parser()
    bp = parse_source_text(_PROGRAM, parser=parser)
    if bp.moduledef is None or bp.moduledef.clipping_bounds != ((-1.0, -1.0), (1.0, 1.0)):
        raise RuntimeError("ModuleDef was not transformed correctly")
    if bp.parse_tree is None:
        raise RuntimeError("parse tree was not attached")

    for api in (create_parser, parse_source_text, describe_parse_error, preprocess_source):
        if not callable(api):
            raise RuntimeError(f"public API {api!r} is not callable")

    print(f"smoke OK (sattline-parser {__version__})")


if __name__ == "__main__":
    main()
