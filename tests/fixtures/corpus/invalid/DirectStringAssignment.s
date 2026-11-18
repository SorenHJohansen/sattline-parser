"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: DirectStringAssignment"
(* INVALID: An equation assigns a value to a plain String variable.
   A String is a fixed-size buffer, so the language copies it with CopyString or
   CopyVar rather than assigning it. The rule covers the plain String datatype;
   the other string families are not covered because nothing establishes that
   the language rejects a direct assignment to them.
   Expected: strict syntax-check fails at stage "validation". *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Text: string  := "";
   CopyStatus: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Text = "value";

ENDDEF (*BasePicture*);
