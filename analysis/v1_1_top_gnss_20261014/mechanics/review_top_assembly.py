#!/usr/bin/env python3
"""Hash-bound static assembly comparison; no CAD changes or RF-performance claims."""
from pathlib import Path
import argparse,sys,json,math,hashlib
import numpy as np
from shapely.geometry import Polygon,Point,LineString,box
from shapely.ops import unary_union
from geometry_distances import triseg
import matplotlib;matplotlib.use('Agg')
import matplotlib.pyplot as plt
ap=argparse.ArgumentParser();ap.add_argument('--native',type=Path,required=True);ap.add_argument('--solar-dir',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();H=args.output.resolve();H.mkdir(parents=True,exist_ok=True);sys.path.insert(0,str(args.solar_dir.resolve()));import generate as solar
j=json.loads(args.native.read_text());f=j['footprints'];u=lambda ps:unary_union([Polygon(p['shell'],p['holes'])for p in ps]);outline=u(j['outline']);r=.1605;m=j['models']['AE2'][0];assert f['AE2']['angle']==90 and m['offset']==[0,-.2,.25]and m['rotation']==[-90,0,-90];x,y=f['AE2']['at'];poses={'selected_top':(np.array([x+.2,y,.45]),np.array([x+.2,y-48,.45])),'original_top':(np.array([63.082,33.218,.45]),np.array([63.082,-14.782,.45])),'rejected_left':(np.array([55.3,47.65,.45]),np.array([7.3,47.65,.45]))};origins={'selected_top':[x,y],'original_top':[62.882,33.218],'rejected_left':[55.3,47.85]};parts=[]
for sign,ref,inner in[(-1,'J2',54.8),(1,'J1',75.2)]:
 xx,yy=f[ref]['at'];mesh,_=solar.build(sign,inner-xx)
 for name,verts,faces,material in mesh.parts:
  pts=np.array(verts)+[xx,yy,0];tri=[pts[[face[0],face[i],face[i+1]]]for face in faces for i in range(1,len(face)-1)];parts.append(dict(ref=ref,name=name,material=material,bounds_mm=np.r_[pts.min(0),pts.max(0)].tolist(),conservative_surface_gap_mm={k:min(triseg(a,b,*t)for t in tri)-r for k,(a,b)in poses.items()}))
holes={h:f[h]['at']for h in['H1','H2']};cx=sum(v[0]for v in holes.values())/2;hy=holes['H1'][1];summary={};bridles={}
for key,(a,b)in poses.items():
 c=Point(origins[key]);wire=LineString([a[:2],b[:2]]);d=dict(land_center_mm=origins[key],wire_centerline_start_mm=a.tolist(),wire_centerline_end_mm=b.tolist(),conservative_solar_gap_mm=min(p['conservative_surface_gap_mm'][key]for p in parts),conservative_terminal_metal_gap_mm=min(p['conservative_surface_gap_mm'][key]for p in parts if p['material']=='bus'),conservative_cell_finger_gap_mm=min(p['conservative_surface_gap_mm'][key]for p in parts if p['material']=='cell'),conservative_positive_copper_lead_gap_mm=min(p['conservative_surface_gap_mm'][key]for p in parts if p['material']=='wire'),hole_edge_ligament_mm=c.distance(outline.boundary)-.5,copper_land_to_outline_mm=c.distance(outline.boundary)-.75,projected_wire_to_H1_annulus_mm=wire.distance(Point(holes['H1']))-1.6-r,AE2_land_to_H1_annulus_mm=c.distance(Point(holes['H1']))-1.6-.75)
 if key!='rejected_left':
  t=(a[0]-holes['H1'][0])/(cx-holes['H1'][0]);d['symmetric_bridle_crossing_fraction']=t;d['symmetric_bridle_max_height_for_XY_crossing_mm']=(hy-b[1])/t
 summary[key]=d;bridles[key]=[]
 for height in[20,30,40,50,60,80,100,120,150]:
  apex=[cx,hy-height];legs=[LineString([holes[h],apex])for h in['H1','H2']];ints=[]
  for leg in legs:
   q=wire.intersection(leg)
   if not q.is_empty and q.geom_type=='Point':ints.append(list(q.coords)[0])
  bridles[key].append(dict(apex_height_mm=height,projected_centerline_gap_mm=min(wire.distance(v)for v in legs),intersections_xy_mm=ints))
# Preserve previously reviewed C5 max-case envelope and nominal L1 side.
c5=f['C5']['at'];case=box(c5[0]-7.25,c5[1]-15.25,c5[0]+7.25,c5[1]+15.25);case_near=[]
for p in j['pads']:
 if p['layer']!='B.Cu' or p['ref']=='C5':continue
 gap=case.distance(u(p['polygons']))
 if gap<1:case_near.append(dict(ref=p['ref'],pin=p['pin'],gap_mm=gap,overlap_mm2=case.intersection(u(p['polygons'])).area))
report=dict(pcb_sha256=j['sha256'],native_source=str(args.native.resolve()),solar_source=str((args.solar_dir/'generate.py').resolve()),solar_source_sha256=hashlib.sha256((args.solar_dir/'generate.py').read_bytes()).hexdigest(),review_type='Nominal static mechanics only; routing and RF performance reviewed separately',summary=summary,bridle_scenarios=bridles,solar_mesh_parts=parts,C5=dict(pose=f['C5'],maximum_case_bounds_mm=list(case.bounds),maximum_case_to_outline_mm=case.distance(outline.boundary),maximum_case_to_near_rear_lands=case_near),L1_pose=f['L1'],U8_pose=f['U8'],limitations=['Solar meshes are photo-derived nominal assembly geometry, not measured production tolerances.','Gap is exact segment-to-triangle distance minus nominal wire radius, a conservative capsule-envelope screen, not a qualified physical minimum.','Wire .321mm diameter and .25mm front-surface centerline elevation are unmeasured; model bottom is .0895mm above board.','Projected bridle intersection is conditional on symmetric taut triangle; actual string diameter, depth, apex, knots and motion are unknown.','At an XY crossing, depth separation must exceed .1605mm plus half string diameter plus dynamic allowance.','Neither greater solar separation nor upward orientation proves best sky coverage, antenna impedance/pattern, or GNSS sensitivity.','Final top pose restores the original flown feed location and upward48mm radiator; no remote side-feed/upwire workaround is used.'])
(H/'assembly-review.json').write_text(json.dumps(report,indent=2)+'\n');fig,ax=plt.subplots(figsize=(9,10));ox,oy=outline.exterior.xy;ax.fill(ox,oy,color='#b5d9ba',alpha=.5,label='PCB outline')
for key,(a,b)in poses.items():ax.plot([a[0],b[0]],[a[1],b[1]],lw=2.8,label=key.replace('_',' '))
for height,col in[(30,'#a23b45'),(80,'#7e5fa4'),(120,'#999999')]:
 ax.plot([holes['H1'][0],cx,holes['H2'][0]],[hy,hy-height,hy],ls='--',c=col,lw=1,label=f'Bridle projection H={height}mm')
for h,(xx,yy)in holes.items():ax.add_patch(plt.Circle((xx,yy),1.6,fill=False,color='black'));ax.text(xx+.4,yy+2,h,fontsize=8)
for ref in['J1','J2']:
 p=next(p for p in parts if p['ref']==ref and p['name']=='polymer laminate');x0,y0,z0,x1,y1,z1=p['bounds_mm'];ax.fill([x0,x1,x1,x0],[y0,y0,y1,y1],color='#d9b34a',alpha=.25)
ax.set_xlim(0,95);ax.set_ylim(92,-93);ax.set_aspect('equal');ax.grid(alpha=.2);ax.set_xlabel('KiCad X (mm)');ax.set_ylabel('KiCad Y (mm)');ax.legend(loc='lower left',fontsize=8);ax.set_title('Chosen top feed and upward48mm wire\nStatic projected mechanics; string depth and movement remain unqualified');fig.tight_layout();fig.savefig(H/'assembly-projection.png',dpi=170);print(json.dumps(summary,indent=2))
