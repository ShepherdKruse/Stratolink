from pathlib import Path
import json,gzip,csv
from collections import Counter
from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union
H=Path(__file__).resolve().parent;d=json.loads(gzip.decompress((H/'native-audit.json.gz').read_bytes()))
def shape(ps):return unary_union([Polygon(p['shell'],p['holes']) for p in ps if len(p['shell'])>=3])
items=[dict(i,geometry={l:shape(ps) for l,ps in i['polygons'].items() if ps}) for i in d['items']]
pth={p['key']:p for p in d['pth']};boundary=shape(d['outline']).boundary
for p in d['pth']:
 p['annulus_min_mm']=(min(p['size_mm'])-max(p['drill_mm']))/2
 p['functional_class']='thermal via encoded as footprint PTH' if p['key'].startswith('U1.') else 'component/wire/structure PTH'
 p['outer_shape']='rectangle' if p['shape']==1 else 'circle' if p['size_mm'][0]==p['size_mm'][1] else 'noncircular'
 assert p['offset_mm']==[0,0]
summary=[];detail={}
for land in [.85,.88,.90,1.00]:
 trial=[]
 for i in items:
  j=dict(i);j['geometry']=dict(i['geometry'])
  if i.get('key','').startswith(('J3.','J4.')):
   p=pth[i['key']];x,y=p['at_mm'];g=box(x-land/2,y-land/2,x+land/2,y+land/2) if p['shape']==1 else Point(x,y).buffer(land/2,quad_segs=512)
   for l in j['geometry']:j['geometry'][l]=g
  trial.append(j)
 rows=[]
 for p in d['pth']:
  if not p['key'].startswith(('J3.','J4.')):continue
  me=next(i for i in trial if i.get('key')==p['key']);hole=Point(p['at_mm']).buffer(.25,quad_segs=512)
  row=dict(key=p['key'],uuid=p['uuid'],at_mm=p['at_mm'],net=p['net'],drill_mm=.5,land_mm=land,annulus_mm=(land-.5)/2,layers={})
  for l in ['0','2']:
   g=me['geometry'][l]
   foreign=[i for i in trial if l in i['geometry'] and i['net']!=me['net'] and i['kind']!='zone']
   def nearest(kind):
    opts=[( (hole if kind=='drill' else g).distance(i['geometry'][l]),i.get('key',i['uuid']),i['kind']) for i in foreign]
    v=min(opts);return dict(clearance_mm=v[0],other=v[1],kind=v[2])
   tracks=[i for i in foreign if i['kind'] in ['track','via']]
   tr=min((g.distance(i['geometry'][l]),i['uuid'],i['kind']) for i in tracks)
   row['layers'][l]=dict(copper_to_foreign=nearest('copper'),drill_to_foreign=nearest('drill'),mask_to_foreign_track_mm=tr[0],nearest_foreign_track_uuid=tr[1],copper_to_outline_mm=g.distance(boundary))
  rows.append(row)
 detail[str(land)]=rows
 summary.append(dict(land_mm=land,drill_mm=.5,annulus_mm=(land-.5)/2,min_adjacent_copper_mask_gap_mm=min(v['copper_to_foreign']['clearance_mm'] for r in rows for v in r['layers'].values()),min_drill_to_foreign_copper_mm=min(v['drill_to_foreign']['clearance_mm'] for r in rows for v in r['layers'].values()),min_copper_to_outline_mm=min(v['copper_to_outline_mm'] for r in rows for v in r['layers'].values()),min_mask_to_foreign_track_mm=min(v['mask_to_foreign_track_mm'] for r in rows for v in r['layers'].values())))
result=dict(baseline=d['baseline'],native_polygon_tolerance_mm=.0001,modeled_circle_tolerance_mm=.000001,component_PTH_inventory=d['pth'],via_count=len(d['vias']),via_geometry_counts=[dict(diameter_mm=k[0],drill_mm=k[1],annulus_mm=(k[0]-k[1])/2,count=v) for k,v in Counter((x['diameter_mm'],x['drill_mm']) for x in d['vias']).items()],header_candidate_summary=summary,header_details=detail,notes=['Header mask margins currently zero; modeled mask uses exactly copper aperture size.','Keeps installed routing: integrated edge candidate has separately reviewed trace changes.','Closest-foreign distances exclude same-net copper and zone fill; candidate refill preserves clearance.','U1.22-.26 are BQ25570 thermal vias embedded in a footprint, not component insertion holes.','Pin1 square shape preserved; remaining equal-axis oval pads are geometrically circular.'])
(H/'geometry-audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(summary,indent=2));print('Vias:',result['via_geometry_counts'])
