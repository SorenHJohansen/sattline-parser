"Syntax version 2.23, date: 2026-11-15-11:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-15-11:00:00.000, name: UnknownRecordField"
(* SEMANTIC: A field that the record does not declare is used for a write and a
   read. The record is declared in this file, so its shape is known.
   Expected: strict syntax-check fails with an undefined-variable finding for
   each use. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   Reading = RECORD DateCode_ 1
      Count: integer  := 0;
   ENDDEF
    (*Reading*);

LOCALVARIABLES
   Sample: Reading;
   Sink: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Sample.Missing = 1;
      Sink = Sample.Missing;

ENDDEF (*BasePicture*);
