- **`parse_and_validate` accepts external definitions.** `external_datatypes`,
  `external_moduletype_defs`, and `allow_unresolved_external_datatypes` now pass
  through to `validate_basepicture`, so a single-source consumer with loaded
  dependency definitions does not have to call the validator itself.
