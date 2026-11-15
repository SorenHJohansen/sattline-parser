"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: ModuleDefWithCode"
(* Covers the module layout block a module body carries:
   - exactly one ModuleDef, with clipping bounds
   - one optional ModuleCode, with an equation block
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   LowerA: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Lower COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      LowerA = LowerA + 1;
ENDDEF (*BasePicture*);
