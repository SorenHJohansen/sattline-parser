- **Façade layering.** `sattline_parser.api` no longer imports
  `sattline_parser.project`. The graphics entry points
  (`parse_graphics_file`, `parse_graphics_text`,
  `resolve_graphics_companion_path`) moved from `api.__all__` to
  `sattline_parser.__all__`, so the documented surface keeps every name while
  `api` now depends only on `source_io`, `errors` and `validation`.
