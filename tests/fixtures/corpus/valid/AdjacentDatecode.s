"Syntax version 2.23, date: 2026-11-15-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-15-12:00:00.000, name: AdjacentDatecode"
(* The datecode prefix is written directly before its number, with no separator,
   and an arithmetic expression is written with no spaces around its operator.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_1

LOCALVARIABLES
   Sink: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Sink = 1+2;

ENDDEF (*BasePicture*);
