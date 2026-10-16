#!/usr/bin/env python3
"""Ground connectivity through actual plated features, with bounded-window limits."""
from pathlib import Path
import json,sys
from shapely.geometry import box,Point
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'analysis/v1_1_peer_review_20261014/digital'))
from check_rf_reference import polygons,parts
p=Path(sys.argv[1])if len(sys.argv)>1 else Path(__file__).parent
d=json.loads((p/'native-copper.json').read_text());native=json.loads((p/'native-layout.json').read_text())
assert d['pcb_sha256']==native['sha256']
items=[dict(i,g=polygons(i['polygons']))for i in d['items']]
def check(bounds,refs):
 window=box(*bounds);ground={l:unary_union([i['g']for i in items if i['net']=='GND'and i['layer']==l]).intersection(window)for l in ['F.Cu','B.Cu']}
 components=[(l,g)for l in ground for g in parts(ground[l])];parent=list(range(len(components)))
 def find(i):
  while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
  return i
 pairs={}
 for i in items:
  if i['net']=='GND'and i['kind']in['pad','PCB_VIA']and window.intersects(i['g']):pairs.setdefault(i['uuid'],[]).append(i)
 for pair in pairs.values():
  if {i['layer']for i in pair}!={'F.Cu','B.Cu'}:continue
  ids=[j for j,(l,g)in enumerate(components)if any(i['layer']==l and i['g'].intersects(g)for i in pair)]
  for q in ids[1:]:parent[find(q)]=find(ids[0])
 pads=[]
 for i in items:
  if i['net']=='GND'and i.get('ref')in refs and i['kind']=='pad'and window.covers(i['g']):
   ids={find(j)for j,(l,g)in enumerate(components)if i['layer']==l and i['g'].intersects(g)}
   pads.append({'ref':i['ref'],'pin':i['pin'],'at':i['at'],'layer':i['layer'],'component_ids':sorted(ids)})
 return {'bounds_mm':bounds,'ground_pads':pads,'all_listed_pads_share_ground':len({x for i in pads for x in i['component_ids']})==1 and all(i['component_ids']for i in pads)}
groups={'converter':['U1','C2','C3','C4','C6','C20'],'GNSS':['U3','C10'],'balancer':['U8','C22','R25'],'radio':['U2','C7','C8'],'pressure':['U4','C11']}
out={'pcb_sha256':d['pcb_sha256'],'whole_board':{k:check([50,28,78,87],refs)for k,refs in groups.items()},'bounded_converter_windows':{str(y):check([62,29,77,y],groups['converter'])for y in [43.5,46]},'repair_stitches':[]}
for xy in [[64.25,32.2],[68.75,59.95],[63.5,49.85],[59.6,48.895]]:
 v=next(t for t in native['tracks']if t['kind']=='PCB_VIA'and t['start']==xy);assert v['net']=='GND'
 entries=[i for i in items if i['uuid']==v['uuid']];row={'uuid':v['uuid'],'at_mm':xy,'net':v['net'],'diameter_mm':v['width'],'drill_mm':v['drill'],'annular_ring_contact_mm2':{}}
 for i in entries:
  ring=i['g'].difference(Point(xy).buffer(v['drill']/2,quad_segs=64));other=unary_union([j['g']for j in items if j['net']=='GND'and j['layer']==i['layer']and j['uuid']!=v['uuid']]);row['annular_ring_contact_mm2'][i['layer']]=ring.intersection(other).area
 row['ground_contact_on_both_faces']=set(row['annular_ring_contact_mm2'])=={'F.Cu','B.Cu'}and min(row['annular_ring_contact_mm2'].values())>1e-6
 out['repair_stitches'].append(row)
out['pass']=all(x['all_listed_pads_share_ground']for x in out['whole_board'].values())and all(x['ground_contact_on_both_faces']for x in out['repair_stitches'])
out['limits']=['Whole-board finite copper connectivity is not minimum loop inductance, return-current distribution or measured rail stability.','Bounded rectangles are geometric screens: failing a small window is not an electrical open when the full-board path is connected.','Converter grounds reconnect within the larger reported window; this does not assert that every available return current travels along that path.','Plated contacts are joined only through the same native pad/via UUID on both faces; coincident copper on separate layers does not itself connect.','Native polygons approximate boundaries at2um; no buffer used to invent connections.']
(p/'ground-review.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({'pcb_sha256':out['pcb_sha256'],'pass':out['pass'],'whole_board':{k:v['all_listed_pads_share_ground']for k,v in out['whole_board'].items()},'converter_windows':{k:v['all_listed_pads_share_ground']for k,v in out['bounded_converter_windows'].items()},'stitches':out['repair_stitches']},indent=2))
assert out['pass']
