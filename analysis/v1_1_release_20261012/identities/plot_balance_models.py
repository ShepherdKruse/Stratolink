from pathlib import Path
import json
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Circle
HERE=Path(__file__).resolve().parent;j=json.loads((HERE/'balance-placement-model-review.json').read_text())
fig=plt.figure(figsize=(13,10));axes=[fig.add_axes([.05,.17,.42,.68]),fig.add_axes([.54,.22,.41,.63])]
for ax,zoom in zip(axes,[False,True]):
 ax.add_patch(Rectangle((53.3165,29.397),23.359,57.298,fill=False,color='#687078',lw=1.2))
 ax.add_patch(Rectangle((57.875,49.707),14,30,facecolor='#ddd',edgecolor='#777',alpha=.55))
 if not zoom:ax.text(64.875,61,'C5 body\nnominal 30 × 14 mm',ha='center',va='center',fontsize=10,color='#4c4c4c')
 for ref,d in j['models'].items():
  if ref in ['C5','AE2']:continue
  b=d['bounds_mm'];x0,y0=b[0][0],-b[1][1];w,h=b[1][0]-b[0][0],b[1][1]-b[0][1]
  if zoom and y0>44:continue
  new=ref in ['U8','R24','R25','R26','C22'];front=ref in ['U3','D3'];c='#2a7693' if new else '#888'
  ax.add_patch(Rectangle((x0,y0),w,h,facecolor=c if new else 'none',edgecolor=c,alpha=.65,ls='--' if front else '-'))
  if zoom or ref in ['U8','U3','L1']:
   ax.text(x0+w/2,y0+h+.2 if ref=='L1' else y0+h/2,ref,ha='center',va='center',fontsize=8,color='white' if new else '#333',clip_on=True)
 for x,label in [(55.665,'H1'),(74.327,'H2')]:
  ax.add_patch(Circle((x,31.745),1.6,fill=False,ec='#a48447'));ax.add_patch(Circle((x,31.745),1,fill=False,ec='#333'))
  if not zoom or label=='H1':ax.text(x,29.7,label,ha='center',fontsize=8)
 for x in [53.3165,76.6755]:ax.plot([x-1,x+1],[54.5,54.5],color='#ab6d36',lw=4)
 ax.set_aspect('equal');ax.set_xlim((53,63.1) if zoom else (51.5,78.5));ax.set_ylim((44,29) if zoom else (87.5,28.3));ax.grid(alpha=.12);ax.set_xlabel('Board X (mm)');ax.set_ylabel('Board Y (mm)');ax.set_title('Upper-left rear detail' if zoom else 'Board XY projection')
fig.suptitle('Balancer placement — projected native model envelopes',y=.96,fontsize=15)
fig.text(.5,.91,'Final integrated model registration verified; nominal geometry passes; physical pilot remains',ha='center',fontsize=11)
fig.text(.54,.065,'Smallest nominal gaps: C5 2.707 mm; new bodies 0.533 mm\nH1 hole-to-model XY lower bound: 1.270 mm\nSolar assembly lower bound: 12.014 mm; positive wire: 35.786 mm\nDashed models are on the opposite face. This is not a strength test.',fontsize=10,va='bottom')
fig.savefig(HERE/'balance-placement-model-review.png',dpi=150)
