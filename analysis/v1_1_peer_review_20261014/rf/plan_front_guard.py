from pathlib import Path
import json,math,argparse
import numpy as np
from shapely import set_precision
from shapely.geometry import LineString,Point,box,Polygon
from shapely.ops import unary_union,linemerge,substring
H=Path(__file__).resolve().parent
ap=argparse.ArgumentParser(description='Derive a finite front-ground guard from saved native RF geometry; no CAD edits.');ap.add_argument('geometry',type=Path);ap.add_argument('--output',type=Path,default=H/'front-guard-plan.json');args=ap.parse_args();d=json.loads(args.geometry.read_text())
def line(i):
 s,e=np.array(i['start']),np.array(i['end'])
 if'mid'not in i:return LineString([s,e])
 m=np.array(i['mid']);o=np.linalg.solve(2*np.array([m-s,e-s]),np.array([m@m-s@s,e@e-s@s]));r=np.linalg.norm(s-o);a=[math.atan2(*(p-o)[::-1])for p in[s,m,e]];da=(a[2]-a[0])%(2*math.pi)
 if(a[1]-a[0])%(2*math.pi)>da:da-=2*math.pi
 return LineString([o+r*np.array([math.cos(t),math.sin(t)])for t in np.linspace(a[0],a[0]+da,100)])
r=linemerge(unary_union([set_precision(line(i),.00001)for i in d['items']if i['layer']=='F.Cu'and i['net']=='Net-(AE2-A)'and i['kind']in['PCB_TRACK','PCB_ARC']]))
if Point(r.coords[0]).distance(Point(55.3,47.85))>1:r=LineString(list(r.coords)[::-1])
o=r.offset_curve(-.525,quad_segs=32);o=substring(o,.92,o.project(Point(57.4,45.225)))
g=unary_union([o.buffer(.15,quad_segs=32),LineString([(55.45,46.65),o.coords[0]]).buffer(.15,quad_segs=32),LineString([o.coords[-1],(57.4,44.95),(58,44.35)]).buffer(.15,quad_segs=32)])
plan={'source_sha256':d['pcb_sha256'],'moves':{'Copper label: STRATOLINK.ORG':[0,-.55],'Copper label: PICO MAINBOARD V1.1':[0,-.22]},'guard':list(g.exterior.coords)[:-1],'via':[55.45,46.65],'nominal_guard_width_mm':.3,'nominal_trace_gap_mm':.15}
args.output.write_text(json.dumps(plan,indent=2)+'\n')
print(g.bounds,g.area)
