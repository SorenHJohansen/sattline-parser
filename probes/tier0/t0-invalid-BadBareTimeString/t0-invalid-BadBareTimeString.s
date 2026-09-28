"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: BadBareTimeString"
(*
tier 0 sweep: invalid/BadBareTimeString.s INVALID: A time variable initialized without the required Time_Value keyword.
   The grammar requires Time_Value before the time string literal.
   Expected: strict syntax-check fails at stage "parsing". *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Timestamp: time  := "2026/04/23 12:00:00";

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
