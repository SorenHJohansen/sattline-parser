- **`sattline project` no longer logs a parser traceback.** A body that fails to
  parse is reported once, as the structured `PROJECT_LOAD_ERROR` finding, with
  nothing on stderr. `--debug` still prints the loader's progress and the
  parser's traceback.
