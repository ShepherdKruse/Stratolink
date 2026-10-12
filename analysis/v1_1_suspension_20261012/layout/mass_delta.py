#!/usr/bin/env python3
"""Bare-board nominal mass delta using full native copper/mask geometry."""
from pathlib import Path
import json,math
from shapely.geometry import Polygon,Point,LineString
from shapely.ops import unary_union
from shapely import affinity
HERE=Path(__file__).resolve().parent
data=json.loads((HERE/'mass-native.json').read_text())
def union(rows):return unary_union([Polygon(c['shell'],c['holes']) for c in rows])
def circle(xy,r):return Point(xy).buffer(r,quad_segs=1024)
def drill(d):
 x,y=d['size']
 if abs(x-y)<1e-8:return circle(d['xy'],x/2)
 r,length=min(x,y)/2,abs(x-y)
 g=LineString([(-length/2,0),(length/2,0)]).buffer(r,quad_segs=512)
 g=affinity.rotate(g,(90 if y>x else 0)-d['rotation'])
 return affinity.translate(g,*d['xy'])
def measure(d,plating=.020):
 # Use the native identical outside profile, correcting only old coarse circular
 # inner contours to 4096-segment nominal circles. This avoids a ~0.014mm2 delta bias.
 edge=union(d['outline'])
 if d['edge_circles']:
  assert len(d['outline'])==1 and len(d['outline'][0]['holes'])==len(d['edge_circles'])
  edge=Polygon(d['outline'][0]['shell']).difference(unary_union([circle(c['xy'],c['radius']) for c in d['edge_circles']]))
 finished=[drill(h) for h in d['drills']]
 holes=unary_union(finished)
 laminate_finished=edge.difference(holes)
 copper={name:union(d['layers'][name]).intersection(laminate_finished) for name in ['F.Cu','B.Cu']}
 mask={name:laminate_finished.difference(union(d['layers'][name])) for name in ['F.Mask','B.Mask']}
 actual_drill=unary_union([g.buffer(plating,resolution=256) if h['plated'] else g for g,h in zip(finished,d['drills'])])
 core=edge.difference(actual_drill)
 barrel_area=sum(g.buffer(plating,resolution=256).area-g.area for g,h in zip(finished,d['drills']) if h['plated'])
 return dict(edge=edge,finished=laminate_finished,core=core,copper=copper,mask=mask,barrels=barrel_area)
old,new=[measure(data[name]) for name in ['baseline','candidate']]
def areas(g):return dict(outline_area_mm2=g['edge'].area,finished_opening_subtracted_area_mm2=g['finished'].area,core_area_after_assumed_oversize_drill_mm2=g['core'].area,copper_mm2={k:v.area for k,v in g['copper'].items()},mask_mm2={k:v.area for k,v in g['mask'].items()},barrel_cross_section_mm2=g['barrels'])
def mass(g,density=1.9):
 return dict(FR4_mg=g['core'].area*.31*density,planar_copper_mg=sum(p.area for p in g['copper'].values())*.035*8.96,mask_mg=sum(p.area for p in g['mask'].values())*.010*1.4,barrel_copper_core_height_mg=g['barrels']*.31*8.96)
bm,cm=mass(old),mass(new);delta={k:cm[k]-bm[k] for k in bm}
pad_discs=unary_union([circle(h['xy'],1.6) for h in data['candidate']['drills'] if h['ref'] in ['H1','H2']])
outside={name:new['copper'][name].difference(old['copper'][name]).difference(pad_discs).area for name in new['copper']}
sens=[]
for density in [1.8,1.9,2.0]:
 for plating in [.015,.020,.025]:
  a,b=[measure(data[name],plating) for name in ['baseline','candidate']]
  sens.append(dict(FR4_density_g_cm3=density,barrel_radial_thickness_mm=plating,delta_mg=sum(mass(b,density).values())-sum(mass(a,density).values())))
report=dict(baseline_sha256=data['baseline']['source_sha256'],candidate_sha256=data['candidate']['source_sha256'],baseline_commit='a9d6ed5',scope='All nominal bare-board substrate, complete native planar copper union, actual native mask-opening geometry and assumed plated barrels. No components, solder, surface finish or string.',assumptions=dict(board_thickness_mm=.4,core_thickness_mm=.31,copper_each_face_mm=.035,mask_each_face_mm=.010,FR4_density_g_cm3=1.9,copper_density_g_cm3=8.96,mask_density_g_cm3=1.4,barrel_radial_thickness_mm=.020,barrel_core_height_mm=.31,plating_accounting='Finished holes expanded by assumed plating thickness for FR4 removal; barrels restore copper in that oversize annulus across core height. The face-layer annulus is already counted in planar copper, avoiding double count.',provenance='Thicknesses are the CAD stackup; densities and barrel thickness are engineering assumptions, not delivered-board measurements.'),baseline_areas=areas(old),candidate_areas=areas(new),baseline_mass_parts_mg=bm,candidate_mass_parts_mg=cm,baseline_mass_mg=sum(bm.values()),candidate_mass_mg=sum(cm.values()),delta_parts_mg=delta,delta_total_mg=sum(delta.values()),added_copper_outside_3p2mm_pad_discs_mm2=outside,added_copper_outside_3p2mm_pad_discs_mg=sum(outside.values())*.035*8.96,sensitivity=sens,limitations=['Copper outlines are KiCad polygon approximations. Original circular routed holes were reconstituted at4096segments for accurate area difference; outside profile is identical in both.', 'Mask mass uses native mask-opening polygons clipped to nominal substrate, not a fixed mask coverage fraction.', 'No ENIG/HASL finish, ink, solder or actual production-thickness tolerance has been assigned. This is a nominal design mass estimate, not measured mass.'])
(HERE/'mass-delta.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ['baseline_mass_mg','candidate_mass_mg','delta_parts_mg','delta_total_mg','added_copper_outside_3p2mm_pad_discs_mm2','added_copper_outside_3p2mm_pad_discs_mg','sensitivity']},indent=2))
