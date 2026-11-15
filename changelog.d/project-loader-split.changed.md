- **The loader is four collaborators.** `ProjectLoader` now orchestrates a
  planner (resolve names into post-order plans), an executor (parse bodies and
  own the worker pool and AST cache), an assembler (registry entries and
  companions), and a validator (validation scope and diagnostic aggregation).
  The dependency algorithm no longer shares a module with multiprocessing or
  the registry, and the public `ProjectLoader` behaviour is unchanged.
