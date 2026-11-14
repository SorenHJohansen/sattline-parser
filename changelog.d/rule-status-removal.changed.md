- **`Rule.status` replaces the rule flags.** `Rule.implemented` and
  `Rule.retired`, and their constructor arguments, are removed; read
  `Rule.status` (`ACTIVE`, `RETIRED`, `UNIMPLEMENTED`) instead. `to_json()`
  keeps the derived `retired` boolean, so a JSON consumer needs no change.
