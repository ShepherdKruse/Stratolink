#!/usr/bin/env python3
"""Report front guard widths on the actual receiver-connected ground component.
Detached flecks are reported separately, never counted as shielding or waived.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json
from shapely.ops import unary_union
p=argparse.ArgumentParser(description=__doc__)
for n in ['repo','geometry','output']:p.add_argument('--'+n,type=Path,required=True)
a=p.parse_args();assert not a.output.exists(),a.output
s=importlib.util.spec_from_file_location('reference_check',a.repo/'analysis/v1_1_peer_review_20261014/digital/check_rf_reference.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
d=json.loads(a.geometry.read_text());items=[dict(i,geometry=m.polygons(i['polygons']))for i in d['items']]
ground={l:unary_union([i['geometry']for i in items if i['net']=='GND'and i['layer']==l])for l in ['F.Cu','B.Cu']}
comps=[(l,g)for l in ground for g in m.parts(ground[l])];parent=list(range(len(comps)))
def find(n):
 while parent[n]!=n:parent[n]=parent[parent[n]];n=parent[n]
 return n
def join(ns):
 for n in ns[1:]:parent[find(n)]=find(ns[0])
paired={}
for i in items:
 if i['net']=='GND'and i['kind']in['pad','PCB_VIA']:paired.setdefault(i['uuid'],[]).append(i)
join_rows=[]
for uid,group in paired.items():
 if {i['layer']for i in group}!={'F.Cu','B.Cu'}:continue
 ns=[n for n,(l,g)in enumerate(comps)if any(i['layer']==l and i['geometry'].intersection(g).area>1e-8 for i in group)]
 join(ns);join_rows.append((uid,group,ns))
pads=[i for i in items if i.get('ref')=='U3'and i.get('pin')in['10','12']and i['layer']=='F.Cu'];assert len(pads)==2
roots={find(n)for n,(l,g)in enumerate(comps)if any(i['layer']==l and i['geometry'].intersection(g).area>1e-8 for i in pads)};assert len(roots)==1
rf=[i for i in items if i['net']=='Net-(AE2-A)'and i['layer']=='F.Cu'];traces=[i for i in rf if i['kind']in['PCB_TRACK','PCB_ARC','board_graphic']];trace=unary_union([i['geometry']for i in traces]);connected_front=unary_union([g for n,(l,g)in enumerate(comps)if l=='F.Cu'and find(n)in roots])
samples=m.lateral_samples(traces,[i for i in rf if i['kind']=='pad'],connected_front)
rows=[]
for uid,group,ns in join_rows:
 gap=min(i['geometry'].distance(trace)for i in group)
 if gap<=1.5:
  i=group[0];c=i['geometry'].centroid
  rows.append({'uuid':uid,'kind':i['kind'],'ref':i.get('ref'),'pin':i.get('pin'),'center_mm':[c.x,c.y],'edge_distance_to_rf_mm':gap,'connected_to_U3_ground':all(find(n)in roots for n in ns)})
r={'pcb_sha256':d['pcb_sha256'],'geometry_sha256':hashlib.sha256(a.geometry.read_bytes()).hexdigest(),'disconnected_ground_components':[{'layer':l,'area_mm2':g.area,'bounds_mm':list(g.bounds),'area_within_1mm_of_rf_mm2':g.intersection(trace.buffer(1)).area}for n,(l,g)in enumerate(comps)if find(n)not in roots],'nearby_plated_ground_joins':rows,'connected_ground_lateral':samples,'limits':['Widths are transverse sampled intervals, not a field simulation or impedance qualification.','Raw widths include native fill clearance/rounding. Nominal0.20mm geometry can report about0.199mm. No tolerance is silently applied.','Removing disconnected components for these width measurements does not approve the original flecks; they remain explicit cleanup findings.']}
a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({'disconnected_components':len(r['disconnected_ground_components']),'nearby_plated_ground_joins':len(rows),'connected_ground_lateral':samples['summary']},indent=2))
