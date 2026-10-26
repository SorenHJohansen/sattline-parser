"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: EdgePropLayer"
(*
open question: graph-object property keywords. Is `Layer_ = 1` accepted on a RectangleObject?
   Our grammar has layer_info: LAYER_PREFIX "=" SIGNED_INT. Isolated to a single property so a
   rejection identifies exactly one keyword.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Flag: boolean := True;
   Count: integer  := 5;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   RectangleObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )
      Layer_ = 1

ENDDEF (*BasePicture*);
