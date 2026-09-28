"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: DatatypeShadowsBuiltinName"
(* INVALID: A DATATYPE is declared with a name that matches a built-in
   datatype. Declaring "Integer" as a record type shadows the built-in
   "integer" type and would make variable typing ambiguous.
   Expected: strict syntax-check fails at stage "validation" (SL-V026). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   Integer = RECORD DateCode_ 1
      X: real  := 0.0;
   ENDDEF
    (*Integer*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
