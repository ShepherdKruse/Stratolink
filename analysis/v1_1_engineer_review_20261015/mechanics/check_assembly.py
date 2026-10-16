from pathlib import Path
import sys,json,hashlib
import numpy as np
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import unary_union
import argparse
ap=argparse.ArgumentParser();ap.add_argument('--repo',type=Path,required=True);ap.add_argument('--native',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();ROOT=args.repo.resolve();OUT=args.output.resolve();OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(ROOT/'analysis/v1_1_top_gnss_20261014/mechanics'));from geometry_distances import triseg
sys.path.insert(0,str(ROOT/'hardware/pcb/3d/solar'));import generate as solar
j=json.loads(args.native.read_text());f=j['footprints'];u=lambda ps:unary_union([Polygon(p['shell'],p['holes'])for p in ps]);outline=u(j['outline']);r=.1605;m=j['models']['AE2'][0]
assert f['AE2']['angle']==90 and m['offset'][:2]==[0,-.2]and m['rotation']==[-90,0,-90]
x,y=f['AE2']['at'];a=np.array([x+.2-.1605,y,.2+m['offset'][2]]);b=a+[0,-48,0];parts=[]
for sign,ref,inner in[(-1,'J2',54.8),(1,'J1',75.2)]:
 xx,yy=f[ref]['at'];mesh,_=solar.build(sign,inner-xx)
 for name,verts,faces,material in mesh.parts:
  pts=np.array(verts)+[xx,yy,0];tri=[pts[[face[0],face[i],face[i+1]]]for face in faces for i in range(1,len(face)-1)]
  parts.append(dict(ref=ref,name=name,material=material,bounds_mm=np.r_[pts.min(0),pts.max(0)].tolist(),surface_gap_mm=min(triseg(a,b,*t)for t in tri)-r))
holes={h:f[h]['at']for h in['H1','H2']};cx=sum(v[0]for v in holes.values())/2;hy=holes['H1'][1];wire=LineString([a[:2],b[:2]]);c=Point([x,y]);t=(a[0]-holes['H1'][0])/(cx-holes['H1'][0]);bridles=[]
for height in[20,30,40,50,60,80,100,120,150]:
 apex=[cx,hy-height];legs=[LineString([holes[h],apex])for h in['H1','H2']]
 bridles.append(dict(apex_height_mm=height,projected_centerline_gap_mm=min(wire.distance(v)for v in legs),crosses=any(wire.intersects(v)for v in legs)))
c5=f['C5']['at'];assert f['C5']['angle']==180;case=box(c5[0]-7.25,c5[1]-15.25,c5[0]+7.25,c5[1]+15.25);case_near=[]
for p in j['pads']:
 if p['layer']!='B.Cu'or p['ref']=='C5':continue
 geom=u(p['polygons']);gap=case.distance(geom)
 if gap<1:case_near.append(dict(ref=p['ref'],pin=p['pin'],net=p['net'],gap_mm=gap,overlap_mm2=case.intersection(geom).area,at=p['at']))
report=dict(pcb_sha256=j['sha256'],outline_area_mm2=outline.area,outline_bounds_mm=list(outline.bounds),GNSS=dict(pose=f['AE2'],wire_centerline=[a.tolist(),b.tolist()],nominal_wire_to_front_surface_mm=a[2]-.2-r,solar_gap_mm=min(p['surface_gap_mm']for p in parts),terminal_gap_mm=min(p['surface_gap_mm']for p in parts if p['material']=='bus'),hole_edge_ligament_mm=c.distance(outline.boundary)-.5,land_to_outline_mm=c.distance(outline.boundary)-.75,wire_to_H1_annulus_mm=wire.distance(Point(holes['H1']))-1.6-r,bridle_projection_crossing_max_apex_height_mm=(hy-b[1])/t,bridle_scenarios=bridles),solar_mesh_parts=parts,C5=dict(pose=f['C5'],maximum_case_bounds_mm=list(case.bounds),maximum_case_to_outline_mm=case.distance(outline.boundary),maximum_case_near_rear_lands=case_near),limitations=['Wire axis includes the STEP solid localX0.1605mm center, confirmed by native GLB export; earlier screen omitted that offset. All envelopes use nominal/display dimensions and CAP-XX datasheet maximum case rectangle, not assembled process tolerance.','Projected overlap of C5 body and solder lands is an assembly clearance concern, not an electrical short unless actual case material/standoff allows contact.','Solar model thickness, bend, fillets and wire diameter remain provisional.','String depth, knot height and motion are unknown. XY crossing alone is not a physical collision.'])
(OUT/'assembly-review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k not in ['solar_mesh_parts']},indent=2))
