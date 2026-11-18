"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: StaleMappingTarget"
(* INVALID: A parameter mapping whose target is not a formal parameter.
   The module type declares Gain only, and the instance maps Absent. A formal
   that was removed from the definition leaves exactly this stale mapping, so
   the finding names the resolved definition rather than the instance alone.
   Expected: strict syntax-check fails at stage "validation". *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

TYPEDEFINITIONS
   GainType = MODULEDEFINITION DateCode_ 1
   MODULEPARAMETERS
      Gain: real  := 1.0;
   LOCALVARIABLES
      Output: real  := 0.0;

   ModuleDef
   ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
   ModuleCode
   EQUATIONBLOCK GainEq COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Output = Gain;

   ENDDEF (*GainType*);

LOCALVARIABLES
   LocalGain: real  := 0.5;

SUBMODULES
   GainBlock Invocation
      ( 0.1 , 0.1 , 0.0 , 0.8 , 0.8
       ) : GainType (
      Absent => LocalGain);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
