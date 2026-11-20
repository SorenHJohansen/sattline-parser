"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: DuplicateSiblingCrossType"
(* INVALID: Two sibling submodule instances with the same label but
   different module kinds: a module-type instance and an inline module.
   A module instance name is an instance label, not a resolvable symbol, and
   it is unique within its container regardless of the module kind.
   Expected: strict syntax-check fails at stage "validation" (SL-V004). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   ChildType = MODULEDEFINITION DateCode_ 2
   MODULEPARAMETERS
      Value: integer  := 0;

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*ChildType*);

SUBMODULES
   Shared Invocation
      ( 0.1 , 0.1 , 0.0 , 0.3 , 0.3
       ) : ChildType (
      Value => 1);

   Shared Invocation
      ( 0.5 , 0.1 , 0.0 , 0.3 , 0.3
       ) : MODULEDEFINITION DateCode_ 3
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*Shared*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
