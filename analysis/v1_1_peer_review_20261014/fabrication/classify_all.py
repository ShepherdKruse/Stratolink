from pathlib import Path
import json,math
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
HERE=Path(__file__).resolve().parent
screen=json.loads((HERE/'geometry-screen.json').read_text())['current']
items=json.loads((HERE.parent/'rf/native-rf-geometry.json').read_text())['items']
art=json.loads((HERE/'artwork-geometry.json').read_text())['items']
def geom(i):return unary_union([Polygon(p['shell'],p['holes']) for p in i['polygons']])
items=[(i,geom(i)) for i in items if i['kind']!='zone']
art=[(i,geom(i)) for i in art]
rows=[]
for layer,ld in screen['layers'].items():
 for kind in ['acute_gap_candidates','small_enclosed_gap_candidates','tiny_copper_components']:
  for n,f in enumerate(ld[kind]):
   pt=Point(f['at_mm']);graphics=[];electrical=[]
   for i,g in art:
    if i['layer']==layer and g.distance(pt)<.003:
     graphics.append({k:i[k] for k in ['kind','uuid','text']})
   for i,g in items:
    if i['layer']==layer and g.distance(pt)<.20:
     electrical.append({'distance_mm':g.distance(pt),**{k:i[k] for k in ['kind','ref','pin','net','uuid'] if k in i}})
   electrical.sort(key=lambda x:x['distance_mm'])
   rows.append({'id':layer+'-'+kind+'-'+str(n+1),'layer':layer,'kind':kind,**f,'graphics':graphics,'nearest_electrical_items':electrical[:6]})
(HERE/'all-candidate-classification.json').write_text(json.dumps(rows,indent=2)+'\n')
for r in rows:
 print(r['id'],r['at_mm'],'ART',[(x['kind'],x['text'])for x in r['graphics']],'ELEC',[(x.get('ref'),x.get('pin'),x['net'])for x in r['nearest_electrical_items'][:2]])
