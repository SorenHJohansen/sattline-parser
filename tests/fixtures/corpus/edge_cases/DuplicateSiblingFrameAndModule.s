"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: DuplicateSiblingFrameAndModule"
(* INVALID: A frame module and an inline module sharing one instance label.
   The container uniqueness rule is about the instance label, not the module
   kind, so a frame module and a single module that fold to one label clash.
   Expected: strict syntax-check fails at stage "validation" (SL-V004). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

SUBMODULES
   Shared Invocation
      ( 0.1 , 0.1 , 0.0 , 0.3 , 0.3
       ) : MODULEDEFINITION DateCode_ 2
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*Shared*);

   Shared Invocation
      ( 0.5 , 0.1 , 0.0 , 0.3 , 0.3
       ) : MODULEDEFINITION DateCode_ 3 (Frame_Module)
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*Shared*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
