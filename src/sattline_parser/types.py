"""Public type facts for the SattLine language.

This module publishes the scalar type families, literal inference, datatype
normalization, dotted-name splitting, and record field resolution that the
parser's own validation uses. Import the type facts from here rather than from
``sattline_parser.validation.typing``, whose layout is an implementation detail.

Expression typing that needs a validation scope stays inside the validation
layer. A consumer that needs a diagnostic answer for a whole picture uses
``validate_basepicture`` instead.

The exported functions are pure. This module is a re-export façade, not an
import-isolation boundary: importing it still executes the validation package.
"""

from __future__ import annotations

from sattline_parser.models.ast_model import Simple_DataType
from sattline_parser.validation.typing import (
    FieldGraph,
    FieldSpec,
    TypeFamily,
    assignment_type_matches,
    builtin_type_matches,
    datatype_family,
    expression_is_zero_literal,
    extract_time_literal,
    family_of,
    format_datatype,
    has_time_literal_marker,
    infer_literal_datatype,
    is_anytype_datatype,
    is_boolean,
    is_boolean_datatype,
    is_numeric,
    is_numeric_datatype,
    is_string_simple_type,
    is_valid_duration_literal,
    is_valid_time_literal,
    literal_matches_expected_datatype,
    merge_compatible_types,
    merge_numeric_types,
    normalize_builtin_datatype,
    resolve_variable_field_datatype,
    split_dotted_name,
    suggest_datatype_name,
)

__all__ = [
    "FieldGraph",
    "FieldSpec",
    "Simple_DataType",
    "TypeFamily",
    "assignment_type_matches",
    "builtin_type_matches",
    "datatype_family",
    "expression_is_zero_literal",
    "extract_time_literal",
    "family_of",
    "format_datatype",
    "has_time_literal_marker",
    "infer_literal_datatype",
    "is_anytype_datatype",
    "is_boolean",
    "is_boolean_datatype",
    "is_numeric",
    "is_numeric_datatype",
    "is_string_simple_type",
    "is_valid_duration_literal",
    "is_valid_time_literal",
    "literal_matches_expected_datatype",
    "merge_compatible_types",
    "merge_numeric_types",
    "normalize_builtin_datatype",
    "resolve_variable_field_datatype",
    "split_dotted_name",
    "suggest_datatype_name",
]
