- **`#;>` decodes as `Non_Zoomable`.** Scanner ordinal 190 was missing from
  `scanner_tokens.json`, so a coded library body that spells the argument failed
  to preprocess with `Unknown compressed marker '#;>'` and was skipped as a
  whole. The ordinal sits between `Cancel_Variable` (189) and `LayerLimit_`
  (191), and a coded invocation spells it where the uncompressed libraries spell
  `Non_Zoomable`. `BatchLib`-class bodies now decode, parse, and validate.
