"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: ConstVarAsBuiltinOutArg"
(*
tier 0 sweep: invalid/ConstVarAsBuiltinOutArg.s INVALID: A built-in call writes its output into a Const-declared variable.
   CopyTime's second argument has direction 'out' and receives the copy
   result; routing it into a read-only Const variable is rejected just like a
   direct assignment to a Const.
   Expected: strict syntax-check fails at stage "validation" (SL-V007). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   SourceTime: time  := Time_Value "2026-01-01-00:00:00.000";
   Fixed: time Const  := Time_Value "2026-01-01-00:00:00.000";

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      CopyTime(SourceTime, Fixed);

ENDDEF (*BasePicture*);
