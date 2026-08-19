"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: GraphObjectsSectionLayer"
(* Covers a section-level Layer_ directive in GraphObjects. The grammar allows
   at most one layer_info per GraphObjects section, and that layer applies to
   every object in the section (objects without their own explicit layer).
   Expected: strict syntax-check passes; both objects report layer = 2. *)

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
