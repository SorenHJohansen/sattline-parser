"Syntax version 2.23, date: 2026-11-15-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-15-12:00:00.000, name: SubmoduleScanGroup"
(* A submodule's own scan group is written after its datecode and before the body.
   The root header carries the same clause, and both must survive a round trip. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1 (GroupConn = RootGroup)

LOCALVARIABLES
   RootGroup: GLOBAL string  := "";
   NestedGroup: string  := "";

SUBMODULES
   Nested Invocation
      ( 0.2 , 0.2 , 0.0 , 0.4 , 0.4
       ) : MODULEDEFINITION DateCode_ 2 (GroupConn = GLOBAL NestedGroup)
   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*Nested*);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
