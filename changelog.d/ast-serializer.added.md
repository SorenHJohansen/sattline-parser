- **Public AST serializer.** `to_jsonable(value, *, depth=None)` turns any model
  value into JSON-friendly data and `to_json(...)` encodes it, both exported by
  `sattline_parser`. Every dataclass field is emitted under its own name, so a
  new model field needs no serializer change, and `depth` replaces a composite
  value with a placeholder at the limit instead of dropping it. The CLI now uses
  the same functions.
