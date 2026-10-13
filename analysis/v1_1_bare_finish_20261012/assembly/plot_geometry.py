#!/usr/bin/env python3
"""Audit native-exported model projections and plot assembly envelopes."""
from pathlib import Path
import json,re,math,sys
import numpy as np
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as Patch,Circle,Rectangle,FancyBboxPatch
from shapely.geometry import Polygon,Point,box
from shapely.affinity import rotate,translate
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE));import build_candidate as build
SCRATCH=build.OUT.parent;doc=(SCRATCH/'wire-candidate.wrl').read_text()
blocks=re.findall(r'Transform\s*\{\s*rotation ([^\n]+)\n\s*translation ([^\n]+)\n\s*scale ([^\n]+)\n\s*children\s*\[\s*Inline\s*\{\s*url "([^"]+)"',doc)
def rotation(v):
 x=np.array([float(x) for x in v.split()]);u=x[:3]/np.linalg.norm(x[:3]);t=x[3];K=np.array([[0,-u[2],u[1]],[u[2],0,-u[0]],[-u[1],u[0],0]])
 return math.cos(t)*np.eye(3)+(1-math.cos(t))*np.outer(u,u)+math.sin(t)*K
def vertices(path):
 t=Path(path).read_text();pts=[]
 for block in re.findall(r'Coordinate\s*\{\s*point\s*\[([^\]]+)\]',t,re.S):
  nums=[float(n) for n in re.findall(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?',block)]
  assert len(nums)%3==0;pts.extend(np.array(nums).reshape(-1,3))
 assert len(pts)>50
 return np.array(pts)
b1=next(b for b in blocks if b[3].endswith('Stratolink_Wire_82mm_D0p321_Nominal.wrl'));t=np.array([float(n) for n in b1[1].split()])*2.54
origin=np.array([68.396-t[0],82.703+t[1]])
geom={};clouds={};polys={}
for ref,part in build.PARTS.items():
 block=next(b for b in blocks if b[3].endswith(Path(part['model']).with_suffix('.wrl').name));raw=vertices(block[3]);world=(raw@rotation(block[0]).T+np.array([float(n) for n in block[1].split()]))*2.54
 world[:,0]+=origin[0];world[:,1]=origin[1]-world[:,1]
 pos,angle=([68.396,82.703],-90) if ref=='AE1' else ([62.882,33.218],90)
 court=translate(rotate(Polygon(part['points']),-angle,origin=(0,0)),*pos);project=Polygon(world[:,:2]).convex_hull
 # Native export serialization rounds transforms; 0.0001 mm is only a numerical allowance.
 assert court.buffer(.0001).covers(project),(ref,project.bounds,court.bounds)
 clouds[ref]=world;polys[ref]=court
 geom[ref]=dict(model_vertices=len(raw),model_bounds_board_mm=[world.min(axis=0).tolist(),world.max(axis=0).tolist()],courtyard_bounds_mm=list(court.bounds),model_projection_inside_courtyard=True,diameter_mm_nominal=.321,insertion_leg_mm_nominal=2,margin_model_to_courtyard_mm=court.boundary.distance(project))
diode=box(71.058-1.25,82.813-.7,71.058+1.25,82.813+.7);body=box(71.058-.65,82.813-.45,71.058+.65,82.813+.45)
pad2=box(70.357999-.15,82.813-.2,70.357999+.15,82.813+.2).buffer(.15,quad_segs=64);land=Point(68.396,82.703).buffer(.75,quad_segs=128)
geom['D1_AE1']=dict(courtyard_clearance_mm=polys['AE1'].distance(diode),ant_land_to_diode_nearest_land_mm=land.distance(pad2),recorded_diode_fab_body_to_model_projection_mm=body.distance(Polygon(clouds['AE1'][:,:2]).convex_hull),original_courtyard_overlap_area_mm2=box(68.396-3.75,82.703-1.75,68.396+3.75,82.703+17.5).intersection(diode).area)
(HERE/'geometry.json').write_text(json.dumps(geom,indent=2)+'\n')
fig,axs=plt.subplots(1,3,figsize=(13,7),gridspec_kw={'width_ratios':[1.6,1,1]});fig.patch.set_facecolor('white')
for ax in axs:ax.set_aspect('equal');ax.grid(alpha=.15);ax.set_xlabel('X (mm)');ax.set_ylabel('Y (mm)')
ax=axs[0];old=box(68.396-3.75,82.703-1.75,68.396+3.75,82.703+17.5)
ax.add_patch(Patch(np.array(old.exterior.coords),fill=False,color='#b64949',linestyle='--',label='Old spring courtyard'))
ax.add_patch(Patch(np.array(polys['AE1'].exterior.coords),fill=False,color='#1f8063',linewidth=2,label='Wire assembly reserve'))
ax.add_patch(Patch(np.array(diode.exterior.coords),fill=False,color='#4968a6',linewidth=2,label='D1 unchanged courtyard'))
ax.add_patch(Patch(np.array(body.exterior.coords),facecolor='#444',alpha=.8,label='D1 recorded body (F.Fab)'))
for cx in [70.357999,71.758001]:ax.add_patch(FancyBboxPatch((cx-.3,82.813-.35),.6,.7,boxstyle='round,pad=0,rounding_size=.15',facecolor='#b98638',zorder=3))
ax.add_patch(Circle((68.396,82.703),.75,color='#b98638'));ax.add_patch(Circle((68.396,82.703),.5,color='white',zorder=5))
ax.add_patch(Patch(np.array(Polygon(clouds['AE1'][:,:2]).convex_hull.exterior.coords),facecolor='#ba702a',edgecolor='none',label='Native-exported wire model'))
ax.annotate('0.162 mm courtyard gap',xy=(69.727,82.6),xytext=(69.4,80.1),arrowprops={'arrowstyle':'->'},ha='center',fontsize=9)
ax.set_xlim(66.6,73);ax.set_ylim(86,79.5);ax.set_title('AE1 / D1 local assembly clearance')
ax.legend(loc='lower left',fontsize=7)
for ax,ref in zip(axs[1:],['AE1','AE2']):
 poly=polys[ref];v=clouds[ref];ax.add_patch(Patch(np.array(poly.exterior.coords),fill=False,color='#1f8063',linewidth=1.5));ax.add_patch(Patch(np.array(Polygon(v[:,:2]).convex_hull.exterior.coords),facecolor='#ba702a',edgecolor='none'));pad=np.array([68.396,82.703]) if ref=='AE1' else np.array([62.882,33.218]);ax.add_patch(Circle(pad,.75,color='#b98638'));ax.set_xlim(pad[0]-4,pad[0]+4);ax.set_ylim(poly.bounds[3]+2,poly.bounds[1]-2);ax.set_title(ref+(' LoRa: 82 mm reference\n86 mm variant fits reserve' if ref=='AE1' else ' GNSS L1: 48 mm'));ax.text(.5,.98,'Diameter / bend are nominal',ha='center',va='top',fontsize=7,transform=ax.transAxes)
fig.suptitle('Straight enameled-wire antennas: copper and RF routing unchanged',fontsize=14)
fig.tight_layout();fig.savefig(HERE/'wire-assembly-clearance.png',dpi=180);plt.close(fig)
print(json.dumps(geom,indent=2))
