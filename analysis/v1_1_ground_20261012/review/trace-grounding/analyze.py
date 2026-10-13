#!/usr/bin/env python3
"""List explicit shortest centreline routes and nominal copper DC resistance."""
from pathlib import Path
import json,heapq,math
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as Patch
HERE=Path(__file__).resolve().parent
data=json.loads((HERE/'native.json').read_text());items=data['items']
rho=1.724e-8;thickness_mm=.035
def xykey(xy):return 'xy:'+','.join(f'{x:.6f}' for x in xy)
graph={};coords={}
def edge(a,b,resistance,uuid=None,length=0):
 graph.setdefault(a,[]).append((b,resistance,uuid,length));graph.setdefault(b,[]).append((a,resistance,uuid,length))
for uuid,row in items.items():
 if row['type']!='PCB_TRACK':continue
 a,b=xykey(row['start']),xykey(row['end']);coords[a]=row['start'];coords[b]=row['end']
 r=rho*(row['length_mm']*.001)/((row['width_mm']*.001)*(thickness_mm*.001))
 edge(a,b,r,uuid,row['length_mm'])
for uuid,row in items.items():
 if row['type']!='PAD':continue
 node=row['ref']+'.'+row['pin'];graph.setdefault(node,[])
 shape=unary_union([Polygon(p['shell'],p['holes']) for p in row['layers'].get('F.Cu',[])])
 for k,xy in coords.items():
  if shape.distance(Point(xy))<1e-8:edge(node,k,0)
vias={u:r for u,r in items.items() if r['type']=='PCB_VIA'}
def path(source,target):
 q=[(0,source)];best={source:0};previous={}
 while q:
  cost,at=heapq.heappop(q)
  if cost!=best[at]:continue
  if at==target:break
  for dest,r,uuid,length in graph[at]:
   alt=cost+r
   if alt<best.get(dest,math.inf):best[dest]=alt;previous[dest]=(at,uuid,length,r);heapq.heappush(q,(alt,dest))
 assert target in best
 steps=[];at=target
 while at!=source:
  before,uuid,length,r=previous[at]
  if uuid:steps.append(dict(uuid=uuid,from_node=before,to_node=at,length_mm=length,width_mm=items[uuid]['width_mm'],resistance_milliohm=r*1000))
  at=before
 steps.reverse();return dict(length_mm=sum(s['length_mm'] for s in steps),nominal_trace_resistance_milliohm=best[target]*1000,segments=steps)
result=dict(source_sha256=data['source_sha256'],zone_free_sha256=data['zone_free_sha256'],zones_removed_for_experiment=data['removed_zone_count'],selected_zone_connect_none_pads=['U7.5','U7.7','U7.8'],selected_ground_pads_retaining_original_zone_relief=['U7.3','U7.6'],assumptions=dict(copper_resistivity_ohm_m_at20C=rho,copper_thickness_mm=thickness_mm,model='Sum rho*L/(width*thickness) along explicit trace centrelines to each via; ignores pad spreading, vias, plane resistance, contacts and parallel paths. A dimensional DC sanity check, not an AC impedance or assembly qualification.'),native_reachable_pads=data['groups']['3']['reachable_pads'],vias={u:{k:v for k,v in r.items() if k!='layers'} for u,r in vias.items()},paths={})
for pin in ['3','5','6','7','8']:
 source='U7.'+pin
 paths={uuid:path(source,xykey(v['start'])) for uuid,v in vias.items()}
 result['paths'][source]=paths
 print(source,[(vias[u]['start'],round(p['length_mm'],6),round(p['nominal_trace_resistance_milliohm'],3)) for u,p in paths.items()])
(HERE/'paths.json').write_text(json.dumps(result,indent=2)+'\n')
fig,ax=plt.subplots(figsize=(7.5,8),layout='constrained');ax.set_aspect('equal');ax.set_xlim(68.8,74.4);ax.set_ylim(39,33);ax.grid(alpha=.15);ax.set_xlabel('Board X (mm)');ax.set_ylabel('Board Y (mm)')
for u,r in items.items():
 if r['type']=='PCB_TRACK':
  ax.plot([r['start'][0],r['end'][0]],[r['start'][1],r['end'][1]],color='#28755e',linewidth=3,zorder=2)
 elif r['type']=='PCB_VIA':
  ax.add_patch(plt.Circle(r['start'],r['width_mm']/2,facecolor='#d7b445',edgecolor='#444',lw=1,zorder=3));ax.add_patch(plt.Circle(r['start'],r['drill_mm']/2,facecolor='white',edgecolor='none',zorder=4));ax.text(r['start'][0],r['start'][1]-.38,u[:8],ha='center',fontsize=8)
 elif r['type']=='PAD':
  color='#db7a32' if r.get('ref')=='U7' and r.get('pin') in ['5','7','8'] else '#709cca'
  for pp in r['layers'].get('F.Cu',[]):ax.add_patch(Patch(pp['shell'],facecolor=color,edgecolor='#333',lw=.6,zorder=4))
  if r.get('ref')=='U7':ax.text(r['xy'][0]+.12,r['xy'][1]+.02,r['pin'],va='center',ha='left',fontsize=9,zorder=5)
  else:
   shapes=unary_union([Polygon(p['shell'],p['holes']) for pp in r['layers'].values() for p in pp])
   ax.text(shapes.bounds[0]-.07,r['xy'][1],r['ref']+'.'+r['pin'],ha='right',va='center',fontsize=8,zorder=6)
ax.set_title('U7 explicit GND traces with all zone fill removed\nOrange: selected trace-fed pads 5, 7, 8; blue: other GND pads')
fig.savefig(HERE/'explicit-ground-paths.png',dpi=170)
