#!/usr/bin/env python3
"""Read-only projected-copper screening; NOT an RF field solver or candidate PCB."""
from pathlib import Path
import json, math
import numpy as np
from shapely.geometry import Polygon, LineString, Point
from shapely.ops import unary_union
HERE = Path(__file__).resolve().parent
d = json.loads((HERE/'native-rf-geometry.json').read_text())
def geom(i):
    return unary_union([Polygon(p['shell'], p['holes']) for p in i['polygons']])
def centerline(i):
    a, c = np.array(i['start']), np.array(i['end'])
    if 'mid' not in i:
        return LineString([a,c]), float(np.linalg.norm(c-a))
    m = np.array(i['mid'])
    matrix=2*np.array([m-a,c-a]); rhs=np.array([m@m-a@a,c@c-a@a])
    o=np.linalg.solve(matrix,rhs); r=float(np.linalg.norm(a-o))
    angles=[math.atan2(*(p-o)[::-1]) for p in [a,m,c]]
    da=(angles[2]-angles[0])%(2*math.pi)
    if (angles[1]-angles[0])%(2*math.pi)>da: da-=2*math.pi
    # Arc chord error < 1 um for these radii.
    n=max(4,math.ceil(abs(da)/.01))
    points=[o+r*np.array([math.cos(t),math.sin(t)]) for t in np.linspace(angles[0],angles[0]+da,n+1)]
    return LineString(points), abs(r*da)
main_ids={
 '10e62ef9-ab31-4e56-96c7-83eee259c020','15d0258b-77c0-4984-944c-6ad003ad2de0',
 'f5f4dd5c-b62e-4228-99e1-d2e95bc0b778','1c9d5e81-4466-4304-8b8e-6d253c736885'}
old_items=[i for i in d['items'] if i['uuid'] in main_ids]
old=unary_union([centerline(i)[0] for i in old_items]); oldlength=sum(centerline(i)[1] for i in old_items)
oldcopper=unary_union([geom(i) for i in old_items])
west_points=[(60.787001,45.114001),(59.5,45.114001),(58.1,43.714001),(58.1,41.2),
             (56.6,39.7),(56.6,35.4),(57.3,34.7),(59.3,34.7),(62.882,33.218)]
west=LineString(west_points); westcopper=west.buffer(.375)
rear_ground=unary_union([geom(i) for i in d['items'] if i['layer']=='B.Cu' and i['net']=='GND'])
switches={net:unary_union([geom(i) for i in d['items'] if i['layer']=='B.Cu' and i['net']==net])
          for net in ['Net-(U1-LBOOST)','Net-(U1-LBUCK)']}
result={'source_sha256':d['pcb_sha256'],'original_main_analytic_length_mm':oldlength,
        'west_screen_length_mm':west.length,'length_increase_percent':(west.length/oldlength-1)*100,
        'west_screen_points_mm':west_points,'main_route_uuids':sorted(main_ids),
        'interpretation':'Rejected exploratory polyline only. No native candidate, refill, DRC, impedance simulation, or CAD edit. Existing saved rear ground screen is not a prediction of refill after rerouting.',
        'routes':{}}
for name,line,copper in [('original',old,oldcopper),('west_rejected',west,westcopper)]:
    crossings=[]
    for i in d['items']:
        if i['layer']!='B.Cu' or i['net']=='GND' or i['kind']=='zone':continue
        g=geom(i); overlap=copper.intersection(g).area
        if overlap>1e-6:
            crossings.append({'net':i['net'],'kind':i['kind'],'ref':i.get('ref'),'pin':i.get('pin'),
                              'uuid':i['uuid'],'projected_overlap_mm2':overlap,
                              'centerline_overlap_length_mm':line.intersection(g).length})
    result['routes'][name]={
      'centerline_length_mm_approximated':line.length,
      'centerline_above_saved_rear_gnd_mm':line.intersection(rear_ground).length,
      'centerline_without_saved_rear_gnd_mm':line.difference(rear_ground).length,
      'copper_projection_area_mm2':copper.area,
      'copper_projection_above_saved_rear_gnd_mm2':copper.intersection(rear_ground).area,
      'switch_projection_edge_distance_mm':{net:copper.distance(g) for net,g in switches.items()},
      'opposite_layer_non_ground_overlaps':crossings}
result['existing_gnd_vias_interfering_with_west_screen']=[i for i in d['items']
 if i['kind']=='PCB_VIA' and i['layer']=='F.Cu' and i['net']=='GND'
 and geom(i).distance(westcopper)<.15]
(HERE/'route-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ['routes','existing_gnd_vias_interfering_with_west_screen']},indent=2))
for name,v in result['routes'].items():
 print(name, 'centerline no GND',v['centerline_without_saved_rear_gnd_mm'], 'switch gap',v['switch_projection_edge_distance_mm'])
 print('Opposite layer pad overlaps:',[(x['ref'],x['pin'],x['net'],round(x['projected_overlap_mm2'],4))for x in v['opposite_layer_non_ground_overlaps']if x['kind']=='pad'])
