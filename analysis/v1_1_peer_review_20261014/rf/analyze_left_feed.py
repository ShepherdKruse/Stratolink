#!/usr/bin/env python3
"""Saved-copper projection screen, not an electromagnetic simulation."""
from pathlib import Path
import json,math,argparse
import numpy as np
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union
ap=argparse.ArgumentParser();ap.add_argument('geometry',type=Path);ap.add_argument('output',type=Path);a=ap.parse_args()
d=json.loads(a.geometry.read_text())
def geometry(i):return unary_union([Polygon(p['shell'],p['holes'])for p in i['polygons']])
def line(i):
 s,e=np.array(i['start']),np.array(i['end'])
 if 'mid'not in i:return LineString([s,e]),float(np.linalg.norm(e-s))
 m=np.array(i['mid']);o=np.linalg.solve(2*np.array([m-s,e-s]),np.array([m@m-s@s,e@e-s@s]));r=float(np.linalg.norm(s-o));angles=[math.atan2(*(p-o)[::-1])for p in[s,m,e]];delta=(angles[2]-angles[0])%(2*math.pi)
 if(angles[1]-angles[0])%(2*math.pi)>delta:delta-=2*math.pi
 return LineString([o+r*np.array([math.cos(t),math.sin(t)])for t in np.linspace(angles[0],angles[0]+delta,200)]),abs(r*delta)
tracks=[i for i in d['items']if i['layer']=='F.Cu'and i['net']=='Net-(AE2-A)'and i['kind']in['PCB_TRACK','PCB_ARC']]
center=unary_union([line(i)[0]for i in tracks]);copper=unary_union([geometry(i)for i in tracks]+[geometry(i)for i in d['items']if i['kind']=='graphic'and i['layer']=='F.Cu'and i['net']=='Net-(AE2-A)']);length=sum(line(i)[1]for i in tracks)
ground=unary_union([geometry(i)for i in d['items']if i['layer']=='B.Cu'and i['net']=='GND'])
# The plated antenna hole and its clearance are deliberately not ground-backed.
terminal=Point(d['footprints']['AE2']['at']).buffer(.9,quad_segs=128)
usable_center=center.difference(terminal);usable_copper=copper.difference(terminal)
launch=next(geometry(i)for i in d['items']if i['kind']=='pad'and i['ref']=='U3'and i['pin']=='11'and i['layer']=='F.Cu')
overlap=[]
for i in d['items']:
 if i['layer']!='B.Cu'or i['net']=='GND'or i['kind']=='zone':continue
 g=geometry(i);area=usable_copper.intersection(g).area
 if area>1e-7:overlap.append(dict(uuid=i['uuid'],ref=i.get('ref'),pin=i.get('pin'),net=i['net'],kind=i['kind'],area_mm2=area))
switches={n:unary_union([geometry(i)for i in d['items']if i['layer']=='B.Cu'and i['net']==n])for n in['Net-(U1-LBOOST)','Net-(U1-LBUCK)']}
r=dict(pcb_sha256=d['pcb_sha256'],source=d['source'],geometry_source=str(a.geometry),analytic_main_length_mm=length,original_main_length_mm=13.439242465768096,length_change_percent=(length/13.439242465768096-1)*100,route_uuids=[i['uuid']for i in tracks],terminal_exclusion_radius_mm=.9,screened_centerline_length_mm=usable_center.length,screened_centerline_without_rear_ground_mm=usable_center.difference(ground).length,screened_trace_area_mm2=usable_copper.area,screened_trace_without_rear_ground_area_mm2=usable_copper.difference(ground).area,projection_tolerance_mm=.005,screened_trace_without_rear_ground_beyond_tolerance_mm2=usable_copper.difference(ground.buffer(.005)).area,screened_centerline_without_rear_ground_beyond_tolerance_mm=usable_center.difference(ground.buffer(.005)).length,receiver_launch_area_mm2=launch.area,receiver_launch_without_rear_ground_area_mm2=launch.difference(ground).area,opposite_layer_non_ground_overlaps=overlap,switch_projection_edge_distance_mm={n:copper.distance(g)for n,g in switches.items()},graphics_included=d['graphics_included'],excluded_copper_text=d['excluded_copper_text'],limitations=['Direct projection tests actual saved fills. It does not prove return-current distribution, impedance, antenna match, or EMI performance.','The 0.9 mm antenna-terminal exclusion includes the 0.75 mm-radius plated pad and its 0.15 mm ground clearance.','Board copper text is listed separately; native DRC includes it, and the four solar polarity marks are outside the RF region.','Native copper contours request <=2 um polygon error. Analytical route length uses native arc coordinates.'])
a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k not in['route_uuids','excluded_copper_text']},indent=2))
