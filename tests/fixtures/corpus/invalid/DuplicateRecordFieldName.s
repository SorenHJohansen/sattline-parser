"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: DuplicateRecordFieldName"
(* INVALID: A record declares two fields with the same name. Field names must
   be unique within a DATATYPE so dotted references like P.Left stay
   unambiguous.
   Expected: strict syntax-check fails at stage "validation" (SL-V025). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   Pair = RECORD DateCode_ 1
      Left: integer  := 0;
      Left: real  := 0.0;
   ENDDEF
    (*Pair*);

LOCALVARIABLES
   Position: Pair  := Default;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
