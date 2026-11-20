"Syntax version 2.23, date: 2026-11-20-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-20-12:00:00.000, name: SfcMappingSource"
(* EDGE: SFC control accessors resolve program-wide.
   The sequence lives in a sibling module. The equation block reads .Reset on it,
   and the mapping tail reads .Reset, .Hold, and .Disable on the same sequence.
   The accessors are available because the sequence enables SeqControl, and an
   unresolved mapping source would not be reported in any case.
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   ChildType = MODULEDEFINITION DateCode_ 1
   MODULEPARAMETERS
      ResetFlag, HoldFlag, DisableFlag: boolean  := False;

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ENDDEF (*ChildType*);

LOCALVARIABLES
   Running: boolean  := False;

SUBMODULES
   Producer Invocation
      ( 0.1 , 0.1 , 0.0 , 0.4 , 0.4
       ) : MODULEDEFINITION DateCode_ 2

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   SEQUENCE StateSequence (SeqControl) COORD 0.0, 0.0 OBJSIZE 1.0, 1.0
      SEQINITSTEP Init
      SEQTRANSITION TrDone WAIT_FOR True
   ENDSEQUENCE
   ENDDEF (*Producer*);

   Consumer Invocation
      ( 0.5 , 0.1 , 0.0 , 0.4 , 0.4
       ) : ChildType (
      ResetFlag => StateSequence.Reset,
      HoldFlag => StateSequence.Hold,
      DisableFlag => StateSequence.Disable);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
EQUATIONBLOCK Watch COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
   Running = StateSequence.Reset;

ENDDEF (*BasePicture*);
