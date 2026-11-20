"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: DuplicateDatatypeFieldType"
(* Edge case: one datatype name declared twice with different types for the
   same field. Two shapes are two valid readings, so the field's datatype is
   unproven: Holder.Value cannot be type-checked, and the assignment is silent.
   Expected: no findings. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   Rec = RECORD DateCode_ 2
      Value: integer;
   ENDDEF (*Rec*);
   Rec = RECORD DateCode_ 3
      Value: boolean;
   ENDDEF (*Rec*);

LOCALVARIABLES
   Holder: Rec;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ModuleCode
EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
   Holder.Value = 5;
ENDDEF (*BasePicture*);
