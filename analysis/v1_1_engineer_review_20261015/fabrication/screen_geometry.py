#!/usr/bin/env python3
"""Geometric candidate screen, not a proof of manufacturability or acid trapping.
Exact native polygon unions are simplified by2um for tessellation noise only;
angles require substantive adjacent edges. Results retain coordinates for review.
"""
from pathlib import Path
import json,math
import shapely
from shapely.geometry import Polygon,Point,LineString,box
from shapely.geometry.polygon import orient
from shapely.ops import unary_union
HERE=Path(__file__).resolve().parent

def loadpolys(rows):return unary_union([Polygon(x['shell'],x['holes']) for x in rows])
def polys(g):return [g] if g.geom_type=='Polygon' else [x for x in g.geoms if x.geom_type=='Polygon']
def bbox(g):return list(g.bounds)
def pangle(a,b,c):
 u=(b[0]-a[0],b[1]-a[1]);v=(c[0]-b[0],c[1]-b[1]);return math.degrees(math.atan2(u[0]*v[1]-u[1]*v[0],u[0]*v[0]+u[1]*v[1]))
def screen(name):
 d=json.loads((HERE/(name+'-geometry.json')).read_text());outline=loadpolys(d['outline']);result={'source_sha256':d['sha256'],'layers':{}}
 for layer,rows in d['copper'].items():
  copper=loadpolys(rows).intersection(outline);pieces=polys(copper);acute=[];tips=[]
  for p in pieces:
   q=orient(p.simplify(.002,preserve_topology=True),1)
   for r in [q.exterior,*q.interiors]:
    pts=list(r.coords)[:-1]
    for j,b in enumerate(pts):
     a,c=pts[(j-1)%len(pts)],pts[(j+1)%len(pts)]
     e1,e2=math.dist(a,b),math.dist(b,c)
     if min(e1,e2)<.075:continue
     turn=pangle(a,b,c)
     if turn<-120:acute.append({'at_mm':list(b),'gap_angle_deg':180+turn,'edge_support_mm':[e1,e2]})
     if turn>150:tips.append({'at_mm':list(b),'copper_tip_angle_deg':180-turn,'edge_support_mm':[e1,e2]})
  # Only enclosed empty-space components are considered; normal pad moats are
  # reported by size, not classified as defects.
  empty=outline.difference(copper);enclosed=[]
  for p in polys(empty):
   if p.distance(outline.boundary)<1e-6:continue
   inc=shapely.maximum_inscribed_circle(p,tolerance=.002);diameter=2*inc.length
   if p.area<.02 and diameter<.10:
    enclosed.append({'area_mm2':p.area,'maximum_inscribed_diameter_mm':diameter,'bounds_mm':bbox(p),'at_mm':list(p.representative_point().coords)[0]})
  tiny=[]
  for p in pieces:
   if p.area<.01:
    tiny.append({'area_mm2':p.area,'bounds_mm':bbox(p),'at_mm':list(p.representative_point().coords)[0]})
  result['layers'][layer]={'copper_component_count':len(pieces),'acute_gap_candidates':acute,'sharp_tip_candidates':tips,'small_enclosed_gap_candidates':enclosed,'tiny_copper_components':tiny}
 return result
if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--geometry',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert a.geometry.name.endswith('-geometry.json')
 HERE=a.geometry.parent;r=screen(a.geometry.name[:-len('-geometry.json')]);r['method']='Native filled copper unions at 2 um maximum-error setting. 2 um simplification; 0.075 mm supporting edges; gaps <60 degrees; tips <30 degrees; enclosed gaps <0.02 mm2 and <0.10 mm inscribed diameter; islands <0.01 mm2. Candidate screening only, not supplier process qualification.'
 a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({layer:{f:len(v)for f,v in n.items()if isinstance(v,list)}for layer,n in r['layers'].items()},indent=2))
