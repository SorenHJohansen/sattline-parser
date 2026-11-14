- **Interim AST payloads leave the model surface.** `CommonProperties`,
  `ModuleOptions`, `TwoLayers`, `Grid`, `SeqLayers`, `Zoomable`, `ClipValue`, and
  `CoordinateClipping` are transformer payloads, never AST nodes, and now live
  in `sattline_parser.transformer._payloads`. They are no longer exported from
  `sattline_parser.models` or `sattline_parser.ast`.
