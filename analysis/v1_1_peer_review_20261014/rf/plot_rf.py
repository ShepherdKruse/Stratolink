from pathlib import Path
import json
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
HERE=Path(__file__).resolve().parent;d=json.loads((HERE/'native-rf-geometry.json').read_text());fig,axs=plt.subplots(1,2,figsize=(16,11))
for ax,layer in zip(axs,['F.Cu','B.Cu']):
 # Paint fill/holes first so the diagnostic never erases foreground pad/track copper.
 for i in sorted(d['items'],key=lambda item: item['kind']!='zone'):
  if i['layer']!=layer:continue
  col='#bdd5b7' if i['net']=='GND'else '#555555';alpha=.6 if i['kind']=='zone'else .8
  if i['net']=='Net-(AE2-A)':col='#c800d0';alpha=1
  if i['net']=='Net-(U1-LBOOST)':col='#df1c15';alpha=1
  if i['net']=='Net-(U1-LBUCK)':col='#ff8100';alpha=1
  if i['net']=='+3.3V':col='#1757c7'
  if i['net']=='VSTOR':col='#a99100'
  for p in i['polygons']:
   ax.add_patch(Polygon(p['shell'],color=col,alpha=alpha,lw=0))
   for h in p['holes']:ax.add_patch(Polygon(h,color='white',lw=0))
  if i['kind']=='pad' and 52<i['at'][0]<77 and 29<i['at'][1]<46:ax.text(*i['at'],i['ref']+'.'+i['pin'],fontsize=5,zorder=9)
 for f,info in d['footprints'].items():
  if info['layer']==layer and 52<info['at'][0]<77 and 29<info['at'][1]<46:ax.text(*info['at'],f,color='#000000',fontsize=9,fontweight='bold',zorder=10)
 ax.plot([62.882,62.882],[33.218,43.490575],color='#d000d0',ls='--',lw=1.4,zorder=15)
 ax.set_xlim(52,77);ax.set_ylim(46,29);ax.set_aspect('equal');ax.grid(alpha=.2);ax.set_title(layer+'; GNSS magenta / boost red / buck orange')
fig.tight_layout();fig.savefig(HERE/'rf-top-copper.png',dpi=180)
