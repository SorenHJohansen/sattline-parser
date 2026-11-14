- **Graphics expression spans.** An `Expr` binding is parsed without a padding
  prefix, and its spans are rebased into companion coordinates afterwards. The
  work is linear in the expression length instead of the file offset, so a
  companion with many bindings no longer pays quadratic padding.
