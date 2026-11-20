"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: EmptyRecordFieldAccess"
(* INVALID: A field access through a record this file declares with no fields.
   The record's shape is declared, not unmodelled, so a field it omits is a
   typo rather than an unknown shape.
   Expected: strict syntax-check fails at stage "validation" (SL-V019). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   EmptyRec = RECORD DateCode_ 2
   ENDDEF (*EmptyRec*);

LOCALVARIABLES
   Holder: EmptyRec;
   Sink: integer;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ModuleCode
EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
   Sink = Holder.Missing;
ENDDEF (*BasePicture*);
