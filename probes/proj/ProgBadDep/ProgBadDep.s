"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: ProgBadDep"
(* project unit ProgBadDep *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 901002

LOCALVARIABLES
   TopVar: integer  := 0;

   PumpInst Invocation
      ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
       ) : MODULEDEFINITION DateCode_ 220100

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
