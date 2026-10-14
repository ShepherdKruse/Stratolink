from pathlib import Path
import argparse,json
from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union
from track_geometry import path
ap=argparse.ArgumentParser();ap.add_argument('--baseline',type=Path,required=True);ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();b=json.loads(args.baseline.read_text());a=json.loads(args.candidate.read_text());g=lambda ps:unary_union([Polygon(p['shell'],p['holes'])for p in ps]);region=box(62.7,35.6,69.3,40.5)
def copper(j,layer):
 shapes=[g(p['polygons'])for p in j['pads']if p['net']=='GND'and layer in p['layers']]+[g(p['polygons'])for p in j['zones']+j['graphics']if p['net']=='GND'and p['layer']==layer]
 for t in j['tracks']:
  if t['net']!='GND':continue
  if t['kind']=='PCB_VIA':shapes.append(Point(t['start']).buffer(t['width']/2,resolution=64))
  elif t['layer']==layer:shapes.append(path(t).buffer(t['width']/2,resolution=64))
 return unary_union([s if s.is_valid else s.buffer(0)for s in shapes]).intersection(region)
rows=[]
for layer in['F.Cu','B.Cu']:
 old=copper(b,layer);new=copper(a,layer);parts=[new] if new.geom_type=='Polygon' else list(new.geoms); same=any(p.buffer(.000002).covers(Point(63.873,39.917)) and p.buffer(.000002).covers(Point(65.540999,38.814998)) for p in parts);rows.append(dict(C2_GND_and_U1_pin1_connected_within_region=same,layer=layer,before_area_mm2=old.area,after_area_mm2=new.area,added_ground_mm2=new.difference(old).area,removed_ground_mm2=old.difference(new).area,removed_bounds_mm=list(old.difference(new).bounds)))
return_ids=['ce6c318c-cb5b-4e36-8507-e30e6495c991','50dc6e87-7f34-4e01-90ba-2af8618be1cb','800617c5-f9f4-4d9c-a616-ccb5a0a44862']
before_tracks={t['uuid']:t for t in b['tracks']};after_tracks={t['uuid']:t for t in a['tracks']};explicit=[after_tracks[k]for k in return_ids];assert all(before_tracks[k]==after_tracks[k]for k in return_ids)
assert all(t['net']=='GND'and t['layer']=='B.Cu'and t['width']==.25 for t in explicit)
return_proof=dict(unchanged=True,width_mm=.25,route_length_to_inside_C2_land_mm=sum(t['length']for t in explicit),tracks=explicit,note='The retained eastward0.25mm route joins U1.1 directly into the C2.GND land; loss of incidental west fill does not remove this local return.')
report=dict(baseline_sha256=b['sha256'],candidate_sha256=a['sha256'],region_bounds_mm=list(region.bounds),explicit_C2_U1_return=return_proof,layers=rows,notes=['Exact native pad/zone polygons and densely approximated track strokes in a bounded C2/U1 neighborhood; this checks geometry, not current-density or inductance.','Ground fills can differ slightly after global native refill. Native connected-island proof remains authoritative.'])
args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
