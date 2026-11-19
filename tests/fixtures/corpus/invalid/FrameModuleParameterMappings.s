"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: FrameModuleParameterMappings"
(* INVALID: Parameter mappings on a frame-module declaration are validated.
   The frame module declares Value: integer and takes three mappings: a
   boolean source, a duplicate target, and an absent formal.
   Expected: SL-V027, SL-V049, SL-V048. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Flag: boolean  := False;
   Count: integer  := 0;

SUBMODULES
   FrameA Invocation
      ( 0.1 , 0.1 , 0.0 , 0.3 , 0.3
       ) : MODULEDEFINITION DateCode_ 2 (Frame_Module)
   MODULEPARAMETERS
      Value: integer  := 0;
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*FrameA*) (Value => Flag, Value => Count, Missing => Count);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
