- **Header metadata reaches the AST.** `BasePicture.header_info` is a
  `HeaderInfo` holding the three quoted header lines as written and the optional
  change description as a `CodeComment`. It reads the written syntax version,
  original file date, and program date, and `program_name` remains the
  convenience view over the `name:` field, matched case-insensitively. `HeaderInfo`
  is exported from `sattline_parser.ast` and visited by `walk`.
