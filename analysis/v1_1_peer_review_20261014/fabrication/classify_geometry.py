from pathlib import Path
import json
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
HERE=Path(__file__).resolve().parent;d=json.loads((HERE.parent/'rf/native-rf-geometry.json').read_text());screen=json.loads((HERE/'geometry-screen.json').read_text());items=[]
for i in d['items']:
 if i['kind']=='zone':continue
 items.append((i,unary_union([Polygon(p['shell'],p['holes']) for p in i['polygons']])))
rows=[]
for layer,features in screen['current']['layers'].items():
 for kind in ['acute_gap_candidates','small_enclosed_gap_candidates','tiny_copper_components']:
  for f in features[kind]:
   if kind=='acute_gap_candidates' and f['near_same_kind_flown_feature_within_0p1mm']:continue
   pt=Point(f['at_mm']);near=[]
   for i,g in items:
    if i['layer']!=layer:continue
    dist=g.distance(pt)
    if dist<.20:near.append({'distance_mm':dist,**{k:i[k] for k in ['kind','ref','pin','net','uuid'] if k in i}})
   near.sort(key=lambda x:x['distance_mm']);rows.append({'layer':layer,'kind':kind,**f,'nearest_electrical_items':near[:6]})
(HERE/'geometry-classification.json').write_text(json.dumps(rows,indent=2)+'\n')
for f in rows:print(f['layer'],f['kind'],f['at_mm'],[(i.get('ref'),i.get('pin'),i['net'])for i in f['nearest_electrical_items'][:3]])
