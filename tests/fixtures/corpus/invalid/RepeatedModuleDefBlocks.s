"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: RepeatedModuleDefBlocks"
(* A module body has one ModuleDef; a second block before the closing ENDDEF is a
   syntax error. The second block has its own clipping bounds and equation code,
   so a parser that silently overwrote the first block would lose them.
   Expected: the source does not parse. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   LowerA: integer  := 0;
   UpperB: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Lower COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      LowerA = LowerA + 1;
ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Upper COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      UpperB = UpperB + 1;
ENDDEF (*BasePicture*);
