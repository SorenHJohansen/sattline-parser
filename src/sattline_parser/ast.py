"""Supported AST surface for the SattLine parser.

This module is the stable import door for the syntax tree. It re-exports every
node, clause payload, and tail type together with the traversal helpers, so a
consumer never has to import from ``sattline_parser.models`` submodules, whose
layout is an implementation detail.

Use it for ordinary tree work::

    from sattline_parser import parse_source_file
    from sattline_parser.ast import VarRef, walk

    picture = parse_source_file(path)
    for event in walk(picture):
        if isinstance(event.node, VarRef):
            print(event.relation, event.node.name)

``walk`` is node-only. Literal values are leaves; the walker does not emit
them. ``iter_literal_leaves`` reads the literal values a node holds, and
``LiteralLeaf`` describes one. ``NodeVisitor`` is the subclassing form, and
``WalkEvent`` carries the relation and ancestry of each visited node.
``tail_list`` is the default factory for tail-bearing fields, and
``is_expression_tail`` is the shared predicate for a computed ``Tail``.
"""

from __future__ import annotations

from .models.ast_model import (
    BasePicture,
    CodeItem,
    DataType,
    Equation,
    FloatLiteral,
    FrameModule,
    GraphicsBinding,
    GraphObject,
    InteractObject,
    IntLiteral,
    MappingSource,
    ModuleCode,
    ModuleDef,
    ModuleHeader,
    ModuleTypeDef,
    ModuleTypeInstance,
    ParameterMapping,
    ScalarDatatype,
    Sequence,
    SFCAlternative,
    SFCBodyItem,
    SFCCodeBlocks,
    SFCFork,
    SFCParallel,
    SFCStep,
    SFCSubsequence,
    SFCTransition,
    SFCTransitionSub,
    SingleModule,
    SourceSpan,
    Variable,
)
from .models.clauses import (
    Alignment,
    AssignClause,
    ClippingClause,
    ColourSpec,
    CoordBox,
    CoordPair,
    EnableClause,
    FlagClause,
    ModuleArguments,
    ModuleInViewClause,
    ModuleMarker,
    PickButton,
    PolygonPoint,
    ProcedureCall,
    ScaleSelector,
    TailedClause,
    ZoomLimits,
)
from .models.expressions import (
    Assignment,
    BinOp,
    BoolOp,
    CodeComment,
    Compare,
    FuncCall,
    FuncCallStmt,
    IfStmt,
    NotOp,
    SLExpression,
    SLStmt,
    TernaryOp,
    UnaryOp,
    VarRef,
)
from .models.header import HeaderInfo
from .models.properties import GraphProperties, InteractBodyEntry, InteractProperties
from .models.tails import (
    LitStringTail,
    Tail,
    VarTail,
    is_expression_tail,
    tail_list,
)
from .models.walk import (
    LiteralLeaf,
    NodeVisitor,
    WalkEvent,
    iter_child_nodes,
    iter_literal_leaves,
    walk,
)

__all__ = [
    "Alignment",
    "AssignClause",
    "Assignment",
    "BasePicture",
    "BinOp",
    "BoolOp",
    "ClippingClause",
    "CodeComment",
    "CodeItem",
    "ColourSpec",
    "Compare",
    "CoordBox",
    "CoordPair",
    "DataType",
    "EnableClause",
    "Equation",
    "FlagClause",
    "FloatLiteral",
    "FrameModule",
    "FuncCall",
    "FuncCallStmt",
    "GraphObject",
    "GraphProperties",
    "GraphicsBinding",
    "HeaderInfo",
    "IfStmt",
    "IntLiteral",
    "InteractBodyEntry",
    "InteractObject",
    "InteractProperties",
    "LitStringTail",
    "LiteralLeaf",
    "MappingSource",
    "ModuleArguments",
    "ModuleCode",
    "ModuleDef",
    "ModuleHeader",
    "ModuleInViewClause",
    "ModuleMarker",
    "ModuleTypeDef",
    "ModuleTypeInstance",
    "NodeVisitor",
    "NotOp",
    "ParameterMapping",
    "PickButton",
    "PolygonPoint",
    "ProcedureCall",
    "SFCAlternative",
    "SFCBodyItem",
    "SFCCodeBlocks",
    "SFCFork",
    "SFCParallel",
    "SFCStep",
    "SFCSubsequence",
    "SFCTransition",
    "SFCTransitionSub",
    "SLExpression",
    "SLStmt",
    "ScalarDatatype",
    "ScaleSelector",
    "Sequence",
    "SingleModule",
    "SourceSpan",
    "Tail",
    "TailedClause",
    "TernaryOp",
    "UnaryOp",
    "VarRef",
    "VarTail",
    "Variable",
    "WalkEvent",
    "ZoomLimits",
    "is_expression_tail",
    "iter_child_nodes",
    "iter_literal_leaves",
    "tail_list",
    "walk",
]
