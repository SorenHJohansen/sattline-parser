"Syntax version 2.23, date: 2026-10-01-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-10-01-12:00:00.000, name: GraphObjectsObjectLayer"
(* Covers a per-object Layer_ directive inside GraphObjects.
   Replaces the section-level clause fixture, which probe 2026-10-01 disproved:
   the real parser rejects "GraphObjects : Layer_ = 2" with
   "AliasSym Expected" (see invalid/GraphObjectsSectionLayer.s). A layer
   belongs to the object that declares it.
   Expected: strict syntax-check passes; each object reports its own layer. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   RectangleObject ( -1.0 , 1.0 ) ( 1.0 , -1.0 )
      Layer_ = 2
   TextObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )
      "DisplayValue"
      Layer_ = 3

ENDDEF (*BasePicture*);
