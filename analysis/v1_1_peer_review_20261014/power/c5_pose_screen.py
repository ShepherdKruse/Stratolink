#!/usr/bin/env python3
"""Independent, conservative XY pose alternatives; does not edit CAD."""
from pathlib import Path
import json,hashlib
from shapely.geometry import Polygon,box
from shapely.ops import unary_union
HERE=Path(__file__).resolve().parent;BASE=HERE.parent
rf=json.loads((BASE/'rf/native-rf-geometry.json').read_text());native=json.loads((BASE/'fabrication/current-geometry.json').read_text())
def union(rows):return unary_union([Polygon(p['shell'],p['holes']) for p in rows])
outline=union(native['outline']);rows=[]
for dx,dy in [(0,0),(2.3,0),(2,0),(1.8,0),(0,1.2),(0,1.25),(0,1.4),(0,1.8)]:
 body=box(57.625+dx,49.457+dy,72.125+dx,79.957+dy)
 nearest=[]
 for i in rf['items']:
  if i['kind']!='pad' or i['layer']!='B.Cu' or i['ref']=='C5':continue
  g=union(i['polygons']);gap=body.distance(g)
  if gap<1.0:nearest.append(dict(ref=i['ref'],pin=i['pin'],net=i['net'],gap_mm=gap,overlap_mm2=body.intersection(g).area))
 # AE1's wire/solder envelope is retained at1.25mm inboard from its feed.
 rows.append(dict(dx_mm=dx,dy_mm=dy,maximum_case_bounds_mm=list(body.bounds),inside_outline=outline.covers(body),case_to_outline_mm=body.distance(outline.boundary),near_rear_pads=sorted(nearest,key=lambda x:x['gap_mm']),case_to_AE1_courtyard_inboard_y_margin_mm=81.453-body.bounds[3],C5_positive_land_top_y_mm=44.457+dy,C5_positive_land_to_U3_RF_pad_Y_gap_mm=44.457+dy-45.514))
out={'status':'Prospective geometry only; final candidate must be independently checked','source_pcb_sha256':rf['pcb_sha256'],'source_dimensions':'CAP-XX DMF4B5R5G105M3DTA0 Rev1.9 p2, visually verified:30±0.5mm×14±0.5mm,4.0mmmaxthickness,34.5mmmaxtotalincludingtabs. Fixedcasecenterdatum and symmetric±0.25mm envelope assumed; no extra placement/solder allowance.','variants':rows,'constraints':['A positive2Dgap is not a solder-access or retention qualification.','Case insulation and actual standoff are unspecified by these projections.','AE1courtyard is a reserved solder/wire envelope, not measured solid material.','IncreasingXretainslowerantenna/Yaccess; increasingYmovescaseclosertolowerantennaassembly.']}
(HERE/'c5-pose-screen.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out,indent=2))
