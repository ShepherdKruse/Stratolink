#!/usr/bin/env python3
"""Plan bounded RF-ECO concavity repairs from exact connected copper unions."""
from pathlib import Path
import json,sys
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
H=Path(__file__).resolve().parent;p=Path(sys.argv[1]);name=sys.argv[2]
items=json.loads((p/'items-rounded.json').read_text());screen=json.loads((H/(name+'-screen.json')).read_text());full=json.loads((H/(name+'-geometry.json')).read_text());assert items['pcb_sha256']==screen['source_sha256']==full['sha256']
def polys(g):return [g] if g.geom_type=='Polygon' else [x for x in getattr(g,'geoms',[]) if x.geom_type=='Polygon']
u=lambda rows:unary_union([Polygon(q['shell'],q['holes']).buffer(0) for q in rows]);by={}
for q in items['items']:
 if not q['net']:continue
 by.setdefault((q['layer'],q['net']),[]).append(u(q['polygons']))
by={k:unary_union(v) for k,v in by.items()}
patches=[];details=[];covered=[]
for layer,checks in screen['layers'].items():
 copper=u(full['copper'][layer]);empty=u(full['outline']).difference(copper)
 for i,t in enumerate(checks['small_enclosed_gap_candidates']):
  at=Point(t['at_mm']);found=[g for g in polys(empty) if g.covers(at) and g.area<.02];assert len(found)==1
  gap=found[0];assert abs(gap.area-t['area_mm2'])<.00001
  # The connected tiny empty-space component is used, never the outer copper
  # clearance cavity. This prevents the rejected earlier logo-fill selection bug.
  keys=[k for k,g in by.items() if k[0]==layer and g.distance(gap)<.002];assert len(keys)==1,keys
  k=keys[0];patch=gap.buffer(.008,quad_segs=16).simplify(.0001,preserve_topology=True);assert patch.area<.05
  for n,q in enumerate(polys(patch)):
   assert not q.interiors;patches.append(dict(id='rf-hole-'+layer+'-'+str(i),sub=n,net=k[1],layer=layer,points=list(q.exterior.coords)[:-1],added_area_mm2=gap.area))
  covered.append((layer,gap.buffer(.005)));details.append(dict(kind='hole',layer=layer,net=k[1],area=gap.area,bounds=list(gap.bounds)))
 for i,t in enumerate(checks['acute_gap_candidates']):
  at=Point(t['at_mm'])
  if any(l==layer and g.covers(at) for l,g in covered):continue
  keys=[k for k,g in by.items() if k[0]==layer and g.distance(at)<.002];assert len(keys)==1,(t,keys)
  k=keys[0];g=by[k];delta=g.buffer(.075,quad_segs=32).buffer(-.075,quad_segs=32).difference(g).intersection(at.buffer(.45,quad_segs=32))
  delta=unary_union([q for q in polys(delta) if q.area>1e-8 and q.distance(at)<.045]);assert not delta.is_empty
  patch=delta.union(g.intersection(delta.buffer(.015,quad_segs=16))).simplify(.0002,preserve_topology=True);assert patch.area<.3
  for n,q in enumerate(polys(patch)):
   assert not q.interiors;patches.append(dict(id='rf-acute-'+layer+'-'+str(i),sub=n,net=k[1],layer=layer,points=list(q.exterior.coords)[:-1],added_area_mm2=delta.area))
  details.append(dict(kind='fillet',at=t['at_mm'],layer=layer,net=k[1],added_area_mm2=delta.area))
(p/'rf-fillet-plan.json').write_text(json.dumps(dict(source_sha256=items['pcb_sha256'],patches=patches,details=details),indent=2)+'\n');print(json.dumps(details,indent=2))
