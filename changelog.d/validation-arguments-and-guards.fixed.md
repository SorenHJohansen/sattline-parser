- **Argument and guard checks.** `accepts_const_string` now exempts only the
  Const-write finding for a string-cursor parameter: `GetStringPos` still
  rejects a non-reference argument (`SL-V014`) and a wrong datatype (`SL-V047`).
  An SFC transition guard is now checked like an IF condition, so
  `WAIT_FOR 123` reports `SL-V030`.
