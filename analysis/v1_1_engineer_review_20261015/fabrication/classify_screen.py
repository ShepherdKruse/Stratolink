from pathlib import Path
import argparse,json
from shapely import make_valid
from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union
p=argparse.ArgumentParser();p.add_argument('--copper',type=Path,required=True);p.add_argument('--screen',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();D=json.loads(a.copper.read_text());S=json.loads(a.screen.read_text());assert D['pcb_sha256']==S['source_sha256']
I=[dict(i,g=unary_union([make_valid(Polygon(p['shell'],p['holes']))for p in i['polygons']]))for i in D['items']]
R=[]
for layer,entry in S['layers'].items():
 for kind in ['acute_gap_candidates','sharp_tip_candidates','small_enclosed_gap_candidates','tiny_copper_components']:
  for c in entry[kind]:
   point=Point(c['at_mm']);near=[]
   for i in I:
    if i['layer']!=layer:continue
    distance=i['g'].distance(point)
    if distance<.025:near.append({k:v for k,v in i.items()if k not in['g','polygons']}|{'distance_mm':distance})
   R.append({'layer':layer,'kind':kind,'feature':c,'near_items':near})
a.output.write_text(json.dumps({'pcb_sha256':D['pcb_sha256'],'features':R},indent=2)+'\n')
for r in R:print(r['layer'],r['kind'],r['feature']['at_mm'],[(i['kind'],i['net'],i.get('ref'),i.get('pin'),i['uuid'])for i in r['near_items']])
