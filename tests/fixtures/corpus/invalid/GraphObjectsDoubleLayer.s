"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: GraphObjectsDoubleLayer"
(* INVALID: a GraphObjects section may carry at most one Layer_ directive.
   A second Layer_ after the first is rejected because the section belongs to
   a single layer. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects : Layer_ = 2 Layer_ = 3
   RectangleObject ( -1.0 , 1.0 ) ( 1.0 , -1.0 )

ENDDEF (*BasePicture*);
