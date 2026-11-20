"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: ProcedureAsValue"
(* INVALID: A procedure call used where a value is required.
   CopyString is a procedure (kind procedure, no return type), so it can only
   be a statement. Used as an assignment source, an IF condition, an arithmetic
   operand, and a ternary branch it cannot supply a value.
   Expected: strict syntax-check fails at stage "validation" (SL-V060). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   S1: string  := "";
   S2: string  := "";
   I: integer  := 0;
   Limit: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ModuleCode
EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
   I = CopyString(S1, S2, I);
   IF CopyString(S1, S2, I) THEN
      I = 1;
   ENDIF;
   I = Limit + CopyString(S1, S2, I);
   I = IF True THEN CopyString(S1, S2, I) ELSE Limit ENDIF;
   CopyString(S1, S2, I);
ENDDEF (*BasePicture*);
