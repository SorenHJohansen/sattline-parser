"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: ModuleSelfLoop"
(* probe C-102: moduletype instantiates itself (degenerate loop) *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 900001

TYPEDEFINITIONS
   TypeA = MODULEDEFINITION DateCode_ 101100
   LOCALVARIABLES
      AVar: integer  := 0;
   SUBMODULES
      AChild Invocation
         ( 0.0 , 0.0 , 0.0 , 0.5 , 0.5
          ) : TypeA;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK AEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      AVar = AVar + 1;
   ENDDEF (*TypeA*);


LOCALVARIABLES
   TopVar: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
