#!/usr/bin/env python3
"""Bounded top-GNSS copper cleanup plan, source geometry remains immutable."""
from pathlib import Path
import json,argparse
from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union
p=argparse.ArgumentParser();p.add_argument('--items',type=Path,required=True);p.add_argument('--screen',type=Path,required=True);p.add_argument('--flecks',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
items=json.loads(a.items.read_text());screen=json.loads(a.screen.read_text());flecks=json.loads(a.flecks.read_text());assert items['pcb_sha256']==screen['source_sha256']==flecks['pcb_sha256']
def polys(g):return [g] if g.geom_type=='Polygon' else [x for x in getattr(g,'geoms',[]) if x.geom_type=='Polygon']
def geom(rows):return unary_union([Polygon(q['shell'],q['holes']).buffer(0) for q in rows])
by={}
for i in items['items']:
 if i['net']:by.setdefault((i['layer'],i['net']),[]).append(geom(i['polygons']))
by={k:unary_union(v) for k,v in by.items()};patches=[];holes=[]
for layer,checks in screen['layers'].items():
 for index,t in enumerate(checks['acute_gap_candidates']):
  pt=Point(t['at_mm']);keys=[k for k,g in by.items() if k[0]==layer and g.distance(pt)<.002];assert len(keys)==1,keys
  k=keys[0];g=by[k];delta=g.buffer(.075,quad_segs=32).buffer(-.075,quad_segs=32).difference(g).intersection(pt.buffer(.45,quad_segs=32));delta=unary_union([q for q in polys(delta) if q.area>1e-8 and q.distance(pt)<.045]);assert not delta.is_empty
  patch=delta.union(g.intersection(delta.buffer(.015,quad_segs=16))).simplify(.0002,preserve_topology=True);assert patch.area<.3
  for n,q in enumerate(polys(patch)):
   assert not q.interiors;patches.append(dict(id=f'top-gnss-acute-{layer}-{index}-{n}',net=k[1],layer=layer,at=t['at_mm'],points=list(q.exterior.coords)[:-1],planned_added_area_mm2=delta.area))
for i,c in enumerate(flecks['components']):
 if c['area_mm2']<1e-8:continue
 assert len(c['source_items'])==1 and c['source_items'][0]['kind']=='zone'
 uid=c['source_items'][0]['uuid'];z=next(q for q in items['items'] if q['uuid']==uid);main=unary_union([q for q in polys(geom(z['polygons'])) if q.area>.001]);hole=box(*c['bounds_mm']).buffer(.01,join_style=2);assert main.distance(hole)>.4
 holes.append(dict(zone_uuid=uid,layer=c['layer'],points=list(hole.exterior.coords)[:-1],original_fleck_area_mm2=c['area_mm2'],original_fleck_bounds_mm=c['bounds_mm'],source_zone_main_copper_distance_mm=main.distance(hole)))
# Native refill tessellation can regenerate a nearby fleck along the same curve.
# Combine this one local cluster; its zone has no connected main copper here.
cluster=[q for q in holes if q['layer']=='B.Cu' and 58.6<q['original_fleck_bounds_mm'][0]<58.8]
assert len(cluster)==3
zone_uid=cluster[0]['zone_uuid'];z=next(q for q in items['items'] if q['uuid']==zone_uid)
main=unary_union([q for q in polys(geom(z['polygons'])) if q.area>.001]);cut=box(58.62,44.15,58.83,44.49);assert main.distance(cut)>1.5
holes=[q for q in holes if q not in cluster]
holes.append(dict(zone_uuid=zone_uid,layer='B.Cu',points=list(cut.exterior.coords)[:-1],original_flecks=cluster,source_zone_main_copper_distance_mm=main.distance(cut),reason='Bounded common clearance region prevents adjacent tessellation fragments regenerating after refill. Does not change other zones or global policy.'))
patches=[q for q in patches if q['at']!=[64.6,39.354079]]
zone_boundaries=[{'zone_uuid': 'b060d665-6e67-589e-a64a-b45127609817', 'layer': 'B.Cu', 'before': [[57, 30], [64.6, 30], [64.6, 46.4], [57, 46.4]], 'after': [[57, 30], [63.5, 30], [63.5, 34.2], [62.6, 34.2], [62.6, 46.4], [57, 46.4]], 'reason': 'Exclude full inherited 0.5 mm thermal neighborhoods of C1/C2/R2 from new solid RF zone; R25 remains intentionally solid for RF reference.'}]
a.output.write_text(json.dumps(dict(source_sha256=items['pcb_sha256'],patches=patches,zone_holes=holes,zone_boundaries=zone_boundaries,ignored_subgrid_components=[c for c in flecks['components'] if c['area_mm2']<1e-8],method='75 um local closing radius, 15 um overlap for three rounded same-net copper junctions; fourth original acute gap removed by the thermal-preserving RF-zone boundary trim; Local source-zone cutouts for seven disconnected saved-fill fragments, with one combined three-fragment cluster. No global zone policy change.'),indent=2)+'\n');print(len(patches),'patches',len(holes),'zone holes')
