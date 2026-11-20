"Syntax version 2.23, date: 2026-11-20-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-20-12:00:00.000, name: RepeatedMappingTarget"
(* EDGE: A repeated target keeps its first entry, and an absent target is inert.
   The first InletY mapping is live and its source is declared. The second
   InletY entry repeats the target, so it is discarded and its undeclared
   source is not checked. InletZ is not a formal parameter of the child, so
   that clause is inert as well.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   ChildType = MODULEDEFINITION DateCode_ 1
   MODULEPARAMETERS
      InletY: integer  := 0;

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*ChildType*);

LOCALVARIABLES
   InletY: integer  := 0;

SUBMODULES
   Child Invocation
      ( 0.1 , 0.1 , 0.0 , 0.8 , 0.8
       ) : MODULEDEFINITION DateCode_ 2

   MODULEPARAMETERS
      InletY: integer  := 0;

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*Child*) (
      InletY => InletY,
      InletY => InletZ,
      InletZ => InletZ);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
