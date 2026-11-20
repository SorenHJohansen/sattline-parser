"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: SiblingSameTypeDifferentLabels"
(* Edge case: two sibling module-type instances of one module type under
   different instance labels. The uniqueness rule is per label, not per
   module type, so this is clean. *)

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
   SensorA Invocation
      ( 0.1 , 0.1 , 0.0 , 0.3 , 0.3
       ) : ChildType (
      Value => 1);

   SensorB Invocation
      ( 0.5 , 0.1 , 0.0 , 0.3 , 0.3
       ) : ChildType (
      Value => 2);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
