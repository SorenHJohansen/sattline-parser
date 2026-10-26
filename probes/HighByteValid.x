"Syntax version 2.23, date: 2026-10-01-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-10-01-12:00:00.000, name: HighByteValid"
(* Encoding probe: VALID Windows-1252 high bytes in a comment.
   Byte 0x92 = ’ (right single quote) and 0xE4 (ä a-umlaut) are defined in cp1252.
   Expected: real parser accepts; our strict cp1252 decode accepts too. *)

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

ENDDEF (*HighByteValid*);
