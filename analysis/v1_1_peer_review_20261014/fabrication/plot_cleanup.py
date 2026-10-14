#!/usr/bin/env python3
from pathlib import Path
import json
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
HERE=Path(__file__).resolve().parent
before=json.loads((HERE/'current-geometry.json').read_text());after=json.loads((HERE/'copper-final4-geometry.json').read_text())
regions=[('Balancer pad/via neck','B.Cu',(56.1,34.75,57.9,36.1)),('U1 front ground voids','F.Cu',(66.65,37.3,67.75,38.35)),('Upper rail and UV notches','F.Cu',(68.1,34.8,75.1,36.5)),('J20 ground joins','F.Cu',(55.4,64.6,57.1,66.1)),('Upper copper label tips','F.Cu',(55,34.9,57.4,42.5)),('Logo details','F.Cu',(60.2,56.1,62.9,57.3))]
fig,axs=plt.subplots(len(regions),2,figsize=(12,19))
for row,(title,layer,b) in enumerate(regions):
 for col,(label,d) in enumerate([('Before',before),('After',after)]):
  ax=axs[row,col]
  for poly in sorted(d['copper'][layer],key=lambda p:abs(sum(p['shell'][i][0]*p['shell'][(i+1)%len(p['shell'])][1]-p['shell'][(i+1)%len(p['shell'])][0]*p['shell'][i][1] for i in range(len(p['shell'])))),reverse=True):
   ax.add_patch(Polygon(poly['shell'],color='#548c5c',lw=0))
   for h in poly['holes']:ax.add_patch(Polygon(h,color='white',lw=0))
  ax.set_xlim(b[0],b[2]);ax.set_ylim(b[3],b[1]);ax.set_aspect('equal');ax.grid(alpha=.15);ax.set_title(f'{title} / {label}',fontsize=10)
fig.tight_layout();fig.savefig(HERE/'candidate/before-after.png',dpi=180);fig.savefig(HERE/'candidate/before-after.pdf')
