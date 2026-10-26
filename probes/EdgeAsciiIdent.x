"Syntax version 2.23, date: 2026-10-02-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-10-02-12:00:00.000, name: EdgeAsciiIdent"
(* ONE VARIABLE: cp1252 high byte (0xE4 a-umlaut) inside an IDENTIFIER.
   Everything else is ASCII. HighByteValid.x already shows high bytes are
   legal in a comment; this asks whether they are legal in a name.
   Our grammar says yes (NAME uses \p{L}). The tool said no for the Danish
   golden formaal. OPEN THIS FILE ALONE - record accept or reject. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Wertä: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Wertä = Wertä + 1;

ENDDEF (*EdgeAsciiIdent*);
