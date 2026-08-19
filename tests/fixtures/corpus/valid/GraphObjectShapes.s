"Syntax version 2.23, date: 2026-08-19-12:00:00.000 N"
"Original file date: ---"
"Program date: 2026-08-19-12:00:00.000, name: GraphObjectShapes"
(* Covers the four non-rectangle graphic object shapes in GraphObjects:
   LineObject, OvalObject, PolygonObject, SegmentObject.
   PolygonObject takes a variable coordinate list; SegmentObject takes a
   separate endpoint coordinate after its origo/size pair.
   Expected: strict syntax-check passes; each shape keeps its type. *)

BasePicture Invocation
   ( 0.0 , 0.0 , 0.0 , 1.0 , 1.0
    ) : MODULEDEFINITION DateCode_ 1

ModuleDef
ClippingBounds = ( -1.0 , -1.0 ) ( 1.0 , 1.0 )
GraphObjects :
   LineObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )
   OvalObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 )
   PolygonObject ( -1.0 , 1.0 ) ( 0.0 , -1.0 ) ( 1.0 , 1.0 )
   SegmentObject ( -0.8 , 0.5 ) ( 0.8 , -0.5 ) ( 0.0 , 0.0 )

ENDDEF (*BasePicture*);
