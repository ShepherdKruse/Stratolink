#!/usr/bin/env python3
"""Conservative projected mechanical review from hash-bound native geometry."""
from pathlib import Path
import json,sys
from shapely.geometry import Polygon,Point,box,LineString
from shapely.ops import unary_union
H=Path(__file__).resolve().parent;ROOT=H.parents[2];sys.path.insert(0,str(ROOT/'hardware/pcb/3d/solar'));import generate as solar
j=json.loads((H/'rf-assembly-native.json').read_text());u=lambda rows:unary_union([Polygon(p['shell'],p['holes']) for p in rows]);outline=u(j['outline']);f=j['footprints'];a=next(p for p in j['pads']if p['ref']=='AE2');origin=Point(a['at']);c5=f['C5']['at'];body=box(c5[0]-7.25,c5[1]-15.25,c5[0]+7.25,c5[1]+15.25)
near=[]
for p in j['pads']:
 if p['layer']!='B.Cu' or p['ref']=='C5':continue
 g=u(p['polygons']);gap=body.distance(g)
 if gap<1:near.append(dict(ref=p['ref'],pin=p['pin'],net=p['net'],max_case_gap_mm=gap,projected_overlap_mm2=body.intersection(g).area))
assert f['AE2']['angle']==180
model=j['models']['AE2'][0];assert model['offset']==[0.0,-.2,.25] and model['rotation']==[-90.0,0.0,-90.0]
# Native VRML export independently verified full rotation maps model+Z to world-X.
# KiCad footprint origin is at y47.85; retained model offset shifts centerline -.20Y.
wire_y=f['AE2']['at'][1]-.2;wire_start=[f['AE2']['at'][0],wire_y];wire_end=[wire_start[0]-48,wire_y];r=.1605;z=.2+.25
parts=[]
for sign,ref,inner in [(-1,'J2',54.8),(1,'J1',75.2)]:
 x,y=f[ref]['at'];m,_=solar.build(sign,inner-x)
 for name,verts,faces,material in m.parts:
  pts=[(q[0]+x,q[1]+y,q[2])for q in verts];parts.append(dict(ref=ref,name=name,bounds=[min(p[i]for p in pts)for i in range(3)]+[max(p[i]for p in pts)for i in range(3)],wire_y_gap_lower_bound_mm=min(p[1]for p in pts)-wire_y-r))
solder=[]
for p in j['pads']:
 if p['ref']in['FB1','C10','D3'] and p['layer']=='F.Cu':solder.append(dict(ref=p['ref'],pin=p['pin'],land_to_AE2_land_mm=u(p['polygons']).distance(u(a['polygons'])),assumed_R1p25_solder_envelope_gap_mm=u(p['polygons']).distance(origin)-1.25))
report=dict(source_sha256=j['sha256'],C5_center_mm=c5,C5_max_case_bounds_mm=list(body.bounds),C5_case_inside_board=outline.covers(body),C5_case_to_outline_mm=body.distance(outline.boundary),C5_case_to_rear_pads=near,C5_max_case_to_lower_AE1_courtyard_y_mm=81.453-body.bounds[3],AE2_origin_mm=a['at'],AE2_hole_diameter_mm=1,AE2_land_diameter_mm=1.5,AE2_annular_ring_mm=.25,AE2_hole_edge_to_outline_ligament_mm=origin.distance(outline.boundary)-.5,AE2_land_to_outline_mm=u(a['polygons']).distance(outline.boundary),AE2_solder_screen=solder,GNSS_wire_nominal_centerline_start_mm=wire_start+[z],GNSS_wire_nominal_centerline_end_mm=wire_end+[z],GNSS_wire_model_radius_mm=r,GNSS_wire_model_to_board_top_z_mm=z-r-.2,GNSS_wire_to_solar_assembly_y_lower_bound_mm=min(p['wire_y_gap_lower_bound_mm']for p in parts),GNSS_wire_to_upward_bridle_y_lower_bound_mm=wire_y-max(f[h]['at'][1]for h in ['H1','H2'])-r,solar_mesh_parts=parts,limitations=['Manufacturer body tolerance is included; additional hand placement, solder bulges and capacitor case insulation/standoff are unqualified.','AE2 R1.25 mm solder envelope is a chosen assembly allowance, not a measured fillet. Nominal .321 mm wire diameter and .25 mm model offset are unmeasured.','Static mesh gaps do not bound flexible-panel motion, loose suspension loops, knots or wire deflection.','Hole ligament geometry is not a pull/bend qualification for the .4 mm PCB; avoid using the 48 mm wire as a lever during assembly.'])
(H/'rf-assembly-review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='solar_mesh_parts'},indent=2))
