import gzip
from pathlib import Path
import json,numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MP
from shapely.geometry import Polygon,box
H=Path(__file__).resolve().parent;d=json.loads(gzip.decompress((H/'regions.json.gz').read_bytes()))
fig,axs=plt.subplots(2,2,figsize=(11,11),layout='constrained')
for i,(label,data) in enumerate(d.items()):
 for j,(ref,bounds) in enumerate([('U7',(69,36,72.5,39.5)),('J20',(59.5,82.5,64,86.5))]):
  ax=axs[j,i];ax.set_aspect('equal');x0,y0,x1,y1=bounds;roi=box(*bounds);ax.set_xlim(x0,x1);ax.set_ylim(y1,y0);ax.set_title(label+' '+ref);ax.grid(alpha=.15)
  for p in data['zones']:
   if not Polygon(p['shell']).intersects(roi):continue
   ax.add_patch(MP(p['shell'],fc='#82bd8d',ec='none',alpha=.8))
   for hole in p['holes']:ax.add_patch(MP(hole,fc='white',ec='none'))
  for o in data['items']:
   for p in o['polygons']:
    if len(p['shell'])<3 or not Polygon(p['shell']).intersects(roi):continue
    ax.add_patch(MP(p['shell'],fc=('#cba046' if o['type']=='pad' else '#3f8155' if o['net']=='GND' else '#ce5365'),ec='none',alpha=.8))
   if o.get('ref')==ref:ax.text(*o['at'],o['pin'],ha='center',va='center',fontsize=9)
  ax.set_xlabel('Board x (mm)');ax.set_ylabel('Board y (mm)')
fig.suptitle('Native front-copper fill: baseline and rejected mixed-angle trial\nGreen=GND fill, gold=pads, red=foreign-net traces. Pad7 remains starved in trial.',fontsize=12)
fig.savefig(H/'regions-before-trial.png',dpi=180)
