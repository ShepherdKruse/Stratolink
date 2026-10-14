#!/usr/bin/env python3
"""Bounded same-net copper closing at independently classified reentrant joins."""
from pathlib import Path
import json,sys,hashlib
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
HERE=Path(__file__).resolve().parent
root=Path('/Users/twarn/Repositories/ai-working/scratch/stratolink-peer-review-20261014/fabrication')
d=json.loads((root/'copper-fix/items.json').read_text())
def ps(g):return [g] if g.geom_type=='Polygon' else [x for x in getattr(g,'geoms',[]) if x.geom_type=='Polygon']
by={}
for i in d['items']:
 k=(i['layer'],i['net']);by.setdefault(k,[]).extend(Polygon(p['shell'],p['holes']) for p in i['polygons'])
by={k:unary_union(v) for k,v in by.items()}
full=json.loads((HERE/'current-geometry.json').read_text())
# PCB_TEXT TransformShapeToPolygon returns its bounding rectangle. The native
# full-layer conversion contains the actual rendered glyph outlines.
for i in json.loads((HERE/'artwork-geometry.json').read_text())['items']:
 if i['kind']=='PCB_TEXT':by[(i['layer'],'ART:'+i['uuid'])]=unary_union([Polygon(p['shell'],p['holes']) for p in full['copper'][i['layer']]])
targets=[]
for t in json.loads((HERE/'all-candidate-classification.json').read_text()):
 if t['kind']!='acute_gap_candidates':continue
 if t['graphics']:
  assert len(t['graphics'])==1
  targets.append(dict(id=t['id'],at=t['at_mm'],net='ART:'+t['graphics'][0]['uuid'],layer=t['layer']))
  continue
 nets=set(x['net'] for x in t['nearest_electrical_items'] if x['distance_mm']<.002)
 if len(nets)!=1:continue
 targets.append(dict(id=t['id'],at=t['at_mm'],net=nets.pop(),layer=t['layer']))
# Retain the remaining closed slits and artwork hole as explicit targets.
targets.extend([dict(id='ground-crescent-tail',at=[70.203592,62.864835],net='GND',layer='F.Cu'),dict(id='rear-ground-hairline',at=[75.064417,80.940702],net='GND',layer='B.Cu')])
cache={};patches=[];results=[]
for t in targets:
 k=(t['layer'],t['net']);g=by[k];p=Point(t['at']);radius=.075
 if k not in cache:
  closed=g.buffer(radius,quad_segs=32).buffer(-radius,quad_segs=32)
  cache[k]=closed.difference(g)
 delta=cache[k].intersection(p.buffer(.45,quad_segs=32))
 # Keep only the concavity at this coordinate. Avoid unrelated nearby corners.
 parts=[q for q in ps(delta) if q.area>1e-8 and q.distance(p)<.045]
 if not parts:
  results.append(dict(**t,status='already absent or below threshold'));continue
 delta=unary_union(parts)
 # Extend only into existing same-net copper; no added clearance penalty.
 patch=delta.union(g.intersection(delta.buffer(.015,quad_segs=16))).simplify(.0002,preserve_topology=True)
 assert patch.area<.3,(t,patch.area)
 for j,q in enumerate(ps(patch)):
  assert not q.interiors,(t,'unexpected interior')
  patches.append(dict(**t,sub=j,radius_mm=radius,added_area_mm2=delta.area,points=list(q.exterior.coords)[:-1]))
 results.append(dict(**t,status='fillet planned',radius_mm=radius,added_area_mm2=delta.area,patch_area_mm2=patch.area))
out=dict(source_sha256=d['pcb_sha256'],method='75um radius closing; local .45mm window, concavity must touch within45um of classified point; patches overlap only existing same-net copper by15um. Coordinates rounded to1nm on CAD insertion. Not an EMI or etchant simulation.',patches=patches,targets=results)
(root/(sys.argv[1] if len(sys.argv)>1 else 'copper-final')/'fillet-plan.json').write_text(json.dumps(out,indent=2)+'\n')
print(len(patches),'patches');print(json.dumps(results,indent=2))
