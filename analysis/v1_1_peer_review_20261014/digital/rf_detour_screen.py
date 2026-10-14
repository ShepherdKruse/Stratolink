#!/usr/bin/env python3
"""Independent projected copper screen of rejected route; not a routed/refilled candidate."""
from pathlib import Path
import json,hashlib
from shapely.geometry import Polygon,LineString
from shapely.ops import unary_union
HERE=Path(__file__).resolve().parent;src=HERE.parent/'rf/native-rf-geometry.json';d=json.loads(src.read_text())
path=LineString([(60.787001,45.114001),(59.5,45.114001),(58.1,43.714001),(58.1,41.2),(56.6,39.7),(56.6,35.4),(57.3,34.7),(59.3,34.7),(62.882,33.218)])
strip=path.buffer(.375)
def g(i):return unary_union([Polygon(p['shell'],p['holes']) for p in i['polygons']])
gnd=unary_union([g(i) for i in d['items'] if i['layer']=='B.Cu' and i['net']=='GND'])
pads=[]
for i in d['items']:
 if i['layer']=='B.Cu' and i.get('ref') in ['U8','R24','R25','R26','C22','C5']:
  x=g(i)
  if strip.distance(x)<.5:pads.append({'ref':i['ref'],'pin':i['pin'],'net':i['net'],'center_mm':i['at'],'projected_edge_clearance_mm':strip.distance(x),'projected_overlap_mm2':strip.intersection(x).area,'centerline_over_copper_mm':path.intersection(x).length})
report={'status':'Rejected exploratory path screen, no native candidate created','source_pcb_sha256':d['pcb_sha256'],'source_geometry_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'width_mm':.75,'route_length_mm':path.length,'path':list(path.coords),'baseline_rear_GND_centerline_gap_mm':path.difference(gnd).length,'baseline_rear_GND_trace_strip_coverage_fraction':strip.intersection(gnd).area/strip.area,'nearby_rear_pads':pads,'limit':'Projection against unchanged saved baseline fills only. Proposed SC_MID hop and ground-via removal are not instantiated; no complete final reference-plane, impedance or noise simulation.'}
(HERE/'rf-detour-screen.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
