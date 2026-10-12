#!/usr/bin/env python3
"""Read-only notch alternatives against native canonical copper polygons."""
from pathlib import Path
import json
import numpy as np
from shapely.geometry import Polygon,box,LineString
from shapely.ops import unary_union
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MP
H=Path(__file__).resolve().parent
d=json.loads((H/'copper_native.json').read_text())
def geometry(o): return unary_union([Polygon(p['shell'],p['holes']) for p in o['polygons']])
for o in d['items']+d['courtyards']:o['g']=geometry(o)

def candidate(side,depth=1.5,height=2.8):
 edge=53.3165 if side=='left' else 76.6755;s=1 if side=='left' else -1
 cut=LineString([(edge-s*2,54.5),(edge+s*(depth-.5),54.5)]).buffer(.5,quad_segs=64)
 env=box(min(edge+s*.2,edge+s*(depth+.8)),54.5-height/2,max(edge+s*.2,edge+s*(depth+.8)),54.5+height/2)
 return cut,env.difference(cut.buffer(.22,quad_segs=64))
def row(o,dist=None):return {k:v for k,v in o.items() if k not in ['polygons','g']} | (dict(distance_mm=dist) if dist is not None else {})
results=[]
for depth,height in [(1.5,2.8),(2,2.8),(2.5,2.8),(3,2.8),(1.5,3.4),(2,3.4),(1.5,4)]:
 for side in ['left','right']:
  cut,land=candidate(side,depth,height)
  other=[o for o in d['items'] if o.get('ref') not in ['J1','J2']]
  cutconf=[row(o,cut.distance(o['g'])) for o in other if cut.distance(o['g'])<.199]
  landconf=[row(o,land.distance(o['g'])) for o in other if o['net']!='GND' and land.distance(o['g'])<.149]
  courtyards=[row(o,cut.distance(o['g'])) for o in d['courtyards'] if o['ref'] not in ['J1','J2'] and cut.distance(o['g'])<.5]
  nearby=sorted([row(o,cut.distance(o['g'])) for o in other if o['type']=='pad'],key=lambda o:o['distance_mm'])[:6]
  nearby_courtyards=sorted([row(o,cut.distance(o['g'])) for o in d['courtyards'] if o['ref'] not in ['J1','J2']],key=lambda o:o['distance_mm'])[:5]
  closest=sorted([row(o,land.distance(o['g'])) for o in other if o['net']!='GND'],key=lambda o:o['distance_mm'])[:10]
  results.append(dict(side=side,depth_mm=depth,land_height_mm=height,land_area_per_face_mm2=land.area,bank_length_mm=depth-.5,usable_straight_solder_length_nominal_mm=depth-.7,cut_conflicts=cutconf,land_conflicts=landconf,near_courtyards=courtyards,nearest_pads_to_cut=nearby,nearest_courtyards_to_cut=nearby_courtyards,nearest_non_GND_to_land=closest))
(H/'screen.json').write_text(json.dumps(dict(source_sha256=d['source_sha256'],method='Exact native copper polygons approximated outward within 0.001mm; candidate arcs approximated with 64 segments per quadrant. Cut conflicts <0.199mm, non-GND land conflicts <0.149mm (0.001mm geometry allowance). Not a native DRC. Zones excluded, require regeneration. Land height varies around y54.5; its inward extent remains depth+0.8mm.',candidates=results),indent=2)+'\n')
for r in results:
 print(r['side'],r['depth_mm'],r['land_height_mm'],'area',round(r['land_area_per_face_mm2'],3),'cut',sorted(set((o.get('ref',''),o['net'],o['layer']) for o in r['cut_conflicts'])),'land',sorted(set((o.get('ref',''),o['net'],o['layer']) for o in r['land_conflicts'])))
 print('courtyard',[(o['ref'],round(o['distance_mm'],3)) for o in r['nearest_courtyards_to_cut'][:3]])
fig,axs=plt.subplots(2,2,figsize=(13,10),layout='constrained')
colors={'GND':'#aaa','VSTOR':'#c22','PB5':'#9169d9','RX':'#2f96ae','TX':'#3063ac','+SOLAR':'#d5891e','SDA':'#238342'}
for i,side in enumerate(['left','right']):
 for j,layer in enumerate(['F.Cu','B.Cu']):
  ax=axs[i,j];ax.set_aspect('equal');ax.set_xlim((52.8,60.5) if side=='left' else (69.5,77.2));ax.set_ylim(58,50.5);ax.set_title(side+' '+layer);ax.grid(alpha=.15)
  for o in d['items']:
   if o['layer']!=layer:continue
   for p in o['polygons']:
    if len(p['shell'])<3:continue
    ax.add_patch(MP(np.array(p['shell']),facecolor=colors.get(o['net'],'#8394a0'),edgecolor='none',alpha=.7))
  for o in d['courtyards']:
   if o['layer']!=layer.replace('Cu','CrtYd') or o['ref'] in ['J1','J2']:continue
   g=o['g'];
   if g.is_empty:continue
   for p in o['polygons']:ax.add_patch(MP(np.array(p['shell']),fill=False,edgecolor='#444',linestyle='--',lw=.7))
   x,y=g.centroid.coords[0]
   if ax.get_xlim()[0]<x<ax.get_xlim()[1] and 50<y<58:ax.text(x,y,o['ref'],fontsize=8)
  for dep,col in [(2,'#ef4423'),(2.5,'#8b39d1'),(3,'#188cba')]:
   cut,land=candidate(side,dep)
   ax.add_patch(MP(np.array(cut.exterior.coords),fill=False,edgecolor=col,lw=1.1,linestyle='--',label=f'{dep}mm cut'))
   ax.add_patch(MP(np.array(land.exterior.coords),fill=False,edgecolor=col,lw=.7))
  ax.legend(fontsize=7,loc='lower left')
fig.suptitle('Read-only deeper notch options over canonical copper: cut and new GND envelope\nExisting routes remain visible; a conflict requires rerouting, not a component move',fontsize=12)
fig.savefig(H/'deeper_notches.png',dpi=160)
