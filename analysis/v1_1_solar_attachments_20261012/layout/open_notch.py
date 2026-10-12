"""Read-only open-notch keepout study; dimensions provisional, no CAD mutation."""
import contextlib,io,json
from pathlib import Path
with contextlib.redirect_stdout(io.StringIO()):
 import study as m
from shapely.geometry import LineString,box
from shapely.ops import unary_union
from matplotlib.patches import Polygon as MPolygon
import matplotlib.pyplot as plt
import numpy as np

def shapes(side,y,depth=1.5,width=1.0):
 edge=53.3165 if side=='left' else 76.6755;sgn=1 if side=='left' else -1;r=width/2
 inner=edge+sgn*depth
 cut=LineString([(edge-sgn*1,y),(inner-sgn*r,y)]).buffer(r)
 bb=box(min(edge+sgn*.2,inner+sgn*.8),y-1.7,max(edge+sgn*.2,inner+sgn*.8),y+1.7)
 land=bb.difference(cut.buffer(.2))
 return cut,land
results=[]
for y in [54,54.5,55,55.5,56]:
 for side in ['left','right']:
  cut,land=shapes(side,y)
  cut_hits=[{k:t[k] for k in ['uuid','net','layer','start','end','width']} for t in m.tracks if cut.buffer(.2).intersects(t['geom'])]
  land_hits=[{k:t[k] for k in ['uuid','net','layer','start','end','width']} for t in m.tracks if t['net']!='GND' and land.buffer(.2).intersects(t['geom'])]
  pads=[{k:p[k] for k in ['ref','pin','net','at','size']} for p in m.pads if p['ref'] not in ['J1','J2'] and (cut.buffer(.2).intersects(p['geom']) or p['net']!='GND' and land.buffer(.2).intersects(p['geom']))]
  results.append(dict(side=side,y=y,notch_depth_mm=1.5,notch_width_mm=1.0,land_overall_bounds=list(land.bounds),cut_conflicts=cut_hits,land_conflicts=land_hits,pad_conflicts=pads))
  print(y,side,'cutnets',sorted(set(t['net'] for t in cut_hits)),'landnets',sorted(set(t['net'] for t in land_hits)),'pads',[(p['ref'],p['pin']) for p in pads])
(m.HERE/'open_notch_screen.json').write_text(json.dumps(results,indent=2)+'\n')
fig,axs=plt.subplots(1,2,figsize=(12,6),layout='constrained')
for ax,layer in zip(axs,['F.Cu','B.Cu']):
 ax.set_aspect('equal');ax.set_xlim(52.6,77.4);ax.set_ylim(61.5,50.5);ax.grid(alpha=.15);ax.set_title(layer);ax.set_xlabel('Board X (mm)');ax.set_ylabel('Board Y (mm)')
 for t in m.tracks:
  if t['layer']==layer:ax.add_patch(MPolygon(np.array(t['geom'].exterior.coords),color=m.colors.get(t['net'],'#bcc7d1'),alpha=.8))
 for p in m.pads:
  if layer in p['layer'] or '*.Cu' in p['layer']:
   ax.add_patch(MPolygon(np.array(p['geom'].exterior.coords),color=m.colors.get(p['net'],'#bcc7d1'),alpha=.8))
 for ref in ['U4','C5','U3','FB1','R15','R16']:
  bb=m.bounds[ref].get(layer.replace('.Cu','.CrtYd'))
  if bb:
   ax.add_patch(MPolygon(np.array(box(*bb).exterior.coords),fill=False,edgecolor='#333',linestyle='--',lw=.8));ax.text((bb[0]+bb[2])/2,(bb[1]+bb[3])/2,ref,ha='center',fontsize=8)
 for x in [53.3165,76.6755]:ax.axvline(x,color='black',lw=1.5)
 for side in ['left','right']:
  cut,land=shapes(side,54.5)
  parts=list(land.geoms) if hasattr(land,'geoms') else [land]
  for p in parts:ax.add_patch(MPolygon(np.array(p.exterior.coords),facecolor='#eab308',edgecolor='black',alpha=.7))
  ax.add_patch(MPolygon(np.array(cut.exterior.coords),facecolor='white',edgecolor='black'))
fig.suptitle('Provisional open unplated notch at y54.5: 1.0 × 1.5 mm cut, GND lands on both faces\nActual copper under overlay shows required reroutes; panel fit and native DRC not verified',fontsize=11)
fig.savefig(m.HERE/'open_notch_layout.png',dpi=180)
