"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: DuplicateSiblingFrameModules"
(* INVALID: Two sibling frame modules with the same instance label.
   A frame module instance name is an instance label, not a resolvable symbol,
   so two frame modules in one container may not share it.
   Expected: strict syntax-check fails at stage "validation" (SL-V004). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

SUBMODULES
   FrameA Invocation
      ( 0.1 , 0.1 , 0.0 , 0.3 , 0.3
       ) : MODULEDEFINITION DateCode_ 2 (Frame_Module)
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*FrameA*);

   FrameA Invocation
      ( 0.5 , 0.1 , 0.0 , 0.3 , 0.3
       ) : MODULEDEFINITION DateCode_ 3 (Frame_Module)
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*FrameA*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
