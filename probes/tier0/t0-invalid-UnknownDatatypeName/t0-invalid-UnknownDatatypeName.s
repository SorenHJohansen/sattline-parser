"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: UnknownDatatypeName"
(*
tier 0 sweep: invalid/UnknownDatatypeName.s INVALID: A variable uses a datatype that is neither a built-in type nor a
   declared DATATYPE. "Zzzyx" appears nowhere in TYPEDEFINITIONS and is not
   close enough to any built-in name to be a typo, so it is an unknown type.
   Expected: strict syntax-check fails at stage "validation" (SL-V020). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Part: Zzzyx  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
