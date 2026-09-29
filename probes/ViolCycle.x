"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: ModuleLoop"
(* probe C-101: moduletype instantiation cycle (A instantiates B, B instantiates A) *)

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
          ) : TypeB;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK AEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      AVar = AVar + 1;
   ENDDEF (*TypeA*);

   TypeB = MODULEDEFINITION DateCode_ 101200
   LOCALVARIABLES
      BVar: integer  := 0;
   SUBMODULES
      BChild Invocation
         ( 0.0 , 0.0 , 0.0 , 0.5 , 0.5
          ) : TypeA;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK BEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      BVar = BVar + 1;
   ENDDEF (*TypeB*);


LOCALVARIABLES
   TopVar: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
