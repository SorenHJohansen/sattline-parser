- **Polygon points and text-object geometry reach the AST.** A `PolygonObject`
  keeps every coordinate pair in `GraphProperties["points"]` as a
  `PolygonPoint`, with the tails written after each value attached to that
  value. A `TextObject` keeps `Width_`, `ValueFraction`, and `Format_String_` as
  `TailedClause` payloads, its `LeftAligned`/`RightAligned` markers in
  `alignments`, and its `ConnectionNode` anchor as a `GraphObject`. `PolygonPoint`
  is exported from `sattline_parser.ast`, and the walk visits each new property
  once.
