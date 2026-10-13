#!/usr/bin/env python3
"""Independent geometry and plotted mask check after verify_native.py.

Use analysis/.venv/bin/python. Distances are nominal CAD geometry, not a
worst-case etch/drill-registration qualification.
"""
from pathlib import Path
import gzip,json,re,sys
from collections import Counter
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-edges-20261012/review'
def union(rows):return unary_union([Polygon(r['shell'],r['holes']).buffer(0) for r in rows])
def mask_program(path):
 # Compare actual graphic commands with aperture IDs replaced by their
 # definitions; this permits harmless aperture renumbering without hiding
 # moved flashes, new regions or altered non-header geometry.
 lines=path.read_text().splitlines();apertures={};ref=None;ap=None;program=[];header=[]
 for s in lines:
  m=re.fullmatch(r'%ADD(\d+)(.*)\*%',s)
  if m:apertures[m[1]]=m[2];continue
  if 'CreationDate' in s or s.startswith('G04 Created by'):continue
  m=re.fullmatch(r'%TO.C,([^*]+)\*%',s)
  if m:ref=m[1]
  m=re.fullmatch(r'D(\d+)\*',s)
  if m:ap=m[1];continue
  if s.endswith('D03*'):
   item=dict(ref=ref,command=s,aperture=apertures[ap])
   if ref in ['J3','J4']:header.append(item)
   else:program.append(('flash',ref,s,apertures[ap]))
  else:
   # Retain the active aperture for non-flash graphics, where width matters.
   program.append((s,apertures.get(ap) if re.search(r'D0[12]\*$',s) else None))
 return program,header

def main():
 data=json.loads(gzip.decompress((HERE/'native-geometry.json.gz').read_bytes()));scope=json.loads((HERE/'approved-scope.json').read_text());result={}
 roi=unary_union([box(53.1,60.1,56.4,77.6),box(73.6,66,77,77.6)])
 reviewed_remote_corner=box(65.53,69.52,65.60,69.60)
 for layer in ['F.Cu','B.Cu']:
  a,b=[union(data[k]['copper'][layer]) for k in ['baseline','candidate']]
  add=b.difference(a);remove=a.difference(b);outside=add.union(remove).difference(roi)
  bounded=b.difference(a.buffer(.000002)).union(a.difference(b.buffer(.000002))).difference(roi)
  ten_nm=b.difference(a.buffer(.000010)).union(a.difference(b.buffer(.000010))).difference(roi)
  fifty_nm=b.difference(a.buffer(.000050)).union(a.difference(b.buffer(.000050))).difference(roi)
  five_um=b.difference(a.buffer(.005)).union(a.difference(b.buffer(.005))).difference(roi)
  assert ten_nm.difference(reviewed_remote_corner).area<1e-10,(layer,'Unreviewed remote fill difference',ten_nm.bounds)
  assert five_um.area<1e-10,(layer,'Remote fill shift exceeds saved5um polygon approximation setting',five_um.area)
  assert fifty_nm.area<1e-10,(layer,'Final remote boundary residue exceeds50nm',fifty_nm.area)
  if layer=='B.Cu':assert bounded.area<1e-10,('Back remote fill change',bounded.area)
  result[layer]=dict(added_mm2=add.area,removed_mm2=remove.area,raw_outside_roi_mm2=outside.area,outside_after_2nm_boundary_buffer_mm2=bounded.area,
   outside_after_10nm_boundary_buffer_mm2=ten_nm.area,outside_after_50nm_boundary_buffer_mm2=fifty_nm.area,outside_after_5um_boundary_buffer_mm2=five_um.area,
   reviewed_remote_GND_corner_bounds_mm=list(reviewed_remote_corner.bounds),remote_corner_raw_added_mm2=add.intersection(reviewed_remote_corner).area,remote_corner_raw_removed_mm2=remove.intersection(reviewed_remote_corner).area)
 route_measurements={};ring_measurements={}
 for label,d in data.items():
  edges=[(e['uuid'],LineString([e['start_mm'],e['end_mm']])) for e in d['straight_edges']]
  rows=[]
  for t in d['routes']:
   if t['uuid'] not in set(scope['changed_segments'])|set(scope.get('added_segments',[]))|set(scope.get('removed_segments',[])):continue
   line=LineString([t['start_mm'],t['end_mm']]);clearance,edge=min((line.distance(e)-t['width_mm']/2,uid) for uid,e in edges)
   row=dict(uuid=t['uuid'],net=t['net'],layer=t['layer'],nearest_straight_edge=edge,clearance_mm=clearance,length_mm=line.length,width_mm=t['width_mm'])
   if label=='candidate':
    target=.20
    row['meets_preferred_0p23mm_margin']=clearance>=.23-.000002
    assert clearance>=target-.000002,('Local edge target missed',row,target)
   rows.append(row)
  route_measurements[label]=rows
  pieces=[(p,union(p['polygons'])) for p in d['individual_copper'] if p['polygons']]
  cp={(p['uuid'],p['layer']):g for p,g in pieces if p['kind']=='pad'}
  rows=[]
  for p in d['rings']:
   assert p['offset_mm']==[0,0] and p['drill_mm']==[.5,.5],p
   if label=='candidate':assert p['size_mm']==[.88,.88] and abs(p['nominal_minimum_ring_mm']-.19)<1e-10,p
   perlayer={}
   for layer in ['F.Cu','B.Cu']:
    foreign=[(q,g) for q,g in pieces if q['layer']==layer and q['net']!=p['net']]
    center=Point(p['at_mm']);hole_gap,closest=min((center.distance(g)-.25,q['uuid']) for q,g in foreign)
    pad_gap,padclosest=min((cp[p['uuid'],layer].distance(g),q['uuid']) for q,g in foreign)
    if label=='candidate':
     assert hole_gap>=.28-.000002,('Header hole-to-foreign-copper below0.28',p['ref'],p['number'],layer,hole_gap,closest)
     assert pad_gap>=.10-.000002,('Header pad-to-foreign-copper below0.10',p['ref'],p['number'],layer,pad_gap,padclosest)
    perlayer[layer]=dict(min_hole_to_foreign_copper_mm=hole_gap,nearest_to_hole_uuid=closest,min_pad_to_foreign_copper_mm=pad_gap,nearest_to_pad_uuid=padclosest)
   rows.append(dict(ref=p['ref'],pad=p['number'],net=p['net'],nominal_ring_mm=p['nominal_minimum_ring_mm'],layers=perlayer))
  pairs=[]
  for ref in ['J3','J4']:
   group=sorted([p for p in d['rings'] if p['ref']==ref],key=lambda p:int(p['number']))
   for p,q in zip(group,group[1:]):
    pair=dict(ref=ref,pads=[p['number'],q['number']],nets=[p['net'],q['net']],center_pitch_mm=Point(p['at_mm']).distance(Point(q['at_mm'])),copper={},mask={})
    for layer in ['F.Cu','B.Cu']:
     pair['copper'][layer]=cp[p['uuid'],layer].distance(cp[q['uuid'],layer])
     if label=='candidate':assert pair['copper'][layer]>=.12-.000004
    for layer in ['F.Mask','B.Mask']:
     pair['mask'][layer]=union(p['mask'][layer]['polygons']).distance(union(q['mask'][layer]['polygons']))
     if label=='candidate':assert pair['mask'][layer]>=.12-.000004
    pairs.append(pair)
  ring_measurements[label]=dict(pads=rows,adjacent_pairs=pairs)
 result['routes']=route_measurements;result['headers']=ring_measurements
 masks={}
 for filename in ['stratolink-F_Mask.gts','stratolink-B_Mask.gbs']:
  before,after=[mask_program(SCRATCH/(k+'-exports')/filename) for k in ['baseline','candidate']]
  assert before[0]==after[0],('Unscoped mask program difference',filename)
  assert len(before[1])==len(after[1])==14
  for a,b in zip(before[1],after[1]):
   assert a['ref']==b['ref'] and a['command']==b['command']
   assert a['aperture'] in ['R,0.850000X0.850000','O,0.850000X0.850000']
   assert b['aperture']==a['aperture'].replace('0.850000','0.880000')
  masks[filename]=dict(changed_header_flashes=after[1],all_other_graphics_exact=True)
 result['mask_exports']=masks
 result['interpretation']='All distances are nominal CAD dimensions. Individual copper polygons use100nm maximum outward approximation error. Final native-union residue outside reviewed regions is bounded by50nm on F.Cu and2nm on B.Cu; raw differences are retained. PTH nominal annulus is not a guaranteed post-registration remaining ring. Sourced JLC0.18mm PTH minimum applies to2-layer1oz, while0.25mm is its recommendation; chosen0.19mm is a local compromise preserving0.50mm finished holes and1.00mm pitch. Header mask-web acceptance is conditional on a1oz green/red/yellow/blue/purple process with0.10mm minimum;0.12mm does not meet the listed0.13mm black/white requirement.'
 (HERE/'geometry-verification.json').write_text(json.dumps(result,indent=2)+'\n')
 print('Copper scope, routed edge distances,14header rings, both-face conductor and mask gaps, hole-to-foreign-copper and exact non-header mask program passed')

if __name__=='__main__':main()
