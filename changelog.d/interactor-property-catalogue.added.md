- **Interactor property catalogue.** `interactor_property_catalogue` names the
  interactor property spellings the scanner defines but the grammar accepts as a
  generic flag or assignment. `find_interactor_property` classifies one spelling
  and `typed_interactor_properties` reads an interactor's properties in written
  order from either container shape. Parsing and the stored clauses are
  unchanged, and an unknown property still parses as a generic clause.
