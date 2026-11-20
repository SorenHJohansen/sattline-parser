"Syntax version 2.23, date: 2026-04-23-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-04-23-12:00:00.000, name: StringFamilyAssignment"
(* INVALID: a direct assignment to any native string family.
   The five string families share one copy rule: the value is moved with
   CopyString() or CopyVar(), never written with an assignment. The
   destination datatype decides the finding, so each of the five lines below
   reports SL-V045 and the copied form stays clean.
   Expected: strict syntax-check fails at stage "validation" (SL-V045). *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   Plain: string  := "";
   Ident: identstring  := "012345678912345";
   Tag: tagstring  := "t";
   Max: maxstring  := "m";
   Line: linestring  := "l";
   Source: string  := "";
   Status: integer  := 0;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      Plain = Source;
      Ident = Source;
      Tag = Source;
      Max = Source;
      Line = Source;
      CopyString(Plain, Source, Status);

ENDDEF (*BasePicture*);
