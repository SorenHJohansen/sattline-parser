"Syntax version 2.23, date: 2026-11-20-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-20-12:00:00.000, name: SiblingLabelAcrossKinds"
(* EDGE: Sibling submodules sharing one label in different declaration scopes.
   A module-type instance is scoped by its module type, so two instances of
   different types may share a label. A single module and a frame module are
   scoped by kind, so the container may hold one of each under the same label.
   Only siblings that share a label and a scope clash.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   ChildType = MODULEDEFINITION DateCode_ 1
   MODULEPARAMETERS
      Value: integer  := 0;

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*ChildType*);

   OtherType = MODULEDEFINITION DateCode_ 2
   MODULEPARAMETERS
      Value: integer  := 0;

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*OtherType*);

SUBMODULES
   Shared Invocation
      ( 0.1 , 0.1 , 0.0 , 0.3 , 0.3
       ) : ChildType (
      Value => 1);

   Shared Invocation
      ( 0.5 , 0.1 , 0.0 , 0.3 , 0.3
       ) : OtherType (
      Value => 2);

   Shared Invocation
      ( 0.1 , 0.5 , 0.0 , 0.3 , 0.3
       ) : MODULEDEFINITION DateCode_ 3
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*Shared*);

   Shared Invocation
      ( 0.5 , 0.5 , 0.0 , 0.3 , 0.3
       ) : MODULEDEFINITION DateCode_ 4 (Frame_Module)
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*Shared*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
