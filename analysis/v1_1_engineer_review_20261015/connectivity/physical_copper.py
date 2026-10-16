#!/usr/bin/env python3
"""Saved-copper connectivity graph joined only through actual plated pads/vias."""
from pathlib import Path
import argparse,json
from shapely import make_valid
from shapely.geometry import Polygon
from shapely.ops import unary_union
p=argparse.ArgumentParser();p.add_argument('--geometry',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();d=json.loads(a.geometry.read_text())
def polygons(g):
 if g.geom_type=='Polygon':return[g]
 if hasattr(g,'geoms'):return[p for child in g.geoms for p in polygons(child)]
 return []
def shape(i):return unary_union([make_valid(Polygon(p['shell'],p['holes']))for p in i['polygons']])
items=[dict(i,g=shape(i))for i in d['items']if i['net']]
results=[]
for net in sorted({i['net']for i in items}):
 ni=[i for i in items if i['net']==net];comps=[(layer,g)for layer in ['F.Cu','B.Cu']for g in polygons(unary_union([i['g']for i in ni if i['layer']==layer]))]
 parent=list(range(len(comps)))
 def find(n):
  while parent[n]!=n:parent[n]=parent[parent[n]];n=parent[n]
  return n
 def join(ids):
  for n in ids[1:]:parent[find(n)]=find(ids[0])
 def key(i):return(i['uuid'],i['layer'])
 touches={key(i):[n for n,(layer,g)in enumerate(comps)if layer==i['layer']and i['g'].intersection(g).area>1e-8]for i in ni if i['kind']in['pad','PCB_VIA','board_graphic','PCB_TRACK','PCB_ARC']}
 plated={}
 for i in ni:
  if i['kind']in['pad','PCB_VIA']:plated.setdefault(i['uuid'],[]).append(i)
 for group in plated.values():
  if {i['layer']for i in group}=={'F.Cu','B.Cu'}:join(sorted({n for i in group for n in touches[key(i)]}))
 groups={}
 for n,(layer,g)in enumerate(comps):groups.setdefault(find(n),[]).append((n,layer,g))
 gr=[]
 for members in groups.values():
  ids={n for n,layer,g in members}
  touching=[i for i in ni if key(i)in touches and ids.intersection(touches[key(i)])]
  pads=sorted({i['ref']+'.'+i['pin']for i in touching if i['kind']=='pad'})
  copper_items=sorted({i['uuid'] for i in touching if i['kind'] in ['PCB_VIA','board_graphic','PCB_TRACK','PCB_ARC']})
  gr.append({'pads':pads,'copper_item_uuids':copper_items,'pieces':[{'layer':layer,'area_mm2':g.area,'bounds_mm':list(g.bounds)}for n,layer,g in members],'total_area_mm2':sum(g.area for n,layer,g in members)})
 results.append({'net':net,'pad_bearing_component_count':sum(bool(g['pads'])for g in gr),'components':gr})
overlaps=[]
for layer in ['F.Cu','B.Cu']:
 shapes={net:unary_union([i['g']for i in items if i['net']==net and i['layer']==layer])for net in sorted({i['net']for i in items})}
 names=list(shapes)
 for ix,net in enumerate(names):
  for other in names[ix+1:]:
   overlap=shapes[net].intersection(shapes[other])
   if overlap.area>1e-8:overlaps.append({'layer':layer,'nets':[net,other],'area_mm2':overlap.area,'bounds_mm':list(overlap.bounds)})
r={'foreign_net_overlaps':overlaps,'pcb_sha256':d['pcb_sha256'],'net_count':len(results),'disconnected_pad_net_names':[r['net']for r in results if r['pad_bearing_component_count']>1],'orphan_component_count':sum(not g['pads']for r in results for g in r['components']),'nets':results,'method':'Native saved copper exported at 2 um polygon tolerance. Graph connects layers only through identical physical plated pad/via UUID. Positive-area overlap threshold 1e-8 mm2. No refill. Pad/via land envelopes include the drill area; overlap areas are screening metrics, not plated metal areas. Tiny isolated results require checking approximation and source geometry before classification as manufacturing defects.'}
a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k!='nets'},indent=2))
