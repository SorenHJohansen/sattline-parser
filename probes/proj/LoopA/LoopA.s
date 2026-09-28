"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: LoopA"
(* project unit LoopA *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 900001

TYPEDEFINITIONS
   LoopAType = MODULEDEFINITION DateCode_ 210100
   LOCALVARIABLES
      AVar: integer  := 0;
   SUBMODULES
      BInst Invocation
         ( 0.0 , 0.0 , 0.0 , 0.5 , 0.5
          ) : MODULEDEFINITION DateCode_ 210200;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK LoopATypeEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      AVar = AVar + 1;
   ENDDEF (*LoopAType*);

LOCALVARIABLES
   TopVar: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
