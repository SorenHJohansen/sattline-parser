# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownLambdaType=false, reportArgumentType=false, reportPrivateUsage=false, reportUnusedImport=false, reportCallIssue=false
"""Tests for the public AST walker in ``sattline_parser.models``."""

from __future__ import annotations

import dataclasses
from pathlib import Path

from sattline_parser import NodeVisitor, parse_source_file, walk
from sattline_parser.models import ast_model, clauses, expressions, iter_child_nodes, tails
from sattline_parser.models import ast_model as m
from sattline_parser.models.clauses import (
    ColourSpec,
    EnableClause,
    FlagClause,
    TailedClause,
)
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
from sattline_parser.models.properties import GraphProperties, InteractProperties
from sattline_parser.models.tails import LitStringTail, VarTail
from sattline_parser.models.walk import (
    _FIELD_SPECS,
    _GRAPH_PROPERTY_ORDER,
    _INTERACT_PROPERTY_ORDER,
    _NODE_TYPES,
    _unowned_tail_entries,
    iter_literal_leaves,
)

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
        clauses.Alignment,
        clauses.AssignClause,
        clauses.ClippingClause,
        clauses.ColourSpec,
        clauses.EnableClause,
        clauses.FlagClause,
        clauses.ModuleArguments,
        clauses.ModuleInViewClause,
        clauses.ModuleMarker,
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


def test_walk_descends_into_header_arguments_and_groupconn() -> None:
    header = m.ModuleHeader(
        name="Header",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        arguments=clauses.ModuleArguments(
            enable=EnableClause(True, VarRef("Enabled")),
            module_in_view=clauses.ModuleInViewClause(True, VarRef("Visible")),
        ),
        invoke_coord_tails=[VarRef("Coord")],
        groupconn=VarRef("Conn"),
    )

    relations = {event.relation for event in walk(header)}

    assert {"arguments", "enable", "module_in_view", "tail", "invoke_coord_tails[0]", "groupconn"} <= relations


def test_walk_orders_header_and_module_type_fields_by_declaration() -> None:
    header = m.ModuleHeader(
        name="Header",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        arguments=clauses.ModuleArguments(
            enable=EnableClause(True, VarRef("Enabled")),
            zoom_limits=clauses.ZoomLimits(0.5, 2.0),
        ),
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
        "arguments",
        "enable",
        "tail",
        "zoom_limits",
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
        source_type=m.MappingSource.VALUE,
        is_duration=False,
        is_source_global=False,
    )

    assert [event.relation for event in walk(mapping)] == ["", "target"]


def test_walk_visits_graph_property_tails_once() -> None:
    """A clause-owned tail is emitted through its clause, not the flat list."""
    clause_tail = VarRef("ColourVar")
    coordinate_tail = VarRef("CoordVar")
    colour = ColourSpec(
        kind="outline",
        assignments=(TailedClause(key="Colour0", value=1, tail=clause_tail),),
    )
    graph_object = m.GraphObject(
        "RectangleObject",
        properties={"colours": [colour], "tails": [coordinate_tail, clause_tail]},
    )

    events = list(walk(graph_object))
    clause_events = [event for event in events if event.node is clause_tail]
    relations = [event.relation for event in events]

    assert len(clause_events) == 1
    assert isinstance(clause_events[0].parents[-1], TailedClause)
    assert "properties.colours[0]" in relations
    assert "properties.tails[0]" in relations
    assert "properties.tails[1]" not in relations


def test_walk_visits_interact_clause_and_body_tails_once() -> None:
    enable_tail = VarRef("EnableVar")
    body_tail = VarRef("BodyVar")
    flag_tail = VarRef("FlagTail")
    interact = m.InteractObject(
        "TextBox_",
        properties={
            "enables": [EnableClause(True, enable_tail)],
            "body": [
                TailedClause(key="Value", value=0, tail=body_tail),
                FlagClause("FlagName", tail=flag_tail),
            ],
            "tails": [enable_tail, body_tail, flag_tail],
        },
    )

    events = list(walk(interact))
    enable_events = [event for event in events if event.node is enable_tail]
    body_events = [event for event in events if event.node is body_tail]
    flag_events = [event for event in events if event.node is flag_tail]

    assert len(enable_events) == 1
    assert len(body_events) == 1
    assert len(flag_events) == 1
    assert isinstance(enable_events[0].parents[-1], EnableClause)
    assert isinstance(body_events[0].parents[-1], TailedClause)
    assert isinstance(flag_events[0].parents[-1], FlagClause)
    assert not any(event.relation.startswith("properties.tails") for event in events)


def test_walk_visits_module_def_clipping_tails_once() -> None:
    tail = VarRef("Source")
    module_def = m.ModuleDef(
        clipping=clauses.ClippingClause(((0.0, 0.0), (1.0, 1.0)), (tail,)),
    )

    events = list(walk(module_def))

    assert [event.relation for event in events if event.node is tail] == ["tails[0]"]


def test_unowned_tails_ignores_a_non_sequence_value() -> None:
    assert list(_unowned_tail_entries(None, set())) == []


def test_field_specs_cover_every_dataclass_field() -> None:
    for node_type in _NODE_TYPES:
        spec = _FIELD_SPECS[node_type]
        assert list(spec) == [field.name for field in dataclasses.fields(node_type)], node_type.__name__
        assert set(spec) == {field.name for field in dataclasses.fields(node_type)}, node_type.__name__
        assert set(spec.values()) <= {"leaf", "node", "value", "properties"}
        for kind in spec.values():
            assert kind != "properties" or node_type in {m.GraphObject, m.InteractObject}


def test_walk_event_field_is_a_declared_child() -> None:
    pictures = (_picture(), parse_source_file(_CORPUS / "BuiltinCalls.s"))
    for picture in pictures:
        for event in walk(picture):
            if not event.parents:
                continue
            assert event.field is not None
            parent = event.parents[-1]
            spec = _FIELD_SPECS[type(parent)]
            properties = getattr(parent, "properties", {})
            if event.field in properties:
                assert spec["properties"] == "properties", (type(parent).__name__, event.field)
            else:
                assert spec[event.field] in {"node", "value"}, (type(parent).__name__, event.field)


def test_walk_reports_field_and_indices() -> None:
    events = list(walk(_picture()))

    local = next(event for event in events if event.relation == "localvariables[0]")
    assert local.field == "localvariables"
    assert local.indices == (0,)

    branch = next(event for event in events if event.relation.startswith("branches[0][1]["))
    assert branch.field == "branches"
    assert branch.indices == (0, 1, 0)

    body = next(event for event in events if event.relation.startswith("properties.body["))
    assert body.field == "body"
    assert body.indices == (0,)


def test_walk_emits_matching_leave_events() -> None:
    picture = _picture()
    enters = list(walk(picture))
    both = list(walk(picture, emit_leave=True))
    enter_events = [event for event in both if event.phase == "enter"]
    leave_events = [event for event in both if event.phase == "leave"]

    assert enter_events == enters
    assert len(leave_events) == len(enter_events)
    assert {id(event.node) for event in (enter_events[0], leave_events[-1])} == {id(picture)}


def test_leave_events_wrap_the_subtree() -> None:
    header = m.ModuleHeader(
        name="Header",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        invoke_coord_tails=[VarRef("Coord")],
    )

    phases = [(event.phase, event.relation) for event in walk(header, emit_leave=True)]

    assert phases == [
        ("enter", ""),
        ("enter", "arguments"),
        ("leave", "arguments"),
        ("enter", "invoke_coord_tails[0]"),
        ("leave", "invoke_coord_tails[0]"),
        ("leave", ""),
    ]


def test_pruned_node_still_gets_a_leave_event() -> None:
    events = list(walk(_picture(), prune=lambda node: isinstance(node, m.Sequence), emit_leave=True))

    sequence = next(event for event in events if isinstance(event.node, m.Sequence))
    leave = next(event for event in events if event.phase == "leave" and event.node is sequence.node)

    assert sequence.phase == "enter"
    assert leave.field == sequence.field
    assert leave.indices == sequence.indices
    assert not any(isinstance(event.node, m.SFCStep) for event in events)


def test_iter_literal_leaves_reads_value_fields() -> None:
    clause = TailedClause("Width_", 2.5, VarTail("in", "Name"))
    comparison = Compare(VarRef("A"), "<", 3)
    variable = m.Variable(name="V", datatype="integer", init_value=7)

    assert [(leaf.field, leaf.indices, leaf.value) for leaf in iter_literal_leaves(clause)] == [("value", (), 2.5)]
    assert [(leaf.field, leaf.value) for leaf in iter_literal_leaves(comparison)] == [("right", 3)]
    assert [(leaf.field, leaf.value) for leaf in iter_literal_leaves(variable)] == [("init_value", 7)]
    assert [(leaf.relation, leaf.value) for leaf in iter_literal_leaves(VarTail("in", "Name"))] == [("value", "Name")]
    assert list(iter_literal_leaves([clause])) == list(iter_literal_leaves(clause))
    assert list(iter_literal_leaves(VarTail("out", LitStringTail("LitString", "Sym")))) == []
    assert list(iter_literal_leaves(m.SourceSpan(0, 1, 1, 1))) == []
    call = FuncCall("Max", (VarRef("A"), 2, 3))
    assert [(leaf.field, leaf.indices, leaf.value) for leaf in iter_literal_leaves(call)] == [
        ("args", (1,), 2),
        ("args", (2,), 3),
    ]


def test_iter_literal_leaves_reads_branch_conditions_and_values() -> None:
    body = (Assignment(VarRef("X"), 1),)
    statement = IfStmt(branches=((True, body),), else_block=None)
    ternary = TernaryOp(branches=((False, 1),), else_expr=2)

    assert [(leaf.field, leaf.indices, leaf.value) for leaf in iter_literal_leaves(statement)] == [
        ("branches", (0, 0), True)
    ]
    assert [(leaf.field, leaf.indices, leaf.value) for leaf in iter_literal_leaves(ternary)] == [
        ("branches", (0, 0), False),
        ("branches", (0, 1), 1),
        ("else_expr", (), 2),
    ]


class _ScopeCollector(NodeVisitor):
    def __init__(self) -> None:
        self.entered: list[str] = []
        self.left: list[str] = []

    def visit_SingleModule(self, module: m.SingleModule) -> None:
        self.entered.append(module.header.name)
        self.generic_visit(module)

    def leave_SingleModule(self, module: m.SingleModule) -> None:
        self.left.append(module.header.name)


def test_node_visitor_runs_leave_hooks_in_reverse_order() -> None:
    child = m.SingleModule(header=m.ModuleHeader(name="Child", invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0)))
    parent = m.SingleModule(
        header=m.ModuleHeader(name="Parent", invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0)),
        submodules=[child],
    )

    collector = _ScopeCollector()
    collector.visit(parent)

    assert collector.entered == ["Parent", "Child"]
    assert collector.left == ["Child", "Parent"]


def test_walk_emits_bound_tail_nodes() -> None:
    litstring = LitStringTail("LitString", "Symbol")
    bound = VarTail("out", litstring)
    header = m.ModuleHeader(
        name="Header",
        invoke_coord=(0.0, 0.0, 0.0, 1.0, 1.0),
        invoke_coord_tails=[bound],
    )

    events = list(walk(header))

    assert [event.relation for event in events if event.node is bound] == ["invoke_coord_tails[0]"]
    assert [event.relation for event in events if event.node is litstring] == ["value"]


def test_walk_property_order_covers_every_typed_dict_key() -> None:
    assert set(_GRAPH_PROPERTY_ORDER) == set(GraphProperties.__annotations__)
    assert set(_INTERACT_PROPERTY_ORDER) == set(InteractProperties.__annotations__)


def test_walk_property_order_keeps_tails_after_clause_owners() -> None:
    graph_owners = {"colours", "enable_tail"}
    interact_owners = {"procedure", "assigns", "enables", "flags", "colours", "body"}

    assert _GRAPH_PROPERTY_ORDER.index("tails") > max(_GRAPH_PROPERTY_ORDER.index(key) for key in graph_owners)
    assert _INTERACT_PROPERTY_ORDER.index("tails") > max(_INTERACT_PROPERTY_ORDER.index(key) for key in interact_owners)


def test_iter_child_nodes_filters_non_node_property_values() -> None:
    tail = VarRef("Tail")
    caption = VarRef("Caption")
    graph_object = m.GraphObject(
        "RectangleObject",
        properties={
            "coords": ((0.0, 0.0), (1.0, 1.0)),
            "polygon_type": ["Polyline"],
            "text_vars": [caption],
            "tails": [tail],
        },
    )

    children = list(iter_child_nodes(graph_object))

    assert children == [("properties.tails[0]", tail), ("properties.text_vars[0]", caption)]


def test_walk_emits_text_variable_and_pick_button_references() -> None:
    caption = VarRef("Caption")
    pick = VarRef("PickVar")
    graph_object = m.GraphObject("TextObject", properties={"text_vars": [caption]})
    button = clauses.PickButton("PickVar", reference=pick)
    interact = m.InteractObject("TextBox_", properties={"body": [button]})

    assert [event.relation for event in walk(graph_object) if event.node is caption] == ["properties.text_vars[0]"]
    assert [event.relation for event in walk(interact) if event.node is pick] == ["reference"]


def test_walk_clause_without_a_tail_has_no_children() -> None:
    assert [event.relation for event in walk(EnableClause(True, None))] == [""]


def test_walk_emits_a_node_valued_clause() -> None:
    value = VarRef("SomeVar")
    clause = TailedClause(key="Value", value=value, tail=None)

    assert [event.relation for event in walk(clause)] == ["", "value"]


def test_walk_visits_typed_interact_body_entries() -> None:
    alignment = clauses.Alignment("right")
    clause = EnableClause(True, VarRef("BodyEnable"))
    interact = m.InteractObject(
        "TextBox_",
        properties={
            "body": [alignment, clause],
            "tails": [clause.tail],
        },
    )

    events = list(walk(interact))

    assert [event.relation for event in events if event.node is alignment] == ["properties.body[0]"]
    assert [event.relation for event in events if event.node is clause] == ["properties.body[1]"]
    assert [event.relation for event in events if event.node is clause.tail] == ["tail"]


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


_NOT_AST_NODE = {
    ast_model.SourceSpan,
    ast_model.GraphicsBinding,
    # Transformer intermediates: their content is folded into an owner before
    # the AST is returned, or they are only arguments to the transformer.
    clauses.CommonProperties,
    clauses.Grid,
    clauses.ModuleOptions,
    clauses.SeqLayers,
    clauses.TwoLayers,
    clauses.Zoomable,
    tails.ClipValue,
    tails.CoordinateClipping,
}


def test_every_exported_dataclass_node_is_in_the_walker_registry() -> None:
    exported: list[type[object]] = []
    for module in (ast_model, expressions, clauses, tails):
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

    assert "name" not in relations
    assert "datecode" not in relations


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
