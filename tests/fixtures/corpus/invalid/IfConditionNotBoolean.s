"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: IfConditionNotBoolean"
(* INVALID: an IF condition is an integer, not a boolean.
   Probe ViolIntCond.x (2026-10-01) used the condition "A" where A is an
   integer and the real parser reported:
     Condition in IF-sentence is not boolean
   Expected: strict syntax-check fails at stage "validation" (SL-V030). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   A: integer  := 1;
   B: integer  := 0;
   C: integer  := 0;
   D: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      IF A THEN
         B = 1;
      ELSIF A + 1 THEN
         C = 2;
      ELSE
         D = True;
      ENDIF;

ENDDEF (*BasePicture*);
