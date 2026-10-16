#!/usr/bin/env python3
"""Quantify and render screened electrical wedge openings without changing CAD."""
from pathlib import Path
import argparse,json,math
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
from shapely.geometry import Polygon,Point,LineString,box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
from shapely.plotting import plot_polygon
p=argparse.ArgumentParser();p.add_argument('--geometry',type=Path,required=True);p.add_argument('--classified',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--figure',type=Path,required=True);a=p.parse_args();D=json.loads(a.geometry.read_text());C=json.loads(a.classified.read_text())
def polys(g):return[g]if g.geom_type=='Polygon'else[x for x in g.geoms if x.geom_type=='Polygon']
def lines(g):return[g]if g.geom_type=='LineString'else[x for x in g.geoms if x.geom_type=='LineString']if hasattr(g,'geoms')else[]
def union(rows):return unary_union([Polygon(x['shell'],x['holes'])for x in rows])
outline=union(D['outline']);CU={l:union(rows).intersection(outline)for l,rows in D['copper'].items()};E={l:outline.difference(g)for l,g in CU.items()};features=[r for r in C['features']if r['kind']=='acute_gap_candidates'and any(i['net']for i in r['near_items'])];R=[]
fig,axes=plt.subplots(4,4,figsize=(16,16));axes=list(axes.flat)
for idx,f in enumerate(features):
 layer=f['layer'];b=f['feature']['at_mm'];found=[]
 for poly in polys(CU[layer]):
  q=orient(poly.simplify(.002,preserve_topology=True),1)
  for ring in [q.exterior,*q.interiors]:
   pts=list(ring.coords)[:-1]
   for j,pnt in enumerate(pts):
    if math.dist(pnt,b)<1e-6:found.append((pts[(j-1)%len(pts)],pnt,pts[(j+1)%len(pts)]))
 assert len(found)==1,(b,found)
 aa,b,cc=found[0];u=[(aa[k]-b[k])/math.dist(aa,b)for k in[0,1]];v=[(cc[k]-b[k])/math.dist(cc,b)for k in[0,1]];vv=[u[k]+v[k]for k in[0,1]];length=math.hypot(*vv);direction=[x/length for x in vv];perp=[-direction[1],direction[0]]
 samples=[]
 for dep in [.025,.05,.075,.10,.125,.15,.20,.25,.30,.50]:
  center=[b[k]+dep*direction[k]for k in[0,1]];line=LineString([[center[k]+sgn*2*perp[k]for k in[0,1]]for sgn in[-1,1]])
  portions=lines(line.intersection(E[layer]));relevant=[l for l in portions if l.distance(Point(center))<1e-7];width=sum(l.length for l in relevant)
  samples.append({'depth_mm':dep,'open_width_mm':width,'center_is_empty':E[layer].covers(Point(center))})
 start=Point([b[k]+.01*direction[k]for k in[0,1]]);components=[g for g in polys(E[layer])if g.covers(start)];assert len(components)==1,(b,'No gap component')
 component=components[0];theta=f['feature']['gap_angle_deg'];theory=.10/(2*math.tan(math.radians(theta/2)))
 entry={'id':idx+1,'layer':layer,'at_mm':list(b),'nets':sorted({i['net']for i in f['near_items']if i['net']}),'gap_angle_deg':theta,'adjacent_edge_support_mm':f['feature']['edge_support_mm'],'ideal_straight_wedge_depth_below_0p10mm_width_mm':theory,'measured_bisector_width_samples':samples,'empty_component_area_mm2':component.area,'empty_component_bounds_mm':list(component.bounds),'empty_component_reaches_board_edge':component.distance(outline.boundary)<1e-6,'standalone_small_enclosed_pocket':component.area<.02,'classification':'Acute reentrant copper boundary. The gap joins the reported larger clearance region; small-angle geometry alone does not establish an etch defect or adequate process margin. Supplier CAM review remains required.'};R.append(entry)
 ax=axes[idx];window=box(b[0]-.65,b[1]-.65,b[0]+.65,b[1]+.65)
 for pp in polys(CU[layer].intersection(window)):
  plot_polygon(pp,ax=ax,add_points=False,facecolor='#b9763c',edgecolor='#653b17',linewidth=.45)
 ax.plot([b[0]],[b[1]],'ro',ms=3);ax.plot([b[0],b[0]+.3*direction[0]],[b[1],b[1]+.3*direction[1]],color='#2360c0',lw=1)
 ax.set_xlim(b[0]-.65,b[0]+.65);ax.set_ylim(b[1]+.65,b[1]-.65);ax.set_aspect('equal');ax.grid(alpha=.25);ax.tick_params(labelsize=7)
 ax.set_title(f"{idx+1}. {layer} {','.join(entry['nets'])}\n({b[0]:.3f}, {b[1]:.3f})  angle {theta:.1f}°",fontsize=9)
for ax in axes[len(features):]:ax.axis('off')
fig.suptitle('Electrical acute-gap candidates • 1.3 mm square views\nCopper brown; etched space white; apex red; gap bisector blue',fontsize=14);fig.tight_layout(rect=(0,0,1,.95));fig.savefig(a.figure,dpi=150);plt.close(fig)
r={'pcb_sha256':D['sha256'],'features':R,'method':'Actual filled full-copper unions, requested 2 µm polygon approximation. Boundary vertex supports from 2 µm simplified polygons; width samples intersect unsimplified copper complement along the local wedge bisector. 0.10 mm is a screening reference, not a universal etch-process qualification. Numeric distances are nominal geometry, not production tolerance guarantees.'};a.output.write_text(json.dumps(r,indent=2)+'\n')
for f in R:print(f['id'],f['layer'],f['nets'],'angle',round(f['gap_angle_deg'],2),'support',f['adjacent_edge_support_mm'],'gaparea',round(f['empty_component_area_mm2'],5),'boardedge',f['empty_component_reaches_board_edge'],'widths',[(x['depth_mm'],round(x['open_width_mm'],3))for x in f['measured_bisector_width_samples']if x['depth_mm']in[.10,.125,.15,.20]])
