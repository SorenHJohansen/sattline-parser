"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: StringLiteralInCallArgument"
(* INVALID: A string literal used as an argument to a call with no known signature.
   A literal is accepted only where a documented signature declares an "in"
   string parameter, which proves that the callee takes a value there. This
   callee has no known signature, so nothing evidences that it accepts a value,
   and the literal is rejected.
   Expected: strict syntax-check fails at stage "validation". *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Input: string  := "";

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      UserProcedure("Expected");

ENDDEF (*BasePicture*);
