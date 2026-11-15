- **Whole-file formatting.** `format_source(picture)` renders a parsed unit back
  to canonical SattLine source, and `format_module(module)` renders one
  `ModuleDef` block. The text parses back to an equal tree for every parsed
  corpus fixture, including graphics and interactor bodies. Each tail is written
  after the value it followed, using the new positional views
  `ModuleHeader.coordinate_tails`, `ClippingClause.corner_tails`, and the
  `coord_tails` property key. A hand-built model that carries a tail without its
  position raises `UnsupportedFormattingError` rather than moving it.
