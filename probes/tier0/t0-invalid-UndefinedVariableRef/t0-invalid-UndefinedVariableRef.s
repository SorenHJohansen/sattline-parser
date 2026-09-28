"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: UndefinedVariableRef"
(*
tier 0 sweep: invalid/UndefinedVariableRef.s INVALID: An equation reads a variable that is not declared anywhere.
   "Ghost" has no declaration in LOCALVARIABLES, TYPEDEFINITIONS, or any
   enclosing module scope, and is not an SFC runtime accessor or boolean
   constant. Validation rejects references to undeclared variables.
   Expected: strict syntax-check fails at stage "validation" (SL-V019). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Input: integer  := 0;
   Result: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Result = Input + Ghost;

ENDDEF (*BasePicture*);
