- **Compressed lexing.** A single-quoted identifier such as `'#84'` is literal
  text, so a marker inside it is no longer expanded or rejected as unknown. A
  description that ends at a line break no longer shields the following lines
  from marker expansion. `load_source_text` expands markers inside a coded
  stream instead of returning them undecoded.
