"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: PumpLib"
(* project unit PumpLib *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 900001

TYPEDEFINITIONS
   PumpType = MODULEDEFINITION DateCode_ 220100
   LOCALVARIABLES
      PumpVar: integer  := 0;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK PumpTypeEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      PumpVar = PumpVar + 1;
   ENDDEF (*PumpType*);

LOCALVARIABLES
   TopVar: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
