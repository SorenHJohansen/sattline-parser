# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportCallIssue=false, reportUnknownLambdaType=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from sattline_parser.models.ast_model import CodeItem, SFCLoop
from sattline_parser.models.expressions import VarRef
from sattline_parser.validation import validate_basepicture

from ._parser_core_test_support import *


def test_sfc_mixin_builds_modulecode_sequences_and_equations():
    mixin = _SFCHarness()
    code_blocks = mixin.code_blocks(
        [
            CodeBlockPayload(kind="enter", items=cast(tuple[CodeItem, ...], ("enter1",))),
            CodeBlockPayload(kind="active", items=cast(tuple[CodeItem, ...], ("active1",))),
            CodeBlockPayload(kind="exit", items=cast(tuple[CodeItem, ...], ("exit1",))),
        ]
    )
    init_step = mixin.seqinitstep([Token("SEQINITSTEP", "SEQINITSTEP"), "Init", code_blocks])
    anonymous_init_step = mixin.seqinitstep([Token("SEQINITSTEP", "SEQINITSTEP"), code_blocks])
    step = mixin.seqstep([Token("SEQSTEP", "SEQSTEP"), "Run", code_blocks])
    anonymous_step = mixin.seqstep([Token("SEQSTEP", "SEQSTEP"), code_blocks])
    transition = mixin.seqtransition(
        [Token("SEQTRANSITION", "SEQTRANSITION"), "Gate", Token("WAIT_FOR", "WAIT_FOR"), True]
    )
    anonymous_transition = mixin.seqtransition(
        [Token("SEQTRANSITION", "SEQTRANSITION"), Token("WAIT_FOR", "WAIT_FOR"), False]
    )
    body_tree = mixin.sequence_body([init_step, transition])

    assert code_blocks == SFCCodeBlocks(
        enter=cast(list[CodeItem], ["enter1"]),
        active=cast(list[CodeItem], ["active1"]),
        exit=cast(list[CodeItem], ["exit1"]),
    )
    assert init_step == SFCStep(kind="init", name="Init", code=code_blocks)
    assert anonymous_init_step == SFCStep(kind="init", name=None, code=code_blocks)
    assert step == SFCStep(kind="step", name="Run", code=code_blocks)
    assert anonymous_step == SFCStep(kind="step", name=None, code=code_blocks)
    assert transition == SFCTransition(name="Gate", condition=True)
    assert anonymous_transition == SFCTransition(name=None, condition=False)
    assert mixin.seqtransitionsub(
        [Token("SUBSEQTRANSITION", "SUBSEQTRANSITION"), "SubGate", body_tree, Token("ENDSUBSEQTRANSITION", "END")]
    ) == SFCTransitionSub(name="SubGate", body=[init_step, transition])
    assert mixin.seqsub(
        [Token("SUBSEQUENCE", "SUBSEQUENCE"), "SubA", body_tree, Token("ENDSUBSEQUENCE", "END")]
    ) == SFCSubsequence(
        name="SubA",
        body=[init_step, transition],
    )
    other_step = SFCStep(kind="step", name="Other", code=SFCCodeBlocks())
    assert mixin.seqalternative([Token("ALT", "ALT"), body_tree, mixin.sequence_body([other_step])]) == SFCAlternative(
        branches=[[init_step, transition], [other_step]]
    )
    assert mixin.seqparallel([Token("PAR", "PAR"), body_tree, mixin.sequence_body([other_step])]) == SFCParallel(
        branches=[[init_step, transition], [other_step]]
    )
    assert mixin.seqfork([Token("SEQFORK", "SEQFORK"), "NextStep"]) == SFCFork(targets=("NextStep",))
    assert mixin.seqfork([Token("SEQFORK", "SEQFORK"), "PathA", "PathB"]) == SFCFork(targets=("PathA", "PathB"))
    assert mixin.seqfork([Token("SEQFORK", "SEQFORK"), "PathA", Token("SEQBREAK", "SEQBREAK")]) == SFCFork(
        targets=("PathA",), has_break=True
    )
    assert mixin.seq_element(Meta(), [step]) is step
    assert step.span is None
    spanned = mixin.seq_element(
        SimpleNamespace(line=3, column=4, start_pos=10, end_pos=20, end_line=3, end_column=14), [step]
    )
    assert spanned is step
    assert step.span == SourceSpan(start=10, end=20, line=3, column=4)
    with pytest.raises(ValueError, match="seq_element expected"):
        mixin.seq_element(Meta(), [Token("SEQSTEP", "SEQSTEP")])

    seqcontrol_tree = Tree(
        parser_const.KEY_SEQ_CONTROL_OPS,
        [
            Token("FLAG", parser_const.GRAMMAR_VALUE_SEQCONTROL),
            Token("FLAG", parser_const.GRAMMAR_VALUE_SEQTIMER),
        ],
    )
    sequence = mixin.sequence(
        [
            Token(parser_const.GRAMMAR_VALUE_OPENSEQUENCE, parser_const.GRAMMAR_VALUE_OPENSEQUENCE),
            "MainSeq",
            (1, 2),
            (3, 4),
            seqcontrol_tree,
            body_tree,
        ]
    )
    anonymous_sequence = mixin.sequence(
        [
            Token(parser_const.GRAMMAR_VALUE_SEQUENCE, parser_const.GRAMMAR_VALUE_SEQUENCE),
            (1, 2),
            (3, 4),
            body_tree,
        ]
    )
    equation = mixin.equationblock(["EqA", (5, 6), (7, 8), Assignment(VarRef("X"), IntLiteral(1))])
    tokenized_equation = mixin.equationblock(
        [
            Token(parser_const.GRAMMAR_VALUE_EQUATIONBLOCK, parser_const.GRAMMAR_VALUE_EQUATIONBLOCK),
            "EqToken",
            (6, 7),
            (8, 9),
            Assignment(VarRef("Y"), IntLiteral(2)),
        ]
    )
    nested_sequence = Sequence(name="Nested", type="SEQUENCE", position=(0, 0), size=(1, 1), code=[])
    nested_equation = Equation(name="EqNested", position=(9, 10), size=(11, 12), code=[])
    modulecode = mixin.modulecode([sequence, equation, nested_sequence, nested_equation])

    assert sequence == Sequence(
        name="MainSeq",
        type=parser_const.GRAMMAR_VALUE_OPENSEQUENCE,
        position=(1.0, 2.0),
        size=(3.0, 4.0),
        seqcontrol=True,
        seqtimer=True,
        code=[init_step, transition],
    )
    assert anonymous_sequence == Sequence(
        name=None,
        type=parser_const.GRAMMAR_VALUE_SEQUENCE,
        position=(1.0, 2.0),
        size=(3.0, 4.0),
        code=[init_step, transition],
    )
    assert equation == Equation(
        name="EqA",
        position=(5.0, 6.0),
        size=(7.0, 8.0),
        code=[Assignment(VarRef("X"), IntLiteral(1))],
    )
    assert tokenized_equation == Equation(
        name="EqToken",
        position=(6.0, 7.0),
        size=(8.0, 9.0),
        code=[Assignment(VarRef("Y"), IntLiteral(2))],
    )
    assert modulecode.sequences == [sequence, nested_sequence]
    assert modulecode.equations == [equation, nested_equation]


def test_sfc_mixin_normalizes_enter_active_exit_code_blocks():
    mixin = _SFCHarness()

    enter_item = FuncCallStmt(call=FuncCall(name="enter_fn", args=()))
    active_item = FuncCallStmt(call=FuncCall(name="active_fn", args=()))
    exit_item = FuncCallStmt(call=FuncCall(name="exit_fn", args=()))

    enter = mixin.entercode([Token("ENTERCODE", "ENTERCODE"), enter_item])
    active = mixin.activecode([Token("ACTIVECODE", "ACTIVECODE"), active_item])
    exit_ = mixin.exitcode([Token("EXITCODE", "EXITCODE"), exit_item])

    code_blocks = mixin.code_blocks([enter, active, exit_])

    assert enter == CodeBlockPayload(kind="enter", items=(enter_item,))
    assert active == CodeBlockPayload(kind="active", items=(active_item,))
    assert exit_ == CodeBlockPayload(kind="exit", items=(exit_item,))
    assert code_blocks == SFCCodeBlocks(
        enter=[enter_item],
        active=[active_item],
        exit=[exit_item],
    )


def test_parse_source_text_preserves_sfc_step_code_blocks():
    bp = _parse_to_basepicture(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        "   Flag: boolean := False;\n"
        "   Counter: integer := 0;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "SEQUENCE Main (SeqControl) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
        "   SEQINITSTEP Init\n"
        "   SEQTRANSITION Tr1 WAIT_FOR True\n"
        "   SEQSTEP Run\n"
        "      ENTERCODE\n"
        "         Flag = True;\n"
        "      ACTIVECODE\n"
        "         Counter = 1;\n"
        "      EXITCODE\n"
        "         Counter = 0;\n"
        "   SEQTRANSITION Done WAIT_FOR False\n"
        "ENDSEQUENCE\n"
        "ENDDEF (*BasePicture*);\n"
    )

    sequence = bp.modulecode.sequences[0]
    run_step = next(node for node in sequence.code if isinstance(node, SFCStep) and node.name == "Run")

    assert len(run_step.code.enter) == 1
    assert len(run_step.code.active) == 1
    assert len(run_step.code.exit) == 1
    enter_stmt = run_step.code.enter[0]
    active_stmt = run_step.code.active[0]
    exit_stmt = run_step.code.exit[0]

    assert isinstance(enter_stmt, Assignment)
    assert isinstance(active_stmt, Assignment)
    assert isinstance(exit_stmt, Assignment)
    assert enter_stmt.target == VarRef("Flag", span=SourceSpan(start=415, end=419, line=16, column=10))
    assert enter_stmt.value is True
    assert enter_stmt.span == SourceSpan(start=415, end=426, line=16, column=10)
    assert active_stmt.target == VarRef("Counter", span=SourceSpan(start=454, end=461, line=18, column=10))
    assert active_stmt.value == 1
    assert active_stmt.span == SourceSpan(start=454, end=465, line=18, column=10)
    assert exit_stmt.target == VarRef("Counter", span=SourceSpan(start=491, end=498, line=20, column=10))
    assert exit_stmt.value == 0
    assert exit_stmt.span == SourceSpan(start=491, end=502, line=20, column=10)


def test_parse_source_text_models_the_loop_construct():
    """`FreeWord1 [NAME] C FreeWord2 [expr] [C] FreeWord3`."""
    bp = _parse_to_basepicture(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "SEQUENCE Main (SeqControl) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
        "   FreeWord1 MyLoop\n"
        "      SEQINITSTEP Init\n"
        "      SEQTRANSITION Tr WAIT_FOR True\n"
        "   FreeWord2 Flag\n"
        "      SEQSTEP Run\n"
        "      SEQTRANSITION Tr2 WAIT_FOR True\n"
        "   FreeWord3\n"
        "   SEQINITSTEP Second\n"
        "   SEQTRANSITION Tr3 WAIT_FOR True\n"
        "ENDSEQUENCE\n"
        "ENDDEF (*BasePicture*);\n"
    )

    assert bp.modulecode is not None
    loop = bp.modulecode.sequences[0].code[0]
    assert isinstance(loop, SFCLoop)
    assert loop.name == "MyLoop"
    assert loop.condition == VarRef("Flag", span=loop.condition.span)  # type: ignore[union-attr]
    assert [type(node).__name__ for node in loop.body] == ["SFCStep", "SFCTransition"]
    assert loop.else_body is not None
    assert [type(node).__name__ for node in loop.else_body] == ["SFCStep", "SFCTransition"]


def test_parse_source_text_accepts_a_bare_loop():
    bp = _parse_to_basepicture(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "SEQUENCE Main (SeqControl) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
        "   FreeWord1\n"
        "      SEQINITSTEP Init\n"
        "      SEQTRANSITION Tr WAIT_FOR True\n"
        "   FreeWord2\n"
        "   FreeWord3\n"
        "   SEQINITSTEP Second\n"
        "   SEQTRANSITION Tr2 WAIT_FOR True\n"
        "ENDSEQUENCE\n"
        "ENDDEF (*BasePicture*);\n"
    )

    assert bp.modulecode is not None
    loop = bp.modulecode.sequences[0].code[0]
    assert isinstance(loop, SFCLoop)
    assert (loop.name, loop.condition, loop.else_body) == (None, None, None)


def test_loop_transformer_rejects_malformed_items():
    mixin = _SFCHarness()
    body_tree = mixin.sequence_body([mixin.seqstep([Token("SEQSTEP", "SEQSTEP"), "Run", mixin.code_blocks([])])])

    with pytest.raises(ValueError, match="expected sequence_body Trees"):
        mixin.loop([Token("FREEWORD1", "FreeWord1"), Tree("other", [])])
    with pytest.raises(ValueError, match="loop unexpected item"):
        mixin.loop([Token("FREEWORD1", "FreeWord1"), body_tree, "name", "cond", "extra"])
    with pytest.raises(ValueError, match="at least one sequence_body"):
        mixin.loop([Token("FREEWORD1", "FreeWord1"), Token("FREEWORD3", "FreeWord3")])


def test_loop_condition_and_else_body_are_walked_and_positioned():
    """The loop condition is an expression and both bodies are closed bodies."""
    bp = _parse_to_basepicture(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "LOCALVARIABLES\n"
        "   Sink: integer := 0;\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "SEQUENCE Main (SeqControl) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
        "   FreeWord1\n"
        "      SEQINITSTEP Init\n"
        "      SEQTRANSITION Tr WAIT_FOR True\n"
        "   FreeWord2 MissingGuard\n"
        "      SEQSTEP ElseStep\n"
        "   FreeWord3\n"
        "   SEQINITSTEP Second\n"
        "   SEQTRANSITION Tr2 WAIT_FOR True\n"
        "ENDSEQUENCE\n"
        "ENDDEF (*BasePicture*);\n"
    )

    diagnostics = validate_basepicture(bp)

    # The guard is walked as an expression, and the else body is position-checked
    # (it ends on a step, which a closed body may not).
    assert any("MissingGuard" in diagnostic.message for diagnostic in diagnostics)
    assert any(str(diagnostic.code) == "SL-V033" for diagnostic in diagnostics)


def test_loop_body_positions_are_validated_like_a_sequence():
    """A loop body is the closed `(S T | M)+` shape, so it must not end on a step."""
    bp = _parse_to_basepicture(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "SEQUENCE Main (SeqControl) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
        "   FreeWord1\n"
        "      SEQSTEP Lonely\n"
        "   FreeWord2\n"
        "   FreeWord3\n"
        "   SEQINITSTEP Second\n"
        "   SEQTRANSITION Tr WAIT_FOR True\n"
        "ENDSEQUENCE\n"
        "ENDDEF (*BasePicture*);\n"
    )

    codes = {str(diagnostic.code) for diagnostic in validate_basepicture(bp)}
    # SEQUENCE_ENDS_WITH_STEP: the loop body is checked as a closed body.
    assert "SL-V033" in codes


def test_equationblock_records_which_keyword_was_written():
    """EQUATIONBLOCK and EQUATIONS are both accepted, with different flags."""
    for keyword, expected in (("EQUATIONBLOCK", "equationblock"), ("EQUATIONS", "equations")):
        bp = _parse_to_basepicture(
            '"SyntaxVersion"\n'
            '"OriginalFileDate"\n'
            '"ProgramDate"\n'
            "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
            "ModuleDef\n"
            "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
            "ModuleCode\n"
            f"{keyword} Calc COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :\n"
            "   Flag = True;\n"
            "ENDDEF (*BasePicture*);\n"
        )

        assert bp.modulecode is not None
        assert bp.modulecode.equations[0].kind == expected


def test_parse_source_text_accepts_unnamed_ordinary_step():
    # Regression: real SattLine accepts ordinary SEQSTEP blocks without a name
    # (verified against the actual parser); the grammar previously required a
    # NAME after SEQSTEP, so this input failed to lex/parse.
    bp = _parse_to_basepicture(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "SEQUENCE Main (SeqControl) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0\n"
        "   SEQINITSTEP Init\n"
        "   SEQTRANSITION Tr1 WAIT_FOR True\n"
        "   SEQSTEP\n"
        "      ENTERCODE\n"
        "         Flag = True;\n"
        "   SEQTRANSITION Tr2 WAIT_FOR True\n"
        "   SEQSTEP\n"
        "   SEQTRANSITION Tr3 WAIT_FOR False\n"
        "ENDSEQUENCE\n"
        "ENDDEF (*BasePicture*);\n"
    )

    sequence = bp.modulecode.sequences[0]
    steps = [node for node in sequence.code if isinstance(node, SFCStep) and node.kind == "step"]
    assert len(steps) == 2
    assert all(step.name is None for step in steps)
    assert len(steps[0].code.enter) == 1
    assert steps[1].code.enter == []


def test_sequence_and_equation_layer_info_is_accepted_but_not_modeled():
    # Layer_ directives after SEQUENCE/OPENSEQUENCE head and EQUATIONBLOCK head
    # are legal SattLine; the AST has no layer field on these nodes, so the
    # value is explicitly ignored (never silently misinterpreted as a code
    # item or coordinate).
    bp = _parse_to_basepicture(
        '"SyntaxVersion"\n'
        '"OriginalFileDate"\n'
        '"ProgramDate"\n'
        "BasePicture Invocation (0.0,0.0,0.0,1.0,1.0) : MODULEDEFINITION DateCode_ 1\n"
        "ModuleDef\n"
        "ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )\n"
        "ModuleCode\n"
        "SEQUENCE Main (SeqControl) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 Layer_ = 2\n"
        "   SEQINITSTEP Init\n"
        "   SEQTRANSITION TrGo WAIT_FOR True\n"
        "ENDSEQUENCE\n"
        "EQUATIONBLOCK Calc COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 Layer_ = 2 :\n"
        "   Flag = True;\n"
        "ENDDEF (*BasePicture*);\n"
    )
    assert bp.modulecode is not None
    assert bp.modulecode.sequences is not None
    assert [type(node).__name__ for node in bp.modulecode.sequences[0].code] == ["SFCStep", "SFCTransition"]
    assert bp.modulecode.equations is not None
    equation = bp.modulecode.equations[0]
    assert equation.name == "Calc"
    assert len(equation.code) == 1
    assert isinstance(equation.code[0], Assignment)


def test_sfc_mixin_rejects_malformed_shapes_and_missing_required_fields():
    mixin = _SFCHarness()

    with pytest.raises(ValueError, match="seqinitstep expected code_blocks"):
        mixin.seqinitstep([Token("SEQINITSTEP", "SEQINITSTEP"), "Init"])
    with pytest.raises(ValueError, match="seqinitstep expected code_blocks"):
        mixin.seqinitstep([Token("SEQINITSTEP", "SEQINITSTEP")])
    with pytest.raises(ValueError, match="seqinitstep unexpected item shape"):
        mixin.seqinitstep([Token("SEQINITSTEP", "SEQINITSTEP"), "Init", "not-code-blocks"])
    with pytest.raises(ValueError, match="seqstep unexpected item shape"):
        mixin.seqstep([Token("SEQSTEP", "SEQSTEP"), "Step", "not-code-blocks"])
    with pytest.raises(ValueError, match="seqstep expected code_blocks"):
        mixin.seqstep([Token("SEQSTEP", "SEQSTEP")])
    with pytest.raises(ValueError, match="seqtransition unexpected item"):
        mixin.seqtransition([Token("SEQTRANSITION", "SEQTRANSITION"), 1.5])
    with pytest.raises(ValueError, match="seqtransition expected an expression after WAIT_FOR"):
        mixin.seqtransition(
            [Token("SEQTRANSITION", "SEQTRANSITION"), Token("WAIT_FOR", "WAIT_FOR"), Token("WAIT_FOR", "WAIT_FOR")]
        )
    with pytest.raises(ValueError, match="seqtransition expected an expression after WAIT_FOR"):
        mixin.seqtransition([Token("SEQTRANSITION", "SEQTRANSITION"), Token("WAIT_FOR", "WAIT_FOR")])
    with pytest.raises(ValueError, match="seqtransitionsub expected"):
        mixin.seqtransitionsub(
            [Token("SUBSEQTRANSITION", "SUBSEQTRANSITION"), "Sub", Tree("wrong", []), Token("END", "END")]
        )
    with pytest.raises(ValueError, match="seqsub unexpected item"):
        mixin.seqsub([Token("SUBSEQUENCE", "SUBSEQUENCE"), "Sub", Tree("wrong", []), Token("END", "END")])
    with pytest.raises(ValueError, match="seqsub expected a sequence_body"):
        mixin.seqsub([Token("SUBSEQUENCE", "SUBSEQUENCE"), "Sub"])
    with pytest.raises(ValueError, match="seqfork expected"):
        mixin.seqfork([Token("SEQFORK", "SEQFORK")])
    with pytest.raises(ValueError, match="Position can't be None"):
        mixin.sequence([Token(parser_const.GRAMMAR_VALUE_SEQUENCE, parser_const.GRAMMAR_VALUE_SEQUENCE), "Seq"])
    with pytest.raises(ValueError, match="Size can't be None"):
        mixin.sequence([Token(parser_const.GRAMMAR_VALUE_SEQUENCE, parser_const.GRAMMAR_VALUE_SEQUENCE), "Seq", (1, 2)])
    with pytest.raises(ValueError, match="equationblock unexpected code item"):
        mixin.equationblock([(1, 2), (3, 4), Tree(parser_const.KEY_STATEMENT, ["stmt"])])
    # name, position and size are optional in the reader
    unnamed = mixin.equationblock([(1, 2), (3, 4)])
    assert unnamed.name is None
    assert unnamed.position == (1, 2)
    assert unnamed.size == (3, 4)
    name_only = mixin.equationblock(["EqA"])
    assert name_only.name == "EqA"
    assert name_only.position is None
    assert name_only.size is None


def test_sfc_mixin_fails_loudly_on_unexpected_modulecode_and_branch_structures():
    mixin = _SFCHarness()

    with pytest.raises(ValueError, match="modulecode expected Sequence/Equation"):
        mixin.modulecode([object()])

    with pytest.raises(ValueError, match="seqalternative expected sequence_body Trees; got Tree"):
        mixin.seqalternative([Tree("wrong", [])])
    with pytest.raises(ValueError, match="seqparallel expected sequence_body Trees; got: int"):
        mixin.seqparallel([42])
    with pytest.raises(ValueError, match="seqalternative expected at least two sequence_body branches"):
        mixin.seqalternative([Token("ALT", "ALT")])

    # layer_info in equationblock is explicitly ignored, not an error.
    eq = mixin.equationblock(["EqA", (1, 2), (3, 4), 7, Assignment(VarRef("A"), 1)])
    assert eq.name == "EqA"
