#!/usr/bin/env python3
"""Read-only suspension-hole feasibility screen using native copper polygons."""
from pathlib import Path
import json,math,csv
import numpy as np
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as Patch
HERE=Path(__file__).resolve().parent
d=json.loads((HERE/'native.json').read_text())
def geom(rows): return unary_union([Polygon(p['shell'],p['holes']) for p in rows])
for row in d['items']+d['courtyards']+d['zones']:row['geometry']=geom(row['polygons'])
outer=Polygon(d['outline'][0]['shell'])
holes=[e for e in d['edges'] if e['shape']=='Circle']
holes.sort(key=lambda e:e['center_mm'][0])
rows=[]; closest=[]
def clean(row):return {k:v for k,v in row.items() if k not in ['polygons','geometry']}
for side,hole,inward in zip(['left','right'],holes,[1,-1]):
 centre=Point(hole['center_mm'])
 for layer in ['F.Cu','B.Cu']:
  copper=sorted([r for r in d['items'] if r['layer']==layer],key=lambda r:centre.distance(r['geometry']))
  closest.append(dict(side=side,layer=layer,nearest=[clean(r)|{'centre_to_copper_mm':centre.distance(r['geometry']),'hole_wall_to_copper_mm':centre.distance(r['geometry'])-hole['radius_mm']} for r in copper[:8]]))
 for shift in [0,.3,.5,1.0]:
  for mode in (['diagonal'] if shift==0 else ['inward','down','diagonal']):
   c=(hole['center_mm'][0]+(shift*inward if mode in ['inward','diagonal'] else 0),hole['center_mm'][1]+(shift if mode in ['down','diagonal'] else 0))
   for diameter,od in [(hole['radius_mm']*2,None),(2.2,None),(2.0,None),(hole['radius_mm']*2,2.5),(hole['radius_mm']*2,3.0),(hole['radius_mm']*2,3.5),(2.2,3.2),(2.0,3.2)]:
    centre=Point(c);radius=diameter/2;pad=centre.buffer((od if od else diameter)/2,quad_segs=256)
    copper=[r for r in d['items'] if not od or r['net']!='GND']
    nearest=min(copper,key=lambda r:centre.distance(r['geometry']))
    ct=min(d['courtyards'],key=lambda r:centre.distance(r['geometry']))
    clearance=centre.distance(nearest['geometry'])-((od or diameter)/2)
    dx=abs(c[0]-hole['center_mm'][0]);dy=c[1]-hole['center_mm'][1];R=2.348
    edge_distance=R+min(dx,dy)
    r=dict(side=side,mode=mode,shift_mm=shift,x_mm=c[0],y_mm=c[1],hole_diameter_mm=diameter,pad_od_mm=od,annulus_mm=(od-diameter)/2 if od else None,
           min_FR4_ligament_mm=edge_distance-radius,
           top_ligament_mm=R+dy-radius,side_ligament_mm=R+dx-radius,
           corner_arc_ligament_mm=min(math.hypot(R+dx,dy),math.hypot(dx,R+dy))-radius,
           min_FR4_ligament_polygon_mm=centre.distance(outer.boundary)-radius,
           min_pad_outer_edge_clearance_mm=edge_distance-od/2 if od else None,
           min_copper_clearance_mm=clearance,nearest_copper=clean(nearest),
           min_pad_to_courtyard_mm=centre.distance(ct['geometry'])-(od or diameter)/2,nearest_courtyard=clean(ct),
           copper_screen_pass=clearance>=(.15 if od else .20),
           pad_edge_screen_pass=(edge_distance-od/2>=.20) if od else True,
           physically_valid_ring=od is None or od>diameter)
    if od:
     r['existing_ground_fill_overlap_mm2']={layer:sum(pad.intersection(z['geometry']).area for z in d['zones'] if z['layer']==layer and z['net']=='GND') for layer in ['F.Cu','B.Cu']}
    rows.append(r)
report=dict(source_sha256=d['source_sha256'],method='Native-object polygon envelope screen; copper distances omit refill-dependent zones except separately reported GND-fill overlap. Grounded ring candidates ignore same-net GND tracks/pads. NPTH screen .20 mm, PTH GND ring .15 mm copper/.20 mm edge. Outer ligament uses analytical nominal R2.348 corner geometry; also reports native polygon approximation, which is about0.003mm low at concentric centers. No native DRC or fabrication release.',holes=holes,closest_existing_copper=closest,candidates=rows)
(HERE/'screen.json').write_text(json.dumps(report,indent=2)+'\n')
fields=['side','mode','shift_mm','x_mm','y_mm','hole_diameter_mm','pad_od_mm','annulus_mm','min_FR4_ligament_mm','min_pad_outer_edge_clearance_mm','min_copper_clearance_mm','min_pad_to_courtyard_mm','copper_screen_pass','pad_edge_screen_pass','physically_valid_ring']
with (HERE/'screen.csv').open('w') as f:
 w=csv.DictWriter(f,fields);w.writeheader();w.writerows({k:r[k] for k in fields} for r in rows)
for r in rows:
 if (r['pad_od_mm']==3.2 or r['pad_od_mm'] is None and r['hole_diameter_mm']<2.3) and r['mode']=='diagonal':
  print(r['side'],r['shift_mm'],r['hole_diameter_mm'],r['pad_od_mm'],'ligament',round(r['min_FR4_ligament_mm'],3),'cu',round(r['min_copper_clearance_mm'],3),r['nearest_copper'].get('net'),'ct',round(r['min_pad_to_courtyard_mm'],3),r['nearest_courtyard']['ref'])
colors={'GND':'#929ca8','+SOLAR':'#f69b29','VSTOR':'#cc374c','+3.3V':'#ab42c8','Net-(D3-A1)':'#22aa55'}
fig,axes=plt.subplots(1,2,figsize=(13,5),layout='constrained')
for ax,layer in zip(axes,['F.Cu','B.Cu']):
 ax.set_aspect('equal');ax.set_xlim(52.8,77.2);ax.set_ylim(37,28.8);ax.set_title(layer);ax.set_xlabel('X (mm)');ax.set_ylabel('Y (mm)');ax.grid(alpha=.15)
 for zone in d['zones']:
  if zone['layer']!=layer:continue
  for p in zone['polygons']:ax.add_patch(Patch(p['shell'],facecolor='#d6e7d6',edgecolor='none',alpha=.5))
 for r in d['items']:
  if r['layer']!=layer:continue
  for p in r['polygons']:ax.add_patch(Patch(p['shell'],facecolor=colors.get(r['net'],'#668aad'),edgecolor='none'))
 for r in d['courtyards']:
  if r['layer']!=layer.replace('.Cu','.CrtYd'):continue
  for p in r['polygons']:
   ax.add_patch(Patch(p['shell'],fill=False,edgecolor='#444',linestyle=':',linewidth=.8))
   g=Polygon(p['shell']);x,y=g.centroid.coords[0]
   if 29<y<37:ax.text(x,y,r['ref'],ha='center',va='center',fontsize=7)
 ax.plot(*outer.exterior.xy,color='black',lw=1)
 for hole in holes:
  c=Point(hole['center_mm']);ax.plot(*c.buffer(hole['radius_mm']).exterior.xy,'k--',lw=1)
  ax.plot(*c.buffer(1.0).exterior.xy,color='#1784d2',lw=2)
  ax.plot(*c.buffer(1.6).exterior.xy,color='#1784d2',lw=1)
fig.suptitle('Top suspension geometry: existing 2.701 mm cutout dashed; 2.0 mm hole / 3.2 mm GND pad blue\nStudy only: filled GND shown pale; original fill has not been regenerated',fontsize=11)
fig.savefig(HERE/'top-corners.png',dpi=180)
