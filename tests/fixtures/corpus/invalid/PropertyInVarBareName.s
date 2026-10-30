"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: PropertyInVarBareName"
(* Covers InVar_/OutVar_ tails on object property assignments.
   Proved 2026-10-05 by running EdgePropEnableInvar.x through the real editor:
   "Error on line 21: DefineSym Expected" at the bare `Flag`. After the
   InVar_/OutVar_ prefix the tool consumes a DefineSym, so only a literal or
   a quoted symbol is legal there -- a bare identifier is rejected.
   The same asymmetry existed for coordinate tails and is covered by
   CoordInVarTail.s; this fixture covers the property-tail position, where the
   grammar previously still allowed a bare NAME via `connected_variable`.
   Expected: rejected by the parser.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Flag: boolean := False;
   PanelX: real  := 0.1;

ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   GraphObjects :
      RectangleObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )
         Enable_ = True : InVar_ Flag

   ModuleCode
      EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
         PanelX = PanelX + 0.01;

ENDDEF (*BasePicture*);
