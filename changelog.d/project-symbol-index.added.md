- **Project symbol index.** `SattLineProject.index` answers which loaded unit
  defines a name and which loaded units use it. `definitions_of(name)` reports
  program, record, module-type, and variable declarations; `usages_of(name)`
  reports variable references and module-type instances. Names compare
  case-insensitively and the results are stable across runs. `invoked_moduletypes`
  is now exported from `sattline_parser.project` for consumers that want the
  loader's reachability answer directly.
