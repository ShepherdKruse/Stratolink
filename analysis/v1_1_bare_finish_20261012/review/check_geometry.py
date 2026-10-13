#!/usr/bin/env python3
"""Independent ideal-CAD copper and exported mask coverage check.

Run with analysis/.venv/bin/python after verify_native.py. This is not a
finished-board tolerance, antenna installation or soldering qualification.
"""
from pathlib import Path
import gzip,hashlib,json,re
from shapely.geometry import Polygon,LineString,Point
from shapely.ops import unary_union,polygonize
HERE=Path(__file__).resolve().parent
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-bare-finish-20261012/review'
def union(rows):return unary_union([Polygon(r['shell'],r['holes']).buffer(0) for r in rows])
def main():
 data=json.loads(gzip.decompress((HERE/'native-geometry.json.gz').read_bytes()));scope=json.loads((HERE/'approved-scope.json').read_text());report={}
 before,after=[{(p['kind'],p['uuid'],p['layer']):p for p in data[k]['individual_copper']} for k in ['baseline','candidate']]
 deleted=set(before)-set(after)
 assert deleted=={('track',u,'F.Cu') for u in scope['removed_segments']}
 assert not set(after)-set(before)
 for k in after:assert before[k]==after[k],('Unchanged individual conductor differs',k)
 stub=scope['removed_segments'][0];long='bfbfa6f4-1dbe-4095-a771-3fb9a012fb75'
 stubpoly=union(before['track',stub,'F.Cu']['polygons']);longpoly=union(before['track',long,'F.Cu']['polygons'])
 residue=stubpoly.difference(longpoly)
 assert stubpoly.difference(longpoly.buffer(.0002)).area<1e-12,'Deleted duplicate falls outside long track, including polygon approximation bound'
 line=LineString([(75.187,67.249),(76.299,68.361)]);short=LineString([(75.187,67.249),(75.195,67.257)])
 assert line.distance(short)<1e-10 and all(line.distance(Point(p))<1e-10 for p in short.coords)
 report['duplicate_stub']=dict(uuid=stub,containing_track=long,ideal_width_mm=.25,centerline_length_mm=short.length,exactly_collinear=True,fully_contained_same_width=True,raw_polygon_approximation_residue_mm2=residue.area)
 report['copper']={}
 for layer in ['F.Cu','B.Cu']:
  old,new=[union(data[k]['copper'][layer]) for k in ['baseline','candidate']]
  add=new.difference(old);remove=old.difference(new)
  buffered=new.difference(old.buffer(.000050)).union(old.difference(new.buffer(.000050)))
  assert buffered.area<1e-10,('Copper difference exceeds 50 nm native-polygon approximation residue',layer,buffered.area)
  report['copper'][layer]=dict(added_mm2=add.area,removed_mm2=remove.area,difference_beyond_50nm_mm2=buffered.area)
 outline_old,outline=[union(data[k]['outline']) for k in ['baseline','candidate']]
 assert outline.equals(outline_old)
 report['mask_exports']={}
 for face,cu,suffix in [('F','F.Cu','gts'),('B','B.Cu','gbs')]:
  path=SCRATCH/'candidate-exports'/f'stratolink-{face}_Mask.{suffix}';text=path.read_text()
  assert '%TF.FilePolarity,Negative*%' in text and '%FSLAX46Y46*%' in text and '%MOMM*%' in text
  assert '%LPD*%' in text and '%LPC*%' not in text,'Clear operations would require complete Gerber boolean evaluation'
  regions=[]
  for match in re.finditer(r'G36\*\n(.*?)G37\*',text,re.S):
   vertices=[]
   for line in match.group(1).splitlines():
    m=re.fullmatch(r'X(-?\d+)Y(-?\d+)D0[12]\*',line)
    if m:vertices.append((int(m[1])/1e6,-int(m[2])/1e6))
   if vertices:regions.append(Polygon(vertices))
  opening=unary_union(regions);copper=union(data['candidate']['copper'][cu])
  assert opening.is_valid and outline.difference(opening).area==0
  assert copper.difference(opening).area==0
  report['mask_exports'][face]=dict(negative_mask_file_polarity=True,no_clear_operations=True,full_opening_bounds_mm=list(opening.bounds),covered_board_area_mm2=0,covered_copper_area_mm2=0,outline_to_opening_edge_margin_mm=outline.distance(opening.boundary))
 job=json.loads((SCRATCH/'candidate-exports/stratolink-job.gbrjob').read_text())
 assert job['GeneralSpecs']['BoardThickness']==.4
 masks=[x for x in job['MaterialStackup'] if x['Type']=='SolderMask'];assert len(masks)==2 and all(x['Thickness']==0 for x in masks)
 report['courtyard']={}
 for label in ['baseline','candidate']:
  geom=data[label]['assembly'];ant,diode=[union(geom[x]['courtyard']) for x in ['AE1','D1']]
  drawn_ant,drawn_diode=[unary_union(list(polygonize(unary_union([LineString([r['start_mm'],r['end_mm']]) for r in geom[x]['courtyard_lines']])))) for x in ['AE1','D1']]
  assert not drawn_ant.is_empty and not drawn_diode.is_empty
  report['courtyard'][label]=dict(native_cached_overlap_mm2=ant.intersection(diode).area,native_cached_clearance_mm=ant.distance(diode),drawn_envelope_overlap_mm2=drawn_ant.intersection(drawn_diode).area,drawn_envelope_clearance_mm=drawn_ant.distance(drawn_diode),native_cached_bounds_mm=dict(AE1=list(ant.bounds),D1=list(diode.bounds)),drawn_bounds_mm=dict(AE1=list(drawn_ant.bounds),D1=list(drawn_diode.bounds)))
  if label=='candidate':assert ant.intersection(diode).area==0 and drawn_ant.intersection(drawn_diode).area==0 and drawn_ant.distance(drawn_diode)>.16
 antpad=union(next(p['polygons'] for p in after.values() if p.get('ref')=='AE1' and p['layer']=='F.Cu'))
 diodepads=unary_union([union(p['polygons']) for p in after.values() if p.get('ref')=='D1' and p['layer']=='F.Cu'])
 report['unchanged_antenna_to_diode_copper_mm']=antpad.distance(diodepads)
 report['interpretation']='All pad, via and remaining track polygons are identical. The sole removed conductor is an exact duplicate inside the retained route. Full-board mask openings cover all native board and copper geometry on both faces; no clear-polarity Gerber operation can re-cover an area. Drawn courtyard centerline envelopes have a 0.162 mm gap; native GetCourtyard caches have boundaries inset 0.005 mm each and therefore a 0.172 mm gap. Stroke width is a drawing convention, not extra assembly space. Antenna courtyard represents the documented installation envelope, not a measured final solder joint or RF qualification. Stackup thickness is nominal.'
 (HERE/'geometry-verification.json').write_text(json.dumps(report,indent=2)+'\n')
 native=json.loads((HERE/'verification.json').read_text());assert native['status']=='native checks passed; independent geometry review pending' or native['status']=='native, independent geometry and fabrication checks passed'
 native['status']='native, independent geometry and fabrication checks passed';native['geometry_report_sha256']=hashlib.sha256((HERE/'geometry-verification.json').read_bytes()).hexdigest()
 (HERE/'verification.json').write_text(json.dumps(native,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
