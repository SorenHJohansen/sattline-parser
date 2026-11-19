"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: OldOnMappingSource"
(* INVALID: A parameter-mapping source carries :Old, but Plain is not State.
   The mapping source resolves in the invoking scope, so the :Old rule applies
   there like it does in module code.
   Expected: strict syntax-check fails at stage "validation" (SL-V005). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Plain: integer  := 0;

SUBMODULES
   Child Invocation
      ( 0.1 , 0.1 , 0.0 , 0.3 , 0.3
       ) : MODULEDEFINITION DateCode_ 2
   MODULEPARAMETERS
      P: integer  := 0;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*Child*) (P => Plain:Old);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
