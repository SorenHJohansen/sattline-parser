"Syntax version 2.23, date: 2026-10-01-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-10-01-12:00:00.000, name: GraphObjectsSectionLayer"
(* INVALID: a section-level Layer_ clause on the GraphObjects section.
   This file used to sit in valid/ and asserted that the section layer
   propagates to every object in the section. Probe 2026-10-01 disproved the
   premise -- ValidGraphObjB.x used exactly "GraphObjects : Layer_ = 2" and the
   real parser reported:
     GraphObjects : >>>Layer_<<< 2 AliasSym Expected
   The tool reads what follows "GraphObjects :" as the start of the first
   object definition and wants an AliasSym there; Layer_ is a reserved keyword,
   so it is not one. There is no section-level layer clause.

   Per-object "Layer_ = N" is still grammar-valid and is covered by
   valid/GraphObjectsObjectLayer.s.
   Expected: strict parse fails. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects : Layer_ = 2
   RectangleObject ( -1.0 , 1.0 ) ( 1.0 , -1.0 )
   TextObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )
      "DisplayValue"

ENDDEF (*BasePicture*);
