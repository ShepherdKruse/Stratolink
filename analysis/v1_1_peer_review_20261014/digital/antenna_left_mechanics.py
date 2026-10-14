#!/usr/bin/env python3
"""Read-only nominal geometry screen of C5 shift and a left-pointing GNSS wire."""
from pathlib import Path
import sys,json,math,hashlib
from shapely.geometry import Polygon,Point,box,LineString
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[3];H=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'hardware/pcb/3d/solar'));import generate as solar
rf=json.loads((H.parent/'rf/native-rf-geometry.json').read_text());native=json.loads((H.parent/'fabrication/current-geometry.json').read_text())
g=lambda rows:unary_union([Polygon(p['shell'],p['holes'])for p in rows]);outline=g(native['outline'])
nominal=box(60.175,49.707,74.175,79.707);maximum=box(59.925,49.457,74.425,79.957)
assert outline.covers(maximum)
records=[]
for i in rf['items']:
 if i['kind']!='pad' or i['layer']!='B.Cu' or i.get('ref')=='C5':continue
 p=g(i['polygons']);dist=maximum.distance(p)
 if dist<1.0:records.append({k:i[k]for k in ['ref','pin','net','uuid']}|{'body_max_to_pad_gap_mm':dist,'body_max_pad_projection_overlap_mm2':maximum.intersection(p).area})
# y separation is a rigorous lower bound for all depicted mesh surfaces,
# independent of uncertain antenna height z. Nominal straight48mm wire along-x.
wire_start=(55.3,45.114);wire_end=(7.3,45.114);wire_radius=.321/2
parts=[]
for side,sign,x,notchx in [('left',-1,54.8-53.3165,53.3165),('right',1,75.2-76.6755,76.6755)]:
 model,_=solar.build(sign,x)
 for name,vertices,faces,material in model.parts:
  pts=[(p[0]+notchx,p[1]+54.5,p[2])for p in vertices]
  miny=min(p[1]for p in pts);maxy=max(p[1]for p in pts)
  parts.append({'side':side,'part':name,'bounds_mm':[min(p[0]for p in pts),miny,min(p[2]for p in pts),max(p[0]for p in pts),maxy,max(p[2]for p in pts)],'wire_to_part_y_separation_lower_bound_mm':miny-wire_start[1]-wire_radius})
# Purely geometric upward bridle legs: any apex y<=hole y keeps each leg above.
holes={ref:rf['footprints'][ref]['at']for ref in ['H1','H2']}
report={'status':'Prospective pose; final native candidate not yet supplied','source_sha256':rf['pcb_sha256'],'proposed_C5_translation_mm':[2.3,0],'nominal_C5_case_envelope_mm':list(nominal.bounds),'maximum_C5_case_envelope_mm':list(maximum.bounds),'C5_primary_dimensions':'CAP-XX DMF4B5R5G105M3DTA0 v1.9 Table3:30±0.5 by14±0.5mm, thicknessmax4.0mm; no added placement allowance.','maximum_case_inside_outline':True,'maximum_case_to_outline_boundary_mm':maximum.distance(outline.boundary),'rear_pad_near_maximum_case':records,'GNSS_wire_start_xy_mm':wire_start,'GNSS_wire_end_xy_mm':wire_end,'nominal_wire_diameter_mm':.321,'minimum_wire_to_modeled_solar_assembly_y_separation_mm':min(p['wire_to_part_y_separation_lower_bound_mm']for p in parts),'solar_parts':parts,'suspension_hole_centers_mm':holes,'wire_to_upward_bridle_y_separation_mm':wire_start[1]-max(p[1]for p in holes.values())-wire_radius,'limitations':['Static nominal assembly geometry only; does not bound panel flutter, wire deflection, loose string or knot envelope.','Solar envelope is photograph-scaled, film thickness/bend radius/menisci are unqualified modeling choices.','The antenna wire diameter has not been physically measured.','Closer parallel proximity to a conductive solar panel changes antenna loading; geometric clearance is not proof of RF performance.','The C5 case may project over exposed GND bank copper without physical panel contact; body insulation/standoff and solder-buildup must be verified before treating this as an assembly pass.','No CAD was changed.']}
(H/'antenna-left-mechanics.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items()if k!='solar_parts'},indent=2))
