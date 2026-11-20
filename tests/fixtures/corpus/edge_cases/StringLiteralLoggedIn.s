"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: StringLiteralLoggedIn"
(* EDGE CASE: A string literal in a documented "in" string parameter.
   LoggedIn declares its user-name parameter as an "in" String, so the literal
   is a value at a value position and the string-literal argument rule is
   silent.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   LoggedOn: boolean  := False;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      LoggedOn = LoggedIn("operator");

ENDDEF (*BasePicture*);
