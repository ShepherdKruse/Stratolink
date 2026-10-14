from pathlib import Path
import json
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.path import Path as MPath
from matplotlib.patches import PathPatch
from shapely.geometry import Polygon,box
from shapely.ops import unary_union
HERE=Path(__file__).resolve().parent;d=json.loads((HERE/'current-geometry.json').read_text())
views=[('B.Cu',57.15,35.45,2.2,1.7,'U8 output neck'),('F.Cu',70.0,61.9,2.0,2.0,'Ground route neck'),('F.Cu',67.191,37.815,1.6,1.6,'Front U1 thermal copper gaps'),('F.Cu',73.825,35.6,.8,.8,'U6 ground junction'),('B.Cu',71.22,41.71,.65,.65,'Rear +3.3 V pocket'),('B.Cu',75.06,80.94,1.3,1.3,'Inherited sub-micron slit')]
fig,axs=plt.subplots(2,3,figsize=(15,10))
for ax,(layer,x,y,w,h,title) in zip(axs.flat,views):
 clip=box(x-w/2,y-h/2,x+w/2,y+h/2)
 for p in d['copper'][layer]:
  g=Polygon(p['shell'],p['holes']).intersection(clip)
  pieces=[g] if g.geom_type=='Polygon' else list(g.geoms) if g.geom_type in ['MultiPolygon','GeometryCollection'] else []
  for poly in pieces:
   if poly.geom_type!='Polygon' or poly.is_empty:continue
   verts=[];codes=[]
   for ring in [poly.exterior,*poly.interiors]:
    pts=list(ring.coords);verts+=pts;codes += [MPath.MOVETO]+[MPath.LINETO]*(len(pts)-2)+[MPath.CLOSEPOLY]
   ax.add_patch(PathPatch(MPath(verts,codes),facecolor='#b66232',edgecolor='#5f351b',lw=.4))
 ax.plot(x,y,'r+',markersize=10);ax.set_xlim(x-w/2,x+w/2);ax.set_ylim(y+h/2,y-h/2);ax.set_aspect('equal');ax.grid(alpha=.3);ax.set_title(title+' '+layer);ax.set_xlabel('mm');ax.set_ylabel('mm')
fig.tight_layout();fig.savefig(HERE/'geometry-details.png',dpi=180)
