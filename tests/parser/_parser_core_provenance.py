# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportCallIssue=false, reportPrivateUsage=false, reportUnusedImport=false, reportAttributeAccessIssue=false, reportOptionalSubscript=false, reportOptionalMemberAccess=false, reportOptionalOperand=false
# ruff: noqa: F403, F405
"""Source-provenance tests.

Verify that preprocessing, parsing, AST spans, and diagnostics all refer to the
ORIGINAL source, including for compressed input. Each end-to-end test checks
``original -> preprocess -> parse -> AST node -> span -> slice original source``.
"""

from ._parser_core_test_support import *


def _compress(text: str, targets: list[str] | None = None) -> str:
    """Naive compressor: single-pass longest-match replacement outside strings/comments.

    Mirrors the decoder's opaque-region handling so round-trips are exact.
    """
    import re as _re  # noqa: PLC0415

    from sattline_parser.preprocessing import SEED_MAPPING  # noqa: PLC0415

    reverse: dict[str, str] = {}
    for marker, word in SEED_MAPPING.items():
        if word and word not in reverse:
            reverse[word] = marker
    if targets is None:
        targets = sorted(reverse, key=len, reverse=True)
    pattern = _re.compile("|".join(_re.escape(w) for w in targets if w not in ("True", "False")))

    parts: list[str] = []
    last = 0
    for _kind, start, end in _opaque_regions(text):
        parts.append(pattern.sub(lambda m: reverse[m.group(0)], text[last:start]))
        parts.append(text[start:end])
        last = end
    parts.append(pattern.sub(lambda m: reverse[m.group(0)], text[last:]))
    return "".join(parts)


def _opaque_regions(text: str) -> list[tuple[str, int, int]]:
    from sattline_parser.preprocessing.compressed import _scan_opaque_regions as scan  # noqa: PLC0415

    return scan(text)


_PROGRAM = (
    '"SyntaxVersion"\n'
    '"OriginalFileDate"\n'
    '"ProgramDate"\n'
    "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
    "LOCALVARIABLES\n"
    "    Counter: integer := 0;\n"
    "ModuleDef\n"
    "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
    "ModuleCode\n"
    "    EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
    "        Counter = Counter + 1;\n"
    "ENDDEF (*BasePicture*);\n"
)

_COMPRESSED = _compress(_PROGRAM)


def test_source_document_identity_maps_positions_exactly():
    doc = SourceDocument.identity("hello\nworld")
    assert doc.is_identity() is True
    assert doc.map_position(0) == 0
    assert doc.map_position(6) == 6
    assert doc.map_range(1, 5) == (1, 5)
    assert doc.line_col(0) == (1, 1)
    assert doc.line_col(6) == (2, 1)
    span = doc.span_from_normalized(0, 5)
    assert span == SourceSpan(start=0, end=5, line=1, column=1)


def test_source_document_rejects_mismatched_char_map():
    with pytest.raises(ValueError, match="char_map length"):
        SourceDocument("abc", "ab", (0, 1, 2))


def test_source_document_derives_line_and_column_from_original_text():
    doc = SourceDocument("a\nb\ncdef", "a\nb\ncdef", tuple(range(8)))
    assert doc.line_col(0) == (1, 1)
    assert doc.line_col(2) == (2, 1)
    assert doc.line_col(4) == (3, 1)
    assert doc.line_col(8) == (3, 5)
    assert doc.line_col(100) == (3, 5)
    assert doc.line_col(-5) == (1, 1)


def test_source_document_map_position_anchors_generated_chars_backward():
    # "XY" is original, "G" is generated between X and Y.
    doc = SourceDocument("XY", "XGY", (0, -1, 1))
    assert doc.map_position(1) == 0
    assert doc.map_position(2) == 1
    assert doc.map_range(1, 2) == (0, 2)


def test_preprocess_source_returns_identity_for_plain_text():
    doc = preprocess_source(_PROGRAM)
    assert doc.is_identity() is True
    assert doc.normalized_text == _PROGRAM


def test_preprocess_source_decodes_compressed_text_and_roundtrips():
    doc = preprocess_source(_COMPRESSED)
    assert doc.is_identity() is False
    assert doc.normalized_text == _PROGRAM
    assert len(doc._char_map) == len(doc.normalized_text)  # type: ignore[attr-defined]


def test_decode_compressed_marks_unknown_marker_as_error_not_space():
    from sattline_parser.preprocessing.compressed import PreprocessError  # noqa: PLC0415

    with pytest.raises(PreprocessError, match=r"Unknown compressed marker '#XX'"):
        preprocess_source("#XX")


def test_decode_compressed_never_rewrites_string_content():
    from sattline_parser.preprocessing.compressed import PreprocessError  # noqa: PLC0415

    # Syntax-looking text inside strings/comments must survive untouched.
    source = _PROGRAM.replace('"SyntaxVersion"', '"ENDDEF; := TrueVar #71 duration := 5s"')
    source = source.replace("(*BasePicture*)", "(* ENDDEF; := TrueVar #71 duration := 5s *)")
    doc = preprocess_source(_compress(source))
    assert '"ENDDEF; := TrueVar #71 duration := 5s"' in doc.normalized_text
    assert "(* ENDDEF; := TrueVar #71 duration := 5s *)" in doc.normalized_text
    # The markers inside opaque regions must not have been decoded.
    assert "#71" in doc.normalized_text
    # No unknown marker error may surface for markers inside strings/comments.
    with pytest.raises(PreprocessError):
        preprocess_source(_compress(source) + " #XX")  # a REAL unknown marker outside regions still errors


def test_decode_compressed_protects_nested_comments_and_escaped_quotes():
    source = (
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "(* outer (* nested #71 ENDDEF; *) comment *)\n"
        "LOCALVARIABLES\n"
        '    S: string := "a ""quoted"" ENDDEF; #71";\n'
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ENDDEF (*BasePicture*);\n"
    )
    doc = preprocess_source(_compress(source))
    assert "(* outer (* nested #71 ENDDEF; *) comment *)" in doc.normalized_text
    assert '"a ""quoted"" ENDDEF; #71"' in doc.normalized_text


def test_decode_compressed_only_rewrites_date_timestamps_after_arrow():
    # "=>" followed by a NON-timestamp string must not be rewritten to Time_Value.
    source = _PROGRAM.replace("Counter = Counter + 1;", 'P => "not-a-timestamp";')
    compressed = _compress(source)
    doc = preprocess_source(compressed)
    assert "=> Time_Value" not in doc.normalized_text
    assert 'P => "not-a-timestamp";' in doc.normalized_text


def test_decode_compressed_rewrites_duration_and_time_assignments_only_in_code():
    source = _PROGRAM.replace(
        "Counter: integer := 0;",
        'Counter: integer := 0;\n    T: duration := "5s";\n    T2: time := "6s";',
    )
    source = source.replace('"SyntaxVersion"', '"duration := 5s"')
    doc = preprocess_source(_compress(source))
    assert 'Duration_Value "5s"' in doc.normalized_text
    assert 'Time_Value "6s"' in doc.normalized_text
    assert '"duration := 5s"' in doc.normalized_text  # inside string: untouched


def test_parse_compressed_source_spans_slice_original_source():
    bp = parser_core_parse_source_text(_COMPRESSED)
    assignment = bp.modulecode.equations[0].code[0]
    assert isinstance(assignment, Assignment)
    assert assignment.span is not None
    slice_text = _COMPRESSED[assignment.span.start : assignment.span.end]
    # "=" is stored as the "#8?" marker in the original compressed text.
    assert slice_text.replace("#8?", "=") == "Counter = Counter + 1"
    assert _COMPRESSED[assignment.target.span.start : assignment.target.span.end] == "Counter"
    assert _COMPRESSED[bp.localvariables[0].declaration_span.start : bp.localvariables[0].declaration_span.end] == (
        "Counter"
    )


def test_parse_plain_source_spans_slice_original_source():
    bp = parser_core_parse_source_text(_PROGRAM)
    assignment = bp.modulecode.equations[0].code[0]
    assert isinstance(assignment, Assignment)
    assert assignment.span is not None
    assert _PROGRAM[assignment.span.start : assignment.span.end] == "Counter = Counter + 1"
    assert _PROGRAM[assignment.target.span.start : assignment.target.span.end] == "Counter"


def test_parse_compressed_source_multiline_construct_spans_slice_original():
    # A multi-line structural comment must slice the ORIGINAL source exactly.
    source = _PROGRAM.replace(
        "EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n        Counter = Counter + 1;",
        "EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
        "        (* first line\n           second line *)\n"
        "        Counter = Counter + 1;",
    )
    compressed = _compress(source)
    bp = parser_core_parse_source_text(compressed)
    assert bp.modulecode is not None
    equation = bp.modulecode.equations[0]
    comment = next(item for item in equation.code if isinstance(item, CodeComment))
    assert comment.span is not None
    assert compressed[comment.span.start : comment.span.end] == "(* first line\n           second line *)"
    assignment = equation.code[1]
    assert isinstance(assignment, Assignment)
    assert compressed[assignment.span.start : assignment.span.end].replace("#8?", "=") == "Counter = Counter + 1"


def test_parse_compressed_source_error_maps_to_original_source():
    bad = _COMPRESSED + " THIS IS GARBAGE !!!"
    with pytest.raises(UnexpectedInput) as exc_info:
        parser_core_parse_source_text(bad)
    exc = exc_info.value
    assert getattr(exc, "_sattline_remapped", False) is True
    original_lines = bad.splitlines()
    assert exc.line == len(original_lines)
    assert exc.column is not None
    details = parser_api.describe_parse_error(exc, bad)
    assert details.line == len(original_lines)
    assert original_lines[details.line - 1] == " THIS IS GARBAGE !!!"


def test_parse_compressed_source_unknown_marker_raises_clear_error():
    from sattline_parser.preprocessing.compressed import PreprocessError  # noqa: PLC0415

    with pytest.raises(PreprocessError, match="Unknown compressed marker"):
        parser_core_parse_source_text(_COMPRESSED.replace("#85", "#ZZ"))


def test_parse_source_file_and_parse_source_text_have_consistent_provenance(tmp_path: Path):
    file_path = tmp_path / "Compressed.s"
    file_path.write_text(_COMPRESSED, encoding="utf-8")
    from_file = parse_source_file(file_path)
    from_text = parser_core_parse_source_text(_COMPRESSED)
    assert from_file.modulecode.equations[0].code[0].span == from_text.modulecode.equations[0].code[0].span
    # No double-decode: spans still point into the original compressed file text.
    raw = file_path.read_text(encoding="utf-8")
    assignment = from_file.modulecode.equations[0].code[0]
    assert raw[assignment.span.start : assignment.span.end].replace("#8?", "=") == "Counter = Counter + 1"


def test_describe_parse_error_maps_untagged_exception_with_source_document():
    bad = _COMPRESSED + " THIS IS GARBAGE !!!"
    source_doc = preprocess_source(bad)
    raw_parser = create_sl_parser()
    try:
        raw_parser.parse(source_doc.normalized_text)
    except UnexpectedInput as exc:
        # Raw exception carries normalized coordinates and is not tagged.
        assert getattr(exc, "_sattline_remapped", False) is False
        details = parser_api.describe_parse_error(exc, bad, source_document=source_doc)
        assert details.line == len(bad.splitlines())
        assert bad.splitlines()[details.line - 1] == " THIS IS GARBAGE !!!"
    else:
        pytest.fail("expected a parse error")


def test_parse_compressed_source_deleted_text_provenance():
    # "ENDDEF;" with trailing semicolon is normalized to "ENDDEF"; the AST
    # end-comment span must still slice the ORIGINAL text.
    source = _PROGRAM.replace("ENDDEF (*BasePicture*);", "ENDDEF; (*BasePicture*);")
    compressed = _compress(source)
    doc = preprocess_source(compressed)
    assert "ENDDEF; (*BasePicture*);" in source
    assert doc.normalized_text.endswith("ENDDEF (*BasePicture*);\n")
    bp = parser_core_parse_source_text(compressed)
    assert [c.text for c in bp.trailing_comments] == ["(*BasePicture*)"]
    comment = bp.trailing_comments[0]
    assert compressed[comment.span.start : comment.span.end] == "(*BasePicture*)"


def test_parse_compressed_source_inserted_modulecode_provenance():
    # EQUATIONBLOCK with no preceding ModuleCode gets one injected; the
    # equation span must still anchor on the real EQUATIONBLOCK text.
    source = _PROGRAM.replace("ModuleCode\n    EQUATIONBLOCK", "EQUATIONBLOCK")
    compressed = _compress(source)
    doc = preprocess_source(compressed)
    assert "ModuleCode" in doc.normalized_text
    bp = parser_core_parse_source_text(compressed)
    equation = bp.modulecode.equations[0]
    assignment = equation.code[0]
    assert isinstance(assignment, Assignment)
    assert assignment.span is not None
    block_slice = compressed[assignment.span.start : assignment.span.end]
    assert "Counter" in block_slice
    assert assignment.span.start < assignment.span.end


def test_describe_parse_error_with_source_document_but_no_offset():
    class FakeUnexpectedInput(UnexpectedEOF):
        def __init__(self) -> None:
            pass

        line = 3
        column = 5
        pos_in_stream = None

        def __str__(self) -> LiteralString:
            return "Unexpected end of input"

    details = parser_api.describe_parse_error(
        FakeUnexpectedInput(),
        _PROGRAM,
        source_document=SourceDocument.identity(_PROGRAM),
    )
    assert details.line == 3
    assert details.column == 5


def test_concurrent_parses_with_nested_comments_do_not_interfere():
    """Regression: the cached parser's lexer is shared across parses.

    Comment depth is per-parse state; concurrent parses of nested-comment
    sources must not corrupt each other.
    """
    import threading  # noqa: PLC0415

    source = _PROGRAM.replace(
        "Counter = Counter + 1;",
        "Counter = Counter + 1;\n"
        "        (* outer (* level 2 (* level 3 *) level 2 *) trailing *)\n"
        "        Counter = Counter * 2;",
    )
    results: list[BasePicture] = []
    errors: list[Exception] = []

    def _worker(barrier: threading.Barrier) -> None:
        barrier.wait()
        for _ in range(20):
            try:
                results.append(parser_core_parse_source_text(source))
            except Exception as exc:  # noqa: BLE001, pragma: no cover - failure path
                errors.append(exc)

    thread_count = 8
    barrier = threading.Barrier(thread_count)
    threads = [threading.Thread(target=_worker, args=(barrier,)) for _ in range(thread_count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(results) == thread_count * 20
    for bp in results:
        assert bp.modulecode is not None
        assert bp.modulecode.equations is not None
        equation = bp.modulecode.equations[0]
        comments = [item for item in equation.code if isinstance(item, CodeComment)]
        assert any("level 3" in c.text for c in comments)


def test_remap_tree_to_original_is_noop_for_identity_documents():
    from sattline_parser.source_document import remap_tree_to_original  # noqa: PLC0415

    tree = parser_core_parse_source_text(_PROGRAM).parse_tree
    assert tree is not None
    first = tree.children[0]
    before = first.meta.start_pos
    remap_tree_to_original(tree, SourceDocument.identity(_PROGRAM))
    assert first.meta.start_pos == before
