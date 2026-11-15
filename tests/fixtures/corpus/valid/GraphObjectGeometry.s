"Syntax version 2.23, date: 2026-11-15-09:00:00.000 N"
"Original file date: ---"
"Program date: 2026-11-15-09:00:00.000, name: GraphObjectGeometry"
(* Covers the geometry a graph object can spell:
   - a PolygonObject with five coordinate pairs and a bound coordinate
   - a TextObject with Width_, ValueFraction, Format_String_, an alignment,
     a VarName label, and a ConnectionNode anchor
   Expected: strict syntax-check passes. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

LOCALVARIABLES
   LabelValue: real     := 0.0;
   LabelWidth: integer  := 6;
   LabelFormat: string  := "%g";
   PointToggle: boolean := True;

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   PolygonObject Polyline ( -0.9 , 0.9 )
      ( -0.5 , 0.9 ) ( 0.5 , 0.9 ) ( 0.5 , 0.4 : InVar_ "PointToggle" )
      ( -0.5 , 0.4 )
   TextObject ( -0.6 , 0.2 ) ( 0.6 , -0.2 )
      "LabelValue" VarName Width_ = 6 : InVar_ "LabelWidth"  ValueFraction = 2
      Format_String_ = "%g" : InVar_ "LabelFormat"  RightAligned
      ConnectionNode ( 0.6 , 0.2 )
      Enable_ = True : InVar_ "PointToggle"
ModuleCode
   EQUATIONBLOCK Main COORD 0.0, 0.0 OBJSIZE 1.0, 1.0 :
      LabelValue = LabelValue + 0.0;
      LabelWidth = LabelWidth + 0;

ENDDEF (*BasePicture*);
