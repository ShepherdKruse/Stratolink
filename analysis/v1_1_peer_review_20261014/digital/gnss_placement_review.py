#!/usr/bin/env python3
"""Independent prospective module-envelope review; reads saved baseline only."""
from pathlib import Path
import json,hashlib
from shapely.geometry import Polygon,Point,box,LineString
from shapely.ops import unary_union
H=Path(__file__).resolve().parent;R=H.parent/'rf'
d=json.loads((R/'native-rf-geometry.json').read_text());pose=json.loads((R/'placement-high-native.json').read_text())
def g(rows):return unary_union([Polygon(p['shell'],p['holes'])for p in rows])
assert pose['rotated_u3']['at']==[59.45,39.8]
# Figure4/Table21: centered core Amax10.7,Bmax9.8. Figure's extra P tab
# is +x after90degrotation; its position varies. Conservative full-side envelope.
body=box(54.1,34.9,64.8,44.7);tabenv=box(54.1,34.9,65.4,44.7)
nominal=box(54.4,34.95,64.8,44.65)
items=[(i,g(i['polygons']))for i in d['items']]
holes=[]
for ref in ['H1','H2']:
 i,cu=next((i,p)for i,p in items if i.get('ref')==ref and i['layer']=='F.Cu')
 pt=Point(i['at']);drill=pt.buffer(i['drill'][0]/2)
 holes.append({'ref':ref,'center_mm':i['at'],'copper_bounds_mm':list(cu.bounds),'drill_diameter_mm':i['drill'][0],'max_body_tab_to_ring_mm':tabenv.distance(cu),'max_body_tab_to_drill_mm':tabenv.distance(drill)})
# Rear copper projection and reference coverage, independent of front rerouting.
rear={};under=[]
for i,p in items:
 if i['layer']!='B.Cu':continue
 if i['kind']=='zone':continue
 cut=p.intersection(body)
 if cut.area>1e-8:
  rear.setdefault(i['net'],[]).append(cut)
  if i['kind']=='pad':under.append({k:i[k]for k in ['ref','pin','net','uuid']}|{'projected_area_mm2':cut.area})
rear={net:unary_union(parts).area for net,parts in rear.items()}
gnd=g([p for i,_ in items if i['layer']=='B.Cu'and i['net']=='GND'for p in i['polygons']])
frontcontacts=[]
for i,p in items:
 if i['layer']!='F.Cu' or i['kind']!='pad'or i.get('ref')in['U3','D3','C10','FB1']:continue
 gap=tabenv.distance(p)
 if gap<.5:frontcontacts.append({k:i[k]for k in ['ref','pin','net','uuid']}|{'maxbody_tab_gap_mm':gap,'maxbody_tab_overlap_mm2':tabenv.intersection(p).area,'core_gap_mm':body.distance(p)})
u1vias=[]
for i,p in items:
 if i.get('ref')=='U1'and i.get('pin')=='21'and i['layer']=='F.Cu':u1vias.append({'uuid':i['uuid'],'at_mm':i['at'],'tab_envelope_copper_gap_mm':tabenv.distance(p)})
report={'source_sha256':d['pcb_sha256'],'pose_input_sha256':hashlib.sha256((R/'placement-high-native.json').read_bytes()).hexdigest(),'pose_mm':[59.45,39.8],'rotation_deg':90,'nominal_envelope_mm':list(nominal.bounds),'conservative_core_max_envelope_mm':list(body.bounds),'conservative_core_plus_variable_tab_envelope_mm':list(tabenv.bounds),'maximum_envelope_assumption':'Amax10.7 core centered on pad-row center; Bmax9.8; add Pmax0.6 beyond +x edge after90deg rotation, allowing tab location anywhere on that edge. Not a claim all maxima occur together.','holes':holes,'nearby_front_pads':frontcontacts,'U1_front_thermal_vias':u1vias,'baseline_rear_copper_projected_beneath_core_by_net_mm2':rear,'baseline_rear_pad_projections':under,'baseline_rear_ground_area_fraction_under_core':gnd.intersection(body).area/body.area,'limitations':['This is an in-memory prospective pose, not a routed board or assembly approval.','Opposite-face projected overlap is not a mechanical collision; it identifies potential coupling and heat sources.','No suspension-line diameter, knot dimensions, electrical emissions, actual receiver shield effectiveness, or production tab distribution were measured.','Ground coverage uses saved baseline copper and must be recomputed on the final routed/refilled candidate.']}
(H/'gnss-placement-independent.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items()if k not in ['baseline_rear_pad_projections','U1_front_thermal_vias']},indent=2))
