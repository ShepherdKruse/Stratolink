#!/usr/bin/env python3
from pathlib import Path
import json,itertools
from shapely.geometry import Polygon
from shapely.ops import unary_union
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon as MP
H=Path(__file__).resolve().parent;d=json.loads((H/'geometry-native.json').read_text())
def geom(ps):return unary_union([Polygon(p['shell'],p['holes']) for p in ps])
others=[(o,geom(o['polygons'])) for o in d['foreign_copper']]
results=[]
for m in ['0.102','0.05','0.025','0.015','0.005','0','-0.005']:
 pads=[(p,geom(p['alternatives'][m])) for p in d['pads']]
 pairs=[]
 for (a,ga),(b,gb) in itertools.combinations(pads,2):
  pairs.append(dict(pads=[a['number'],b['number']],nets=[a['net'],b['net']],gap_mm=ga.distance(gb),overlap_area_mm2=ga.intersection(gb).area))
 traces=[]
 for p,g in pads:
  nearest=sorted([(g.distance(gg),o) for o,gg in others if o['net']!=p['net']],key=lambda x:x[0])[:3]
  traces.append(dict(pad=p['number'],closest_foreign_copper=[{k:v for k,v in o.items() if k!='polygons'}|dict(gap_mm=dist) for dist,o in nearest]))
 results.append(dict(margin_mm=float(m),minimum_pair_gap_mm=min(p['gap_mm'] for p in pairs),overlapping_pairs=[p for p in pairs if p['overlap_area_mm2']>1e-10],pairs_with_gap_below_0p13_mm=[p for p in pairs if p['gap_mm']<.13],nearest_foreign_copper=traces))
(H/'geometry-screen.json').write_text(json.dumps(dict(source_sha256=d['source_sha256'],alternatives=results),indent=2)+'\n')
for r in results:
 print('margin',r['margin_mm'],'minpairgap',round(r['minimum_pair_gap_mm'],6),'overlaps',len(r['overlapping_pairs']),'differentnet',sum(p['nets'][0]!=p['nets'][1] for p in r['overlapping_pairs']),'minforeign',min(o['gap_mm'] for p in r['nearest_foreign_copper'] for o in p['closest_foreign_copper']))
fig,axs=plt.subplots(1,2,figsize=(11,6),layout='constrained')
for ax,margin in zip(axs,['0.102','0']):
 ax.set_aspect('equal');ax.set_xlim(69.1,72);ax.set_ylim(39.25,36.35);ax.set_title('Existing +0.102 mm margin' if margin=='0.102' else 'Selected explicit 0.000 mm margin');ax.grid(alpha=.15)
 for p in d['pads']:
  for q in p['alternatives'][margin]:ax.add_patch(MP(q['shell'],facecolor='#3bb897',edgecolor='#137059',alpha=.35))
  for q in p['alternatives']['0']:ax.add_patch(MP(q['shell'],facecolor='#d09d37',edgecolor='#775006',alpha=.9,lw=.7))
  x,y=p['at_mm'];ax.text(x,y,p['number'],ha='center',va='center',fontsize=9)
 ax.set_xlabel('Board x (mm)');ax.set_ylabel('Board y (mm)')
fig.suptitle('U7 LIS2DH12: copper unchanged; mask openings no longer overlap\nMinimum corner web 0.100 mm at pads 4–5; row webs 0.150 mm',fontsize=12)
fig.savefig(H/'mask-before-after.png',dpi=180)
