#!/usr/bin/env python3
"""Read-only geometry screen. Not a native DRC or a fabrication design."""
from pathlib import Path
import sys,json,math,hashlib,subprocess
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MPolygon
from shapely.geometry import Point,LineString,Polygon,box
from shapely.affinity import rotate,translate
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
import cad_helpers as a
BASELINE='1aed52ff7af3d27aef6ff4b0ceba710c57dc6865'
source_bytes=subprocess.check_output(['git','show',BASELINE+':hardware/pcb/stratolink.kicad_pcb'],cwd=ROOT)
b=a.parse(source_bytes.decode());fps={a.prop(f,'Reference'):f for f in a.nodes(b,'footprint')}
tracks=[dict(uuid=a.scalar(s,'uuid'),net=a.scalar(s,'net'),layer=a.scalar(s,'layer'),start=a.floats(s,'start'),end=a.floats(s,'end'),width=float(a.scalar(s,'width'))) for s in a.nodes(b,'segment')]
for t in tracks:t['geom']=LineString([t['start'],t['end']]).buffer(t['width']/2)
vias=[dict(uuid=a.scalar(v,'uuid'),net=a.scalar(v,'net'),at=a.floats(v,'at'),size=float(a.scalar(v,'size')),drill=float(a.scalar(v,'drill'))) for v in a.nodes(b,'via')]
for v in vias:v['geom']=Point(v['at']).buffer(v['size']/2)
pads=[];bounds={}
for ref,f in fps.items():
 bounds[ref]={}
 for layer in ['F.CrtYd','B.CrtYd','F.Fab','B.Fab']:
  pts=[]
  for g in f:
   if isinstance(g,list) and g[0].startswith('fp_') and a.scalar(g,'layer')==layer:
    for key in ['start','end','center']:
     p=a.floats(g,key)
     if p:pts.append(a.point_global(f,p))
  if pts:bounds[ref][layer]=[min(p[0] for p in pts),min(p[1] for p in pts),max(p[0] for p in pts),max(p[1] for p in pts)]
 for p in a.nodes(f,'pad'):
  w,h=a.floats(p,'size');xy=a.point_global(f,a.floats(p,'at',[0,0]));ang=a.floats(p,'at',[0,0,0]);ang=ang[2] if len(ang)>2 else 0
  if p[3]=='circle':g=Point(0,0).buffer(w/2)
  elif p[3]=='oval':g=LineString([(0,-(h-w)/2),(0,(h-w)/2)]).buffer(w/2) if h>=w else LineString([(-(w-h)/2,0),((w-h)/2,0)]).buffer(h/2)
  else:g=box(-w/2,-h/2,w/2,h/2)
  g=translate(rotate(g,-ang,origin=(0,0)),*xy)
  pads.append(dict(ref=ref,pin=p[1],net=a.scalar(p,'net',''),layer=a.one(p,'layers'),at=xy,size=[w,h],geom=g))

def capsule(x,y,w,h):
 return LineString([(x,y-(h-w)/2),(x,y+(h-w)/2)]).buffer(w/2)
def screen(label,centers,size,net):
 out=[]
 for side,(x,y) in zip(['left','right'],centers):
  g=capsule(x,y,*size)
  clashes=[{k:t[k] for k in ['uuid','net','layer','start','end','width']}|{'distance_mm':g.distance(t['geom']),'overlap_area_mm2':g.intersection(t['geom']).area} for t in tracks if t['net']!=net and g.distance(t['geom'])<.2]
  padclashes=[{k:p[k] for k in ['ref','pin','net','at','size']} for p in pads if p['ref'] not in ['J1','J2'] and p['net']!=net and g.distance(p['geom'])<.2]
  mechanical=[]
  for ref,bds in bounds.items():
   if ref in ['J1','J2']:continue
   for layer,bb in bds.items():
    if 'CrtYd' in layer and g.distance(box(*bb))<.2:mechanical.append({'ref':ref,'layer':layer,'bounds':bb,'distance_mm':g.distance(box(*bb))})
  out.append(dict(label=label,side=side,center_mm=[x,y],pad_size_mm=size,net=net,track_conflicts=clashes,pad_conflicts=padclashes,courtyard_nearby=mechanical))
 return out
candidates={
 'middle_ground_55p5':([(54.8,55.5),(74.6,55.5)],(1.6,3.2),'GND'),
 'middle_ground_56p0':([(54.8,56),(74.6,56)],(1.6,3.2),'GND'),
 'middle_positive_59p5':([(54.8,59.5),(74.6,59.5)],(1.6,1.6),'+SOLAR'),
 'upper_ground_39p0':([(54.8,39),(74.6,39)],(1.6,3.2),'GND'),
 'upper_ground_34p5':([(54.8,34.5),(74.6,34.5)],(1.6,3.2),'GND'),
 'upper_positive_42p5':([(54.8,42.5),(74.6,42.5)],(1.6,1.6),'+SOLAR'),
}
results=sum([screen(k,*v) for k,v in candidates.items()],[])
(HERE/'candidate_screen.json').write_text(json.dumps({'source_sha256':hashlib.sha256(source_bytes).hexdigest(),'method':'Copper geometry screening at 0.20 mm, unfilled zones excluded; pad rectangles conservative; distance_mm is zero for overlap; overlap_area_mm2 reports its area separately. No claim of fabrication approval.','bounds':bounds,'candidates':results},indent=2)+'\n')
for r in results:
 print(r['label'],r['side'],'tracks',len(r['track_conflicts']),'nets',sorted(set(t['net'] for t in r['track_conflicts'])),'pads',[(p['ref'],p['pin']) for p in r['pad_conflicts']],'courtyards',[(p['ref'],p['layer']) for p in r['courtyard_nearby']])
colors={'GND':'#6b7280','+SOLAR':'#d97706','VSTOR':'#dc2626','PB5':'#9333ea','RX':'#0891b2','TX':'#2563eb','SDA':'#16a34a','SCL':'#059669','+3.3V':'#db2777'}
fig,axs=plt.subplots(2,2,figsize=(13,10),layout='constrained')
for row,(yy,title) in enumerate([((51.5,62),'Middle mounts: freed microphone space left; MS5611 right'),((31.5,44),'Upper mounts: power and temperature-sensor neighbourhood')]):
 for col,layer in enumerate(['F.Cu','B.Cu']):
  ax=axs[row,col];ax.set_aspect('equal');ax.set_xlim(52.6,77.4);ax.set_ylim(yy[1],yy[0]);ax.set_title(title+'\n'+layer,fontsize=10);ax.set_xlabel('Board X (mm)');ax.set_ylabel('Board Y (mm)');ax.grid(alpha=.12)
  for t in tracks:
   if t['layer']==layer:
    g=t['geom'];ax.add_patch(MPolygon(np.array(g.exterior.coords),color=colors.get(t['net'],'#b7c3ce'),alpha=.8))
  for p in pads:
   if layer in p['layer'] or '*.Cu' in p['layer']:
    ax.add_patch(MPolygon(np.array(p['geom'].exterior.coords),color=colors.get(p['net'],'#b7c3ce'),alpha=.9))
  for ref,bds in bounds.items():
   for l,bb in bds.items():
    if l==layer.replace('.Cu','.CrtYd'):
     ax.add_patch(MPolygon(np.array(box(*bb).exterior.coords),fill=False,edgecolor='#333',linestyle='--',linewidth=.65))
     if bb[1]>=yy[0] and bb[3]<=yy[1]:ax.text((bb[0]+bb[2])/2,(bb[1]+bb[3])/2,ref,fontsize=7,ha='center',va='center')
  for x in [53.317,76.675]:ax.axvline(x,color='black',lw=1)
  for r in results:
   use=r['label'] in (['middle_ground_55p5','middle_positive_59p5'] if row==0 else ['upper_ground_39p0','upper_positive_42p5'])
   if use:
    g=capsule(*r['center_mm'],*r['pad_size_mm']);ax.add_patch(MPolygon(np.array(g.exterior.coords),facecolor='white',edgecolor='black',lw=1.7,alpha=.65));ax.text(*r['center_mm'],'GND' if r['net']=='GND' else '+',fontsize=6,ha='center',va='center',rotation=90 if r['net']=='GND' else 0)
fig.suptitle('Proposed contact envelopes over actual copper: study only, routes not yet changed',fontsize=13)
fig.savefig(HERE/'candidate_layout.png',dpi=180)
