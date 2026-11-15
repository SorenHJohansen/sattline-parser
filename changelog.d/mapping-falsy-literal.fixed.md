- **A boolean parameter mapping value is kept.** `Name => True` was read as the
  optional `GLOBAL` keyword, and `Name => False` as its absence, because the
  keyword and a boolean literal shared the value `True`. The keyword now has
  its own payload, so `True`, `False`, `0`, and `""` all reach the model as the
  written values.
