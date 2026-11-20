"Syntax version 2.23, date: 2026-11-20-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-20-12:00:00.000, name: StaleMappingTarget"
(* EDGE: A parameter mapping whose target is not a formal parameter.
   SattLine keeps an instance mapping when its formal parameter is deleted from
   the definition, so the clause is inert. Neither the removed target nor its
   source is reported, even when the source name is undeclared.
   The module type declares Gain only, and the instance maps Absent.
   Expected: strict syntax-check passes. *)

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
      Absent => NoSuchVariable);

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
