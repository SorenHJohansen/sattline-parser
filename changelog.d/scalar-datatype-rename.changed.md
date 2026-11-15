- **`ScalarDatatype`.** `Simple_DataType` becomes `ScalarDatatype`, the closed
  set of the language's scalar datatypes. The name says what the enum holds: a
  scalar value, not a record, and not the `AnyType` wildcard, which stays a
  plain string for the type graph to resolve. The members, `from_any`, and the
  normalization behaviour are unchanged; the old spelling is removed, so a
  caller that imported it updates the name. Import it from
  `sattline_parser.ast` or `sattline_parser.types`.
