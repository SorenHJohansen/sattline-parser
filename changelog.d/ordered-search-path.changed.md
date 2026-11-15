- **The search path is the lookup order.** `SattLineProject.load` and
  `sattline project` search the roots in the order given, and an earlier root
  wins, matching the path list the real tool searches. Requester-relative
  precedence, cluster sorting by branch, and the terminal-root fallback are
  removed, and `ProjectLookup` computes one order instead of one per requester.
  `parse_search_path` reads the `GC\UnitLib,HA\UnitLib` notation, and
  `sattline project` gains `--search-path` and `--search-path-base`; positional
  roots and `--search-path` cannot be combined. Because one path order resolves
  every name, one folded name can no longer reach two bodies:
  `NAME_RESOLUTION_CONFLICT` is removed, and a later same-named body is never
  planned, parsed, or validated. `LOOKUP_CACHE_VERSION` is `2`.
