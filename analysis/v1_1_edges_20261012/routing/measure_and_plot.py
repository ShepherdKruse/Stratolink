#!/usr/bin/env python3
"""Measure native-board geometry and draw the three bounded routing edits."""
from pathlib import Path
import json,gzip,math,argparse
from collections import Counter,defaultdict
from shapely.geometry import Polygon,LineString
from shapely.ops import unary_union,nearest_points
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch
from build_candidate import HERE,CHANGES,ADDED_UUID

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--revision-r2',action='store_true',help='Read/write only the r2 evidence directory')
args=parser.parse_args()
if args.revision_r2:
 from build_candidate_r2 import EVIDENCE,R2_CHANGES
 HERE=EVIDENCE;CHANGES=R2_CHANGES

data=json.loads(gzip.decompress((HERE/'native_geometry.json.gz').read_bytes()))
def union(polys):return unary_union([Polygon(p['shell'],p['holes']) for p in polys])
def line(s):return LineString([s['start_mm'],s['end_mm']])
def grouped(d):return {s['uuid']:s for s in d['segments']}
old,new=grouped(data['baseline']),grouped(data['candidate'])
outline=union(data['baseline']['outline']);assert outline.equals(union(data['candidate']['outline']))
rows=[]
for uid in sorted(set(CHANGES)|{ADDED_UUID}):
 row=dict(uuid=uid,net=new[uid]['net'],layer=new[uid]['layer'],width_mm=new[uid]['width_mm'])
 for name,source in [('before',old),('after',new)]:
  if uid not in source:continue
  s=source[uid];l=line(s);nearest=nearest_points(l,outline.boundary)
  row[name]=dict(start_mm=s['start_mm'],end_mm=s['end_mm'],length_mm=l.length,
    copper_to_board_edge_mm=l.distance(outline.boundary)-s['width_mm']/2,
    nearest_centerline_and_outline_points_mm=[list(p.coords[0]) for p in nearest])
 rows.append(row)

boundary={};lengths={}
for net in ['+SOLAR','VSTOR','PA9']:
 boundary[net]={};lengths[net]={}
 for name,source,ids in [('before',old,set(CHANGES)),('after',new,set(CHANGES)|{ADDED_UUID})]:
  counts=Counter(tuple(p) for uid in ids if source[uid]['net']==net for p in [source[uid]['start_mm'],source[uid]['end_mm']])
  boundary[net][name]=sorted([list(p) for p,n in counts.items() if n==1])
  lengths[net][name]=sum(line(source[uid]).length for uid in ids if source[uid]['net']==net)
 assert boundary[net]['before']==boundary[net]['after']
 lengths[net]['delta_mm']=lengths[net]['after']-lengths[net]['before']

def geom_parts(geom):return list(geom.geoms) if hasattr(geom,'geoms') else [geom]
copper={}
for layer in ['F.Cu','B.Cu']:
 a,b=[union(data[v]['copper'][layer]) for v in ['baseline','candidate']]
 changed=a.symmetric_difference(b)
 copper[layer]=dict(before_area_mm2=a.area,after_area_mm2=b.area,added_area_mm2=b.difference(a).area,
  removed_area_mm2=a.difference(b).area,changed_bounds_mm=list(changed.bounds),
  parts_below_1e_minus5_mm2_total_area_mm2=sum(g.area for g in geom_parts(changed) if g.area<1e-5),
  bounds_of_parts_over_1e_minus5_mm2=list(unary_union([g for g in geom_parts(changed) if g.area>=1e-5]).bounds),
  changed_parts=[dict(area_mm2=g.area,bounds_mm=list(g.bounds)) for g in geom_parts(changed) if g.area>1e-9])

result=dict(geometry_source='Native KiCad outline and copper, line-to-outline Euclidean distance minus unchanged trace half-width',
 source_hashes={v:data[v]['source_sha256'] for v in data},routes=rows,
 outer_route_endpoints=boundary,local_trace_lengths_mm=lengths,full_copper_delta=copper,
 proposed_0p88_header_corridor=dict(PA9_to_J3_1_mm=54.444998-.44-(53.675+.125),
 VSTOR_to_J4_1_mm=76.299-.125-(75.531+.44)))
if args.revision_r2:
 checks=[]
 for uid in sorted(set(CHANGES)|{ADDED_UUID}):
  s=new[uid]
  for pad in data['candidate']['pads']:
   if pad['ref'] not in ['J3','J4'] or pad['layer']!=s['layer'] or pad['net']==s['net']:continue
   distance=line(s).distance(union(pad['shape']))-s['width_mm']/2
   checks.append(dict(segment_uuid=uid,net=s['net'],pad=f"{pad['ref']}.{pad['number']}",gap_mm=distance))
 result['native_0p88_header_to_changed_routes']=sorted(checks,key=lambda d:d['gap_mm'])
 assert min(c['gap_mm'] for c in checks)>=.20
 result['comparison_scope']='Final r2 including the separately reviewed .88 mm header lands, versus d70a53d; full-copper delta therefore includes both ring and route changes.'
(HERE/'geometry-review.json').write_text(json.dumps(result,indent=2)+'\n')

def patch(poly,color,alpha,ax):
 for p in geom_parts(poly):
  if p.is_empty or p.geom_type!='Polygon':continue
  vertices=[];codes=[]
  for ring in [p.exterior,*p.interiors]:
   points=list(ring.coords);vertices+=points;codes += [MPath.MOVETO]+[MPath.LINETO]*(len(points)-2)+[MPath.CLOSEPOLY]
  ax.add_patch(PathPatch(MPath(vertices,codes),facecolor=color,edgecolor='none',alpha=alpha))

fig,axs=plt.subplots(1,3,figsize=(12.5,8.4),gridspec_kw={'width_ratios':[1.15,1,1]})
specs=[('+SOLAR · front','+SOLAR','F.Cu',(53.05,56.35,60.15,65.5)),
 ('VSTOR · front','VSTOR','F.Cu',(74.65,76.95,66.85,70.55)),
 ('PA9 · back','PA9','B.Cu',(53.05,55.25,67.85,71.55))]
for ax,(title,net,layer,box) in zip(axs,specs):
 patch(union(data['candidate']['copper'][layer]),'#c8d2d9',.60,ax)
 for p in geom_parts(outline):
  x,y=p.exterior.xy;ax.plot(x,y,color='#2c3e50',lw=1.3)
 for source,ids,color,label,style in [(old,set(CHANGES),'#df8626','Before','--'),(new,set(CHANGES)|{ADDED_UUID},'#0c7495','After','-')]:
  for uid in ids:
   s=source[uid]
   if s['net']!=net:continue
   x,y=line(s).xy;ax.plot(x,y,color=color,lw=2.7,linestyle=style)
 for p in data['candidate']['pads']:
  if p['layer']==layer and p['ref'] in ['J3','J4']:
   shape=union(p['shape']);c=shape.centroid
   if box[0]<c.x<box[1] and box[2]<c.y<box[3]:ax.text(c.x,c.y,f"{p['ref']}.{p['number']}",ha='center',va='center',fontsize=8,color='#34495e')
 ax.set_xlim(box[0],box[1]);ax.set_ylim(box[3],box[2]);ax.set_aspect('equal');ax.set_title(title,fontsize=12,fontweight='bold')
 ax.grid(alpha=.2);ax.set_xlabel('Board X (mm)');ax.set_ylabel('Board Y (mm)')
 mins=[r['after']['copper_to_board_edge_mm'] for r in rows if r['net']==net and r['uuid'] in CHANGES and r['uuid']!='c1227579-013e-4ffa-b72b-869589a0d2ea']
 label=f'Min edited run edge gap: {min(mins):.3f} mm'
 if args.revision_r2 and net=='+SOLAR':label='Upper repair: 0.289 mm\nLower side feed: 0.234 mm'
 ax.text(.03,.98,label,transform=ax.transAxes,va='top',fontsize=8.5,bbox=dict(facecolor='white',edgecolor='none',alpha=.9))
fig.suptitle('Stratolink v1.1 · local routing away from the board edge',fontsize=15,fontweight='bold',y=.98)
fig.text(.5,.935,'Orange dashed = original centerline    Blue = candidate centerline    Gray = candidate copper',ha='center',fontsize=10)
footer='All trace widths remain 0.25 mm; pad and board geometry remain unchanged in this routing-only candidate.\n+SOLAR transitions back to the original long side feed; PA9 uses ≥0.23 mm edge clearance to preserve 0.20 mm spacing to enlarged header lands.'
if args.revision_r2:footer='Revision 2 includes 0.88 mm header lands; all edited traces remain 0.25 mm wide.\n+SOLAR side feed moves 0.008 mm outward; the VSTOR lower bend moves down to clear the square J4.1 corner. All edited routes clear header copper by ≥0.203 mm.'
fig.text(.5,.025,footer,ha='center',fontsize=9)
fig.subplots_adjust(left=.06,right=.985,bottom=.095,top=.90,wspace=.28)
fig.savefig(HERE/'routing-before-after.png',dpi=190)
print(json.dumps(dict(local_trace_lengths_mm=lengths,route_edge_gaps={r['uuid']:r['after']['copper_to_board_edge_mm'] for r in rows},full_copper_delta={k:{x:y for x,y in v.items() if x!='changed_parts'} for k,v in copper.items()}),indent=2))
