"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: AuxLib"
(* project unit AuxLib *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 900001

TYPEDEFINITIONS
   AuxType = MODULEDEFINITION DateCode_ 230100
   LOCALVARIABLES
      AuxVar: integer  := 0;
   SUBMODULES
      PumpInst Invocation
         ( 0.0 , 0.0 , 0.0 , 0.5 , 0.5
          ) : MODULEDEFINITION DateCode_ 220100;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK AuxTypeEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      AuxVar = AuxVar + 1;
   ENDDEF (*AuxType*);

LOCALVARIABLES
   TopVar: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
