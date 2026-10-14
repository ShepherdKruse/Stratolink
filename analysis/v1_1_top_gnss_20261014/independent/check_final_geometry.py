#!/usr/bin/env python3
"""Independently bound residual etch seams, thermal reliefs and RF transition.
Read-only, with exact source-bound geometry inputs. Retains every raw candidate.
"""
from pathlib import Path
import argparse,hashlib,json,math
import shapely
from shapely.geometry import Polygon,Point,box
from shapely.ops import unary_union
p=argparse.ArgumentParser(description=__doc__)
for n in ['geometry','reference_geometry','zones','screen','reference','output']:p.add_argument('--'+n.replace('_','-'),type=Path,required=True)
a=p.parse_args();assert not a.output.exists()
D={n:json.loads(getattr(a,n).read_text())for n in ['geometry','reference_geometry','zones','screen','reference']}
sha=D['geometry']['sha256'];assert all(D[n].get('pcb_sha256',D[n].get('source_sha256'))==sha for n in D if n!='geometry')
def load(rows):return unary_union([shapely.make_valid(Polygon(x['shell'],x['holes']))for x in rows])
def parts(g):return[g]if g.geom_type=='Polygon'else[x for x in g.geoms if x.geom_type=='Polygon']
items=[dict(i,g=load(i['polygons']))for i in D['reference_geometry']['items']]
outline=load(D['geometry']['outline']);copper={l:load(rows).intersection(outline)for l,rows in D['geometry']['copper'].items()}
residual=[]
for layer,c in copper.items():
 groups={'small_enclosed_gap_candidates':[g for g in parts(outline.difference(c))if g.area<.02 and g.distance(outline.boundary)>1e-6], 'tiny_copper_components':[g for g in parts(c)if g.area<.01]}
 for kind,gs in groups.items():
  # Match the unmodified raw screen by exact bounds; do not skip any reported feature.
  for raw in D['screen']['layers'][layer][kind]:
   found=[g for g in gs if max(abs(x-y)for x,y in zip(g.bounds,raw['bounds_mm']))<1e-10];assert len(found)==1
   g=found[0];diam=2*shapely.maximum_inscribed_circle(g,tolerance=1e-9).length
   source=[]
   for i in items:
    if i['layer']!=layer:continue
    overlap=i['g'].intersection(g).area;gap=i['g'].distance(g)
    if overlap>g.area*.01 or gap<=.000005:
     source.append({'kind':i['kind'],'uuid':i['uuid'],'net':i['net'],'ref':i.get('ref'),'pin':i.get('pin'),'overlap_area_mm2':overlap,'distance_mm':gap})
   residual.append({'layer':layer,'kind':kind,'bounds_mm':list(g.bounds),'area_mm2':g.area,'refined_maximum_inscribed_diameter_mm':diam,'refinement_tolerance_mm':1e-9,'empty_after_5nm_inward_offset':g.buffer(-.000005).is_empty,'adjacent_or_overlapping_native_primitives':source,'disposition':'Sub-10 nm polygon contour remnant; retained in raw report. Not counted as fabricated isolated copper or an etch pocket.'})
assert all(x['refined_maximum_inscribed_diameter_mm']<.00001 and x['empty_after_5nm_inward_offset'] and x['adjacent_or_overlapping_native_primitives']for x in residual)
assert all(not D['screen']['layers'][l][f]for l in copper for f in ['acute_gap_candidates','sharp_tip_candidates'])
# Inventory actual solid-zone influence, including inherited thermal halos.
settings={x['uuid']:x for x in D['zones']['ground_pads']}
newzones=[dict(z,g=load(z['outline']))for z in D['zones']['ground_zones']if z['priority']==6];assert len(newzones)==2 and all(z['pad_connection']==2 for z in newzones)
thermal=[];intersections=[]
for i in items:
 if i['kind']!='pad' or i['net']!='GND':continue
 for z in newzones:
  if i['layer']not in z['layers']:continue
  overlap=i['g'].intersection(z['g']).area
  if overlap>1e-9:intersections.append({'ref':i['ref'],'pin':i['pin'],'layer':i['layer'],'zone_uuid':z['uuid'],'overlap_mm2':overlap,'pad_footprint_override':settings[i['uuid']]['resolved_pad_footprint_override']})
 for ref,pin in [('C1','1'),('C2','2'),('R2','2')]:
  if (i.get('ref'),i.get('pin'),i['layer'])!=(ref,pin,'B.Cu'):continue
  z=next(z for z in newzones if z['layers']==['B.Cu']);halo=i['g'].buffer(.5,quad_segs=64)
  # Saved zone copper must retain actual clear thermal sectors rather than fill the whole halo.
  ring=halo.difference(i['g']);void=ring.difference(copper['B.Cu']);ground=unary_union([x['g']for x in items if x['net']=='GND'and x['layer']=='B.Cu'])
  thermal.append({'ref':ref,'pin':pin,'pad_bounds_mm':list(i['g'].bounds),'pad_to_new_solid_zone_mm':i['g'].distance(z['g']),'solid_zone_overlap_with_0_5mm_halo_mm2':halo.intersection(z['g']).area,'saved_total_copper_void_in_thermal_ring_mm2':void.area,'saved_same_net_ground_in_thermal_ring_mm2':ring.intersection(ground).area,'pad_override':settings[i['uuid']]['resolved_pad_footprint_override']})
assert len(thermal)==3 and all(x['pad_override']==-1 and x['pad_to_new_solid_zone_mm']>=.5 and x['solid_zone_overlap_with_0_5mm_halo_mm2']<1e-9 and x['saved_total_copper_void_in_thermal_ring_mm2']>.01 for x in thermal)
assert all(x['pad_footprint_override']==2 or (x['ref'],x['pin'],x['layer'])==('R25','2','B.Cu')for x in intersections),intersections
main=next(z for z in D['zones']['ground_zones']if z['uuid']=='795c4093-4930-4bcb-9c07-8e31d04084fe');assert main['pad_connection']==1 and main['thermal_gap_mm']==.5
# The opposite-side RF antenna land is the same electrical net, not foreign copper.
rfnet='Net-(AE2-A)';front=unary_union([i['g']for i in items if i['layer']=='F.Cu'and i['net']==rfnet]);trace=unary_union([i['g']for i in items if i['layer']=='F.Cu'and i['net']==rfnet and i['kind']!='pad']);ant=next(i['g']for i in items if i.get('ref')=='AE2'and i['kind']=='pad'and i['layer']=='F.Cu');rear_gnd=unary_union([i['g']for i in items if i['layer']=='B.Cu'and i['net']=='GND']);foreign=[i for i in items if i['layer']=='B.Cu'and i['net']not in['GND',rfnet]]
transition=trace.difference(ant).difference(rear_gnd.buffer(.005));full_foreign=[{'uuid':i['uuid'],'net':i['net'],'overlap_mm2':front.intersection(i['g']).area}for i in foreign if front.intersection(i['g']).area>1e-8]
assert not full_foreign and transition.difference(ant.buffer(.15)).area<1e-9
r={'pcb_sha256':sha,'input_hashes':{n:hashlib.sha256(getattr(a,n).read_bytes()).hexdigest()for n in D},'raw_candidates_preserved':True,'residual_feature_count':len(residual),'maximum_residual_inscribed_diameter_nm':max(x['refined_maximum_inscribed_diameter_mm']for x in residual)*1e6,'residual_feature_dispositions':residual,'no_substantive_etch_candidates_at_declared_thresholds':True,'thermal_reliefs':thermal,'new_solid_zone_pad_intersections':intersections,'main_zone_thermal_gap_mm':main['thermal_gap_mm'],'rf_antenna_transition':{'rear_missing_trace_outside_pad_bounds_mm':list(transition.bounds),'rear_missing_trace_outside_pad_area_mm2':transition.area,'entire_missing_transition_contained_within_pad_plus_0_15mm':True,'foreign_copper_overlap_entire_RF_net':full_foreign,'antenna_rear_land_is_same_RF_net':True},'all_checks_pass':True,'limits':['The feature screen is a bounded CAD geometry screen, not an etchant-process guarantee.','Numerical residual diameters are below 10 nm and far below 2 um polygon extraction approximation; the raw contour records are retained.','Antenna through-hole and its 0.15 mm copper-clearance transition intentionally lack a rear ground plane. The RF line beyond this transition is evaluated separately.','Local solid-zone coverage changes R25.2 to solid intentionally. C1/C2/R2 preserve inherited 0.5 mm thermal neighborhoods and actual empty sectors in saved copper.']}
a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:v for k,v in r.items()if k in ['pcb_sha256','residual_feature_count','maximum_residual_inscribed_diameter_nm','thermal_reliefs','new_solid_zone_pad_intersections','rf_antenna_transition','all_checks_pass']},indent=2))
