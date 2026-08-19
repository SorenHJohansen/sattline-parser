# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportCallIssue=false, reportUnknownLambdaType=false, reportUnusedImport=false
# ruff: noqa: F403, F405
from sattline_parser.models.ast_model import CodeItem

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
    assert mixin.seqalternative([Token("ALT", "ALT"), body_tree, mixin.sequence_body([SFCBreak()])]) == SFCAlternative(
        branches=[[init_step, transition], [SFCBreak()]]
    )
    assert mixin.seqparallel(
        [Token("PAR", "PAR"), body_tree, mixin.sequence_body([SFCFork(targets=("Other",))])]
    ) == SFCParallel(branches=[[init_step, transition], [SFCFork(targets=("Other",))]])
    assert mixin.seqfork([Token("SEQFORK", "SEQFORK"), "NextStep"]) == SFCFork(targets=("NextStep",))
    assert mixin.seqfork([Token("SEQFORK", "SEQFORK"), "PathA", "PathB"]) == SFCFork(targets=("PathA", "PathB"))
    assert isinstance(mixin.seqbreak([]), SFCBreak)
    assert mixin.seq_element([step]) is step
    with pytest.raises(ValueError, match="seq_element expected"):
        mixin.seq_element([])

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

    enter = mixin.entercode([Token("ENTERCODE", "ENTERCODE"), Tree(parser_const.KEY_STATEMENT, ["enter_stmt"])])
    active = mixin.activecode([Token("ACTIVECODE", "ACTIVECODE"), Tree(parser_const.KEY_STATEMENT, ["active_stmt"])])
    exit_ = mixin.exitcode([Token("EXITCODE", "EXITCODE"), Tree(parser_const.KEY_STATEMENT, ["exit_stmt"])])

    code_blocks = mixin.code_blocks([enter, active, exit_])

    assert enter == CodeBlockPayload(
        kind="enter", items=cast(tuple[CodeItem, ...], (Tree(parser_const.KEY_STATEMENT, ["enter_stmt"]),))
    )
    assert active == CodeBlockPayload(
        kind="active", items=cast(tuple[CodeItem, ...], (Tree(parser_const.KEY_STATEMENT, ["active_stmt"]),))
    )
    assert exit_ == CodeBlockPayload(
        kind="exit", items=cast(tuple[CodeItem, ...], (Tree(parser_const.KEY_STATEMENT, ["exit_stmt"]),))
    )
    assert code_blocks == SFCCodeBlocks(
        enter=cast(list[CodeItem], [Tree(parser_const.KEY_STATEMENT, ["enter_stmt"])]),
        active=cast(list[CodeItem], [Tree(parser_const.KEY_STATEMENT, ["active_stmt"])]),
        exit=cast(list[CodeItem], [Tree(parser_const.KEY_STATEMENT, ["exit_stmt"])]),
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

    with pytest.raises(ValueError, match="seqinitstep expected"):
        mixin.seqinitstep([Token("SEQINITSTEP", "SEQINITSTEP"), "Init"])
    with pytest.raises(ValueError, match="seqinitstep expected"):
        mixin.seqinitstep([Token("SEQINITSTEP", "SEQINITSTEP")])
    with pytest.raises(ValueError, match="seqinitstep expected"):
        mixin.seqinitstep([Token("SEQINITSTEP", "SEQINITSTEP"), "Init", "not-code-blocks"])
    with pytest.raises(ValueError, match="seqinitstep expected"):
        mixin.seqinitstep([Token("SEQINITSTEP", "SEQINITSTEP"), "not-code-blocks"])
    with pytest.raises(ValueError, match="seqstep expected"):
        mixin.seqstep([Token("SEQSTEP", "SEQSTEP"), "Step", "not-code-blocks"])
    with pytest.raises(ValueError, match="seqstep expected"):
        mixin.seqstep([Token("SEQSTEP", "SEQSTEP")])
    with pytest.raises(ValueError, match="seqstep expected"):
        mixin.seqstep([Token("SEQSTEP", "SEQSTEP"), "not-code-blocks"])
    with pytest.raises(ValueError, match="seqtransition expected WAIT_FOR"):
        mixin.seqtransition([Token("SEQTRANSITION", "SEQTRANSITION"), "Gate", Token("NAME", "NAME"), True])
    with pytest.raises(ValueError, match="seqtransition expected WAIT_FOR"):
        mixin.seqtransition([Token("SEQTRANSITION", "SEQTRANSITION"), Token("NAME", "NAME"), True])
    with pytest.raises(ValueError, match=r"seqtransition expected \(SEQTRANSITION"):
        mixin.seqtransition([Token("SEQTRANSITION", "SEQTRANSITION")])
    with pytest.raises(ValueError, match="seqtransition expected an expression after WAIT_FOR"):
        mixin.seqtransition([Token("SEQTRANSITION", "SEQTRANSITION"), Token("WAIT_FOR", "WAIT_FOR")])
    with pytest.raises(ValueError, match="seqtransitionsub expected"):
        mixin.seqtransitionsub(
            [Token("SUBSEQTRANSITION", "SUBSEQTRANSITION"), "Sub", Tree("wrong", []), Token("END", "END")]
        )
    with pytest.raises(ValueError, match="seqsub expected"):
        mixin.seqsub([Token("SUBSEQUENCE", "SUBSEQUENCE"), "Sub", Tree("wrong", []), Token("END", "END")])
    with pytest.raises(ValueError, match="seqfork expected"):
        mixin.seqfork([Token("SEQFORK", "SEQFORK")])
    with pytest.raises(ValueError, match="Position can't be None"):
        mixin.sequence([Token(parser_const.GRAMMAR_VALUE_SEQUENCE, parser_const.GRAMMAR_VALUE_SEQUENCE), "Seq"])
    with pytest.raises(ValueError, match="Size can't be None"):
        mixin.sequence([Token(parser_const.GRAMMAR_VALUE_SEQUENCE, parser_const.GRAMMAR_VALUE_SEQUENCE), "Seq", (1, 2)])
    with pytest.raises(ValueError, match="equationblock unexpected code item"):
        mixin.equationblock([(1, 2), (3, 4), Tree(parser_const.KEY_STATEMENT, ["stmt"])])
    with pytest.raises(ValueError, match="Name can't be None"):
        mixin.equationblock([(1, 2), (3, 4)])
    with pytest.raises(ValueError, match="Position can't be None"):
        mixin.equationblock(["EqA"])
    with pytest.raises(ValueError, match="Size can't be None"):
        mixin.equationblock(["EqA", (1, 2)])


def test_sfc_mixin_fails_loudly_on_unexpected_modulecode_and_branch_structures():
    mixin = _SFCHarness()

    with pytest.raises(ValueError, match="modulecode expected Sequence/Equation/CodeComment"):
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
