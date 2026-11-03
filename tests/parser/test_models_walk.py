# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""Tests for the public AST walker in ``sattline_parser.models``."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from sattline_parser import NodeVisitor, parse_source_file, walk
from sattline_parser.models import ast_model, expressions, iter_child_nodes
from sattline_parser.models import ast_model as m
from sattline_parser.models.expressions import (
    Assignment,
    BinOp,
    BoolOp,
    Compare,
    FuncCall,
    FuncCallStmt,
    IfStmt,
    NotOp,
    TernaryOp,
    UnaryOp,
    VarRef,
)
from sattline_parser.models.walk import _NODE_TYPES

_CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "corpus" / "valid"


def _picture() -> m.BasePicture:
    return parse_source_file(_CORPUS / "UnCompressedFullGrammar.s")


def test_walk_starts_at_the_root_with_its_relation_and_ancestry() -> None:
    picture = _picture()
    events = list(walk(picture))

    root = events[0]
    assert root.node is picture
    assert root.relation == ""
    assert root.parents == ()

    header = next(event for event in events if event.node is picture.header)
    assert header.relation == "header"
    assert header.parents == (picture,)


def test_walk_reports_nested_relations_and_parents() -> None:
    picture = _picture()
    events = list(walk(picture))

    assignment = next(event.node for event in events if isinstance(event.node, Assignment))
    target_event = next(event for event in events if event.node is assignment.target)
    assert target_event.relation == "target"
    assert target_event.parents[-1] is assignment
    assert picture in target_event.parents


def test_walk_visits_each_node_once_in_pre_order() -> None:
    events = list(walk(_picture()))
    identities = [id(event.node) for event in events]
    positions = {identity: index for index, identity in enumerate(identities)}

    assert len(identities) == len(set(identities))
    for index, event in enumerate(events):
        for parent in event.parents:
            assert positions[id(parent)] < index


def test_walk_covers_every_model_shape() -> None:
    pictures = (_picture(), parse_source_file(_CORPUS / "BuiltinCalls.s"))
    visited = {type(event.node) for picture in pictures for event in walk(picture)}
    visited |= {type(event.node) for event in walk(UnaryOp("-", VarRef("Count")))}

    expected = {
        m.BasePicture,
        m.CodeComment,
        m.DataType,
        m.Equation,
        m.FrameModule,
        m.GraphObject,
        m.InteractObject,
        m.ModuleCode,
        m.ModuleDef,
        m.ModuleHeader,
        m.ModuleTypeDef,
        m.ModuleTypeInstance,
        m.ParameterMapping,
        m.SFCCodeBlocks,
        m.SFCAlternative,
        m.SFCFork,
        m.SFCParallel,
        m.SFCStep,
        m.SFCSubsequence,
        m.SFCTransition,
        m.SFCTransitionSub,
        m.Sequence,
        m.SingleModule,
        m.Variable,
        Assignment,
        BinOp,
        BoolOp,
        Compare,
        FuncCall,
        FuncCallStmt,
        IfStmt,
        NotOp,
        TernaryOp,
        UnaryOp,
        VarRef,
    }
    assert expected <= visited


def test_walk_does_not_emit_literal_leaves() -> None:
    for event in walk(_picture()):
        assert not isinstance(event.node, (bool, int, float, str)), event.node


def test_walk_prunes_after_yielding_the_node() -> None:
    events = list(walk(_picture(), prune=lambda node: isinstance(node, m.Sequence)))

    assert any(isinstance(event.node, m.Sequence) for event in events)
    assert not any(isinstance(event.node, m.SFCStep) for event in events)


def test_walk_accepts_a_sequence_of_nodes() -> None:
    empty = m.Sequence(name="Empty", type="SEQUENCE", position=(0.0, 0.0), size=(1.0, 1.0))
    other = m.Sequence(name="Other", type="SEQUENCE", position=(0.0, 0.0), size=(1.0, 1.0))

    events = list(walk([empty, other]))

    assert [event.relation for event in events] == ["[0]", "[1]"]
    assert [event.node for event in events] == [empty, other]


def test_walk_reports_branch_shapes_for_statements_and_ternaries() -> None:
    condition = VarRef("Flag")
    body = (Assignment(target=VarRef("Count"), value=1),)
    statement = IfStmt(branches=((condition, body),), else_block=None)
    ternary = TernaryOp(branches=((condition, VarRef("A")),), else_expr=VarRef("B"))

    statement_relations = {event.relation for event in walk(statement)}
    ternary_relations = {event.relation for event in walk(ternary)}

    assert "branches[0][0]" in statement_relations
    assert "branches[0][1][0]" in statement_relations
    assert "branches[0][0]" in ternary_relations
    assert "branches[0][1]" in ternary_relations
    assert "else_expr" in ternary_relations


def test_walk_descends_into_header_tails_and_groupconn() -> None:
    header = m.ModuleHeader(
        name="Header",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        invoke_coord_tails=[VarRef("Coord")],
        enable_tail=VarRef("Enabled"),
        groupconn=VarRef("Conn"),
    )

    relations = {event.relation for event in walk(header)}

    assert {"invoke_coord_tails[0]", "enable_tail", "groupconn"} <= relations


def test_walk_orders_header_and_module_type_fields_by_declaration() -> None:
    header = m.ModuleHeader(
        name="Header",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        enable_tail=VarRef("Enabled"),
        invoke_coord_tails=[VarRef("Coord")],
        groupconn=VarRef("Conn"),
    )
    module_type = m.ModuleTypeDef(
        name="Type",
        moduleparameters=[m.Variable(name="P", datatype="integer")],
        localvariables=[m.Variable(name="L", datatype="integer")],
        groupconn=VarRef("Conn"),
    )

    assert [event.relation for event in walk(header)] == [
        "",
        "enable_tail",
        "invoke_coord_tails[0]",
        "groupconn",
    ]
    assert [event.relation for event in walk(module_type)] == [
        "",
        "moduleparameters[0]",
        "localvariables[0]",
        "groupconn",
    ]


def test_walk_reports_a_mapping_target_without_a_source() -> None:
    mapping = m.ParameterMapping(
        target=VarRef("Target"),
        source_type="integer",
        is_duration=False,
        is_source_global=False,
    )

    assert [event.relation for event in walk(mapping)] == ["", "target"]


def test_walk_handles_a_transition_without_a_condition() -> None:
    transition = m.SFCTransition(name="Bare", condition=None)

    assert [event.relation for event in walk(transition)] == [""]


def test_walk_handles_a_ternary_without_an_else() -> None:
    ternary = TernaryOp(branches=((VarRef("C"), VarRef("A")),), else_expr=None)

    relations = {event.relation for event in walk(ternary)}

    assert "branches[0][1]" in relations
    assert "else_expr" not in relations


def test_walk_skips_non_node_items_in_a_sequence() -> None:
    events = list(walk([VarRef("A"), 3]))

    assert [event.node for event in events] == [VarRef("A")]


_NOT_AST_NODE = {ast_model.SourceSpan, ast_model.GraphicsBinding}


def test_every_exported_dataclass_node_is_in_the_walker_registry() -> None:
    exported: list[type[object]] = []
    for module in (ast_model, expressions):
        for name in module.__all__:
            value = getattr(module, name)
            if isinstance(value, type) and dataclasses.is_dataclass(value):
                exported.append(value)

    missing = sorted(cls.__name__ for cls in exported if cls not in _NOT_AST_NODE and cls not in _NODE_TYPES)

    assert missing == []


def test_iter_child_nodes_labels_a_sequence_by_index() -> None:
    picture = _picture()
    children = list(iter_child_nodes(picture.modulecodes))

    assert children
    assert children[0][0] == "[0]"
    assert children[0][1] is picture.modulecodes[0]


def test_iter_child_nodes_skips_non_nodes() -> None:
    picture = _picture()
    relations = {relation for relation, _child in iter_child_nodes(picture)}

    assert "parse_tree" not in relations
    assert "graphics_bindings" not in relations


class _Collector(NodeVisitor):
    def __init__(self) -> None:
        self.variables: list[str] = []
        self.calls: list[str] = []

    def visit_Variable(self, variable: m.Variable) -> None:
        self.variables.append(variable.name)

    def visit_FuncCall(self, call: FuncCall) -> None:
        self.calls.append(call.name)
        self.generic_visit(call)


def test_node_visitor_dispatches_and_descends_on_request() -> None:
    collectors: list[_Collector] = []
    for picture in (_picture(), parse_source_file(_CORPUS / "BuiltinCalls.s")):
        collector = _Collector()
        collector.visit(picture)
        collectors.append(collector)

    assert any(collector.variables for collector in collectors)
    assert any(collector.calls for collector in collectors)
    assert all(isinstance(name, str) for collector in collectors for name in collector.calls)
