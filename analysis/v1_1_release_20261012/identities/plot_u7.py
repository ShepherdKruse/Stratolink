from pathlib import Path
import json,math
from shapely.geometry import Polygon,box,Point
from shapely.ops import unary_union
import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent;x=json.loads((HERE/'u7-geometry-native.json').read_text());conv=lambda p:unary_union([Polygon(q['shell'],q['holes']) for q in p]);center=box(70.008,37.267,71.088,38.347);body=box(69.473,36.732,71.623,38.882);window=box(68.7,36.25,74,40.35);report={}
fig,axes=plt.subplots(2,2,figsize=(14,12))
def draw(ax,g,color,alpha=1):
 if g.is_empty:return
 for p in getattr(g,'geoms',[g]):
  if isinstance(p,Polygon):
   xx,yy=p.exterior.xy;ax.fill(xx,yy,color=color,alpha=alpha)
   for h in p.interiors:xx,yy=h.xy;ax.fill(xx,yy,color='white')
for row,label in enumerate(['before','after']):
 o=x[label];tracks=unary_union([conv(t['polygons']) for t in o['tracks'] if t['layer']=='F.Cu']);zone=conv(o['zones']['F.Cu']);report[label]={'central_track_area_mm2':tracks.intersection(center).area,'central_zone_area_mm2':zone.intersection(center).area,'central_all_top_copper_area_mm2':conv(o['copper']['F.Cu']).intersection(center.buffer(-.00001)).area}
 for col,layer in enumerate(['F.Cu','B.Cu']):
  ax=axes[row,col];draw(ax,conv(o['zones'][layer]).intersection(window),'#e2d4b8')
  for t in o['tracks']:
   if t['layer']==layer:draw(ax,conv(t['polygons']),'#b4893e' if t['net']=='GND' else '#278199')
  for p in o['pads']:
   if p['layer']==layer:
    q=conv(p['polygons']);draw(ax,q,'#244e62');ax.text(q.centroid.x,q.centroid.y,p['ref']+'.'+p['pad'],color='white',fontsize=7,ha='center',va='center')
  xx,yy=body.exterior.xy;ax.plot(xx,yy,color='black',ls='--',lw=1)
  xx,yy=center.exterior.xy;ax.plot(xx,yy,color='#bc3f43',ls='--',lw=1)
  ax.set_xlim(68.7,74);ax.set_ylim(40.35,36.25);ax.set_aspect('equal');ax.set_title(label.title()+' — '+layer)
fig.suptitle('U7 escape and stencil revision — native copper, unchanged lands',fontsize=16);fig.tight_layout();fig.savefig(HERE/'u7-before-after.png',dpi=160)
for layer in ['F.Cu','B.Cu']:
 aa,bb=[conv(x[l]['copper'][layer]) for l in ['before','after']];delta=aa.symmetric_difference(bb);report[layer]={'changed_area_mm2':delta.area,'delta_bounds_mm':delta.bounds,'outside_local_window_mm2':delta.difference(window).area}
near_land=conv(next(p for p in x['after']['pads'] if p['ref']=='C6' and p['pad']=='2')['polygons'])
report['power_via_to_C6_pad2']={'net_both':'+3.3V','copper_gap_mm':Point(69.85,39.2).buffer(.25,resolution=512).distance(near_land),'hole_to_land_gap_mm':Point(69.85,39.2).buffer(.15,resolution=512).distance(near_land),'conservative_copper_bbox_gap_mm':.131,'conservative_hole_bbox_gap_mm':.231,'disposition':'Same-net deliberate B.Cu connection; no different-net clearance requirement or pad clearance override. Via hole is outside the paste land. Bare-board solder-wicking needs pilot inspection.'}
assert report['after']['central_all_top_copper_area_mm2']<1e-9
(HERE/'u7-geometry-screen.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
