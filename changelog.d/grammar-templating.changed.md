- **Grammar templating.** `sattline.lark` placeholders are substituted by name
  instead of through `str.format`, so a literal brace such as a regex
  quantifier (`{2,3}`) is written as it reads and no longer has to be doubled.
  An unknown placeholder now fails with an explicit error instead of reaching
  Lark.
