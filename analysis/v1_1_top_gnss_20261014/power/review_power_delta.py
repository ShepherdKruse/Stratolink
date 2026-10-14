#!/usr/bin/env python3
"""Compare native electrical/placement snapshots without editing either CAD file."""
from pathlib import Path
import argparse,json,math,heapq
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import unary_union
ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();b=json.loads(args.baseline.read_text());a=json.loads(args.candidate.read_text());g=lambda p:unary_union([Polygon(q['shell'],q['holes'])for q in p['polygons']]);rho_sheet=.0004925714285714286
crit=['U1','U8','C2','C3','C4','C6','L2','C22','R24','R25','R26','C5'];checks={r:b['footprints'][r]==a['footprints'][r] for r in crit};checks['L1_pad_sizes_and_nets_exact']=all((p['size'],p['net'])==(q['size'],q['net'])for p,q in zip([p for p in b['pads']if p['ref']=='L1'],[p for p in a['pads']if p['ref']=='L1']));tracks={}
for net in['+SOLAR','Net-(U1-LBOOST)','Net-(U1-LBUCK)']:
 before={t['uuid']:t for t in b['tracks']if t['net']==net};after={t['uuid']:t for t in a['tracks']if t['net']==net};removed=[v for k,v in before.items()if k not in after];added=[v for k,v in after.items()if k not in before];changed=[dict(before=before[k],after=after[k])for k in before.keys()&after.keys()if before[k]!=after[k]]
 tracks[net]=dict(before_total_track_length_mm=sum(t['length']for t in before.values()),after_total_track_length_mm=sum(t['length']for t in after.values()),before_total_trace_R_ohm=sum(rho_sheet*t['length']/t['width']for t in before.values()if t['kind']!='PCB_VIA'),after_total_trace_R_ohm=sum(rho_sheet*t['length']/t['width']for t in after.values()if t['kind']!='PCB_VIA'),removed=removed,added=added,changed=changed)
# A path screen of selected local supply terminals; graph uses copper endpoint contacts.
def paths(j):
 tt=[t for t in j['tracks']if t['net']=='+SOLAR'];pp=[p for p in j['pads']if p['net']=='+SOLAR'];adj={};coord=lambda x:tuple(round(v,5)for v in x)
 def add(u,v,R,L,uid):adj.setdefault(u,[]).append((v,R,L,uid));adj.setdefault(v,[]).append((u,R,L,uid))
 for t in tt:
  if t['kind']=='PCB_VIA':add(('F.Cu',)+coord(t['start']),('B.Cu',)+coord(t['start']),0,0,t['uuid'])
  else:add((t['layer'],)+coord(t['start']),(t['layer'],)+coord(t['end']),rho_sheet*t['length']/t['width'],t['length'],t['uuid'])
 for p in pp:
  key=(p['ref'],p['pin']);geom=g(p)
  for node in list(adj):
   if len(node)==3 and node[0]in p['layers'] and geom.buffer(.00002).covers(Point(node[1:])):add(key,node,0,0,'pad-contact')
 def shortest(start,end):
  q=[(0,0,start,[])];seen=set()
  while q:
   R,L,n,path=heapq.heappop(q)
   if n in seen:continue
   seen.add(n)
   if n==end:return dict(resistance_ohm=R,track_length_mm=L,track_UUIDs=[p for p in path if p!='pad-contact'])
   for v,r,l,uid in adj.get(n,[]):
    if v not in seen:heapq.heappush(q,(R+r,L+l,v,path+[uid]))
  return dict(unresolved='Endpoint graph did not find path; native copper connectivity remains authoritative.')
 return {name:shortest(*pair)for name,pair in{'C2_to_L1':(('C2','1'),('L1','2')),'C2_to_VIN':(('C2','1'),('U1','2')),'J2_to_L1':(('J2','1'),('L1','2')),'J1_to_L1':(('J1','1'),('L1','2'))}.items()}
near=[]
for p in a['pads']:
 if p['ref']!='L1':continue
 for q in a['pads']:
  if q['ref']=='L1' or not set(p['layers'])&set(q['layers']):continue
  gap=g(p).distance(g(q))
  if gap<1:near.append(dict(L1pin=p['pin'],other_ref=q['ref'],other_pin=q['pin'],net=q['net'],copper_gap_mm=gap))
report=dict(baseline_sha256=b['sha256'],candidate_sha256=a['sha256'],checks=checks,L1_before=b['footprints']['L1'],L1_after=a['footprints']['L1'],net_track_deltas=tracks,supply_paths_before=paths(b),supply_paths_after=paths(a),L1_nearby_pads=near,notes=['TrackR uses20°C35µm nominalCu;viaR/padspreading/temperature excluded.','Whole-net summed resistance is NOT a source equivalent resistance; path results are distinguished.','Zero-R pad-contact links omit pad-spreading resistance and avoid attributing center-to-land travel to a trace.','Endpoint graph is a centerline screen, not a substitute for exact native copper connectivity.','Native DRC and actual GND return/reference must be reviewed alongside these values.'])
args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(checks=checks,L1_before=b['footprints']['L1']['at'],L1_after=a['footprints']['L1']['at'],switch_length_before_mm=tracks['Net-(U1-LBOOST)']['before_total_track_length_mm'],switch_length_after_mm=tracks['Net-(U1-LBOOST)']['after_total_track_length_mm'],supply_paths_before=report['supply_paths_before'],supply_paths_after=report['supply_paths_after']),indent=2))
