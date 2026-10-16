#!/usr/bin/env python3
"""Check one mask text aperture against connected front-side ground copper."""
from pathlib import Path
import argparse,json
from shapely import make_valid
from shapely.geometry import Polygon
from shapely.ops import unary_union
p=argparse.ArgumentParser();p.add_argument('--copper',type=Path,required=True);p.add_argument('--mask',type=Path,required=True);p.add_argument('--physical',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--uuid',default='517aa68d-ce15-590c-89c7-5c81211a9ef5');a=p.parse_args();D=json.loads(a.copper.read_text());M=json.loads(a.mask.read_text());G=json.loads(a.physical.read_text());assert D['pcb_sha256']==M['pcb_sha256']==G['pcb_sha256']
def shape(i):return unary_union([make_valid(Polygon(p['shell'],p['holes']))for p in i['polygons']])
items=[dict(i,g=shape(i))for i in D['items']if i['layer']=='F.Cu'];gnd=unary_union([i['g']for i in items if i['net']=='GND']);foreign=unary_union([i['g']for i in items if i['net'] and i['net']!='GND']);glyph=next(m for m in M['items']if m['uuid']==a.uuid);aperture=shape(glyph);rn=next(n for n in G['nets']if n['net']=='GND');islands=[p for c in rn['components']if not c['pads']for p in c['pieces']if p['layer']=='F.Cu']
r={'pcb_sha256':D['pcb_sha256'],'mask_glyph_uuid':glyph['uuid'],'text':glyph['text'],'xy_mm':glyph['position'],'aperture_bounds_mm':list(aperture.bounds),'aperture_area_mm2':aperture.area,'uncovered_by_ground_area_mm2':aperture.difference(gnd).area,'foreign_net_overlap_area_mm2':aperture.intersection(foreign).area,'minimum_foreign_net_distance_mm':aperture.distance(foreign),'minimum_ground_edge_distance_mm':aperture.distance(gnd.boundary),'ground_pad_bearing_component_count':rn['pad_bearing_component_count'],'front_unanchored_ground_pieces':islands,'pass':aperture.difference(gnd).area<1e-8 and aperture.intersection(foreign).area<1e-8 and rn['pad_bearing_component_count']==1 and not islands,'method':'Full native text aperture against saved front copper. Graph verifies GND connectivity with plated layer joins. No source modification.'};a.output.write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
