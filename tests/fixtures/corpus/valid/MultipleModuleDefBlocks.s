"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: MultipleModuleDefBlocks"
(* Covers multiple "ModuleDef ... [ModuleCode ...] ENDDEF" blocks inside a
   single module body. Legacy coded files repeat this block once per layer, so
   a parser that only keeps the last block silently drops the earlier layers.
   Each block has its own clipping bounds and its own equation code.
   Expected: strict syntax-check passes; all blocks survive in source order. *)

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
ENDDEF
ModuleDef
ClippingBounds = ( -2.0 , -2.0 ) ( 2.0 , 2.0 )
ModuleCode
   EQUATIONBLOCK Upper COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      UpperB = UpperB + 1;
ENDDEF (*BasePicture*);
