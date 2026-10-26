"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: EdgePropEnable"
(*
open question: is `Enable_ = True` accepted bare, with no trailing clause? ValidInteractEnabl.x was
   rejected at `Enable_ = True:` with `AliasSym Expected`, but that file has a trailing colon, so this
   isolates the bare form.
   Expected: unknown - this probe decides it. *)

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
      Enable_ = True

ENDDEF (*BasePicture*);
