"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: AmbiguousDatatypeTypo"
(* INVALID: A datatype name that is equally close to two built-in names.
   "magstring" is one edit from both "maxstring" and "tagstring", so there is no
   single suggestion to offer. The typo rule stays silent and the unknown-name
   rule reports the declaration instead.
   Expected: strict syntax-check fails at stage "validation". *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Counter: magstring  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )

ENDDEF (*BasePicture*);
