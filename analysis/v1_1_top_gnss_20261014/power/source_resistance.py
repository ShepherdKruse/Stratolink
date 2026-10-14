#!/usr/bin/env python3
"""Nominal actual-route resistance screen; not a field/current-density model."""
from pathlib import Path
import json,argparse,heapq
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();b=json.loads(a.baseline.read_text());d=json.loads(a.candidate.read_text());sheet=1.724e-8/35e-6;start=(54.781,58.032)
def route(j,start,end,blocked=set()):
 adj={}
 for t in j['tracks']:
  if t['net']!='+SOLAR' or t['layer']!='B.Cu' or t['kind']=='PCB_VIA' or t['uuid'] in blocked:continue
  u,v=tuple(t['start']),tuple(t['end']);R=sheet*t['length']/t['width'];adj.setdefault(u,[]).append((v,R,t));adj.setdefault(v,[]).append((u,R,t))
 queue=[(0,start,[])];seen=set()
 while queue:
  R,u,path=heapq.heappop(queue)
  if u in seen:continue
  seen.add(u)
  if u==end:return dict(length_mm=sum(t['length']for t in path),resistance_ohm_20C=R,track_uuids=[t['uuid']for t in path],widths_mm=sorted(set(t['width']for t in path)))
  for v,r,t in adj.get(u,[]):
   if v not in seen:heapq.heappush(queue,(R+r,v,path+[t]))
 raise RuntimeError(('No exact endpoint path',start,end))
l1=next(p['at']for p in b['pads']if p['ref']=='L1'and p['pin']=='2');c2=next(p['at']for p in b['pads']if p['ref']=='C2'and p['pin']=='1');left=route(b,start,tuple(l1));right=route(b,start,tuple(l1),set(left['track_uuids']));local=route(b,tuple(l1),tuple(c2));parallel=left['resistance_ohm_20C']*right['resistance_ohm_20C']/(left['resistance_ohm_20C']+right['resistance_ohm_20C']);old=parallel+local['resistance_ohm_20C'];new=route(d,start,tuple(c2));delta=new['resistance_ohm_20C']-old
r=dict(baseline_sha256=b['sha256'],candidate_sha256=d['sha256'],rho20_ohm_m=1.724e-8,nominal_copper_thickness_um=35,start_mm=start,C2_end_mm=c2,old_left=left,old_right=right,old_parallel_ohm=parallel,old_local_L1_to_C2=local,old_junction_to_C2_ohm=old,new_junction_to_C2=new,delta_ohm=delta,conditional_voltage_drop_increase_mV={str(mA):delta*mA for mA in[100,200]},conditional_200mA_delta_mV_at85C=delta*200*(1+.00393*65),limitations=['100/200mA are conditional current screens, not measured panel output.','Uses actual path lengths and widths; excludes via, solder and pad-spreading resistance, current crowding and copper-thickness tolerance.','Common connector-to-junction paths add resistance in both versions.','Centerline branches terminating inside large same-net L1 pads make this an approximate circuit model, not an exact resistance extraction.'])
a.output.write_text(json.dumps(r,indent=2)+'\n');print('delta_mOhm',delta*1000)
