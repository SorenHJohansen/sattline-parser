"Syntax version 2.23, date: 2026-10-01-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-10-01-12:00:00.000, name: HighByteInvalid"
(* Encoding probe: byte 0x81 (Å) is UNDEFINED in Windows-1252.
   Expected: our strict decode raises UnicodeDecodeError (no utf-8/latin-1
   fallback). Real-parser behavior unknown - OPEN THIS FILE ALONE. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Var1: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Var1 = Var1 + 1;

ENDDEF (*HighByteInvalid*);
