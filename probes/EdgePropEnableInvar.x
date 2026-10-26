"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: EdgePropEnableInvar"
(*
open question: our `enable` rule REQUIRES a trailing invar (`: InVar_ x`). Does SattLine accept
   `Enable_ = True : InVar_ Flag`, or is the whole enable property unknown?
   Expected: unknown. *)

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
      Enable_ = True : InVar_ Flag

ENDDEF (*BasePicture*);
