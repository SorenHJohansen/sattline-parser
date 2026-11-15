- **Coordinate tails keep their value.** A module header's coordinate tails are
  also grouped in `ModuleHeader.coordinate_tails`, a clipping clause's in
  `ClippingClause.corner_tails`, and a graphics or interact coordinate run in
  the `coord_tails` property key. Each group is index-aligned with the written
  values and holds the same tail objects as the flat view. The flat fields are
  unchanged, so existing readers and validation rules keep working.
