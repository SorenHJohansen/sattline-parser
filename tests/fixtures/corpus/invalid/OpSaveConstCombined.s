"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: OpSaveConstCombined"
(* INVALID: OpSave combined with Const, in that order.

   Proved 2026-10-05 (OpSaveConst.x) - the real tool emits
     "illegal attribute mix"
   for `OpSave Const`, the same error it gives `OpSave State`, which is
   covered by invalid/OpSaveAndStateCombined.s.

   Note the order matters: `State OpSave` (the reversed spelling) is ACCEPTED
   by the tool and is pinned by valid/VariableModifiers.s. The grammar checks
   the recorded attribute order, not the set of modifiers.

   Expected: strict syntax-check passes.
   Expected: SL-V031. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Base: integer  := 0;
   Mirror: integer  OpSave := 0;
   Mixed: integer  OpSave Const := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Base = Mirror;
      Base = Mixed;

ENDDEF (*BasePicture*);
