- **A 21-character declared identifier is a friendly finding.** The lexer accepts
  an identifier of any length, so an over-long name parses and `SL-V038` reports
  it at the declaration with its span, instead of the lexer rejecting the
  twenty-first character as unexpected. A sidecar dependency name is still
  capped at 20 characters, because that name builds a filesystem path.
