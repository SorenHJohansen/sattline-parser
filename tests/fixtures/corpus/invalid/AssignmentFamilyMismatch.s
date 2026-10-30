"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: AssignmentFamilyMismatch"
(* INVALID: an assignment moves a value across type classes.
   Probe ViolIntFromBool.x (2026-10-01) assigned a boolean to an integer and
   the real parser reported:
     Datatype error in assignment: Output = Flag1
   Probes confirmed that same-family assignment is accepted, including
   integer into real, so the rule rejects a differing type class rather than
   demanding an exact match.
   Expected: strict syntax-check fails at stage "validation" (SL-V029). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Output: integer  := 0;
   Flag1: boolean  := True;
   Label: identstring  := "x";
   Tag: tagstring  := "t";
   Span: time  := Time_Value "1984-01-01-00:00:00.000";
   DurFull: duration  := Duration_Value "0d0h5m0s0ms";

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Output = Flag1;
      Tag = Label;
      DurFull = Span;

ENDDEF (*BasePicture*);
