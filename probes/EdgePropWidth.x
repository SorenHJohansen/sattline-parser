"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: EdgePropWidth"
(*
open question: is `Width_ = 4` accepted on a TextObject? our width_tailed rule.
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
   TextObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )
      Width_ = 4

ENDDEF (*BasePicture*);
