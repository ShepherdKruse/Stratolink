#!/usr/bin/env python3
"""Read-only saved-copper comparison for the final fabrication cleanup.

Inputs are produced by the existing extract_rf.py --include-graphics. This
reports geometric changes, not electrical/EM qualification or automatic signoff.
"""
from pathlib import Path
import argparse, hashlib, json, re
from shapely import make_valid, maximum_inscribed_circle
from shapely.geometry import Polygon
from shapely.ops import unary_union

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('before',type=Path)
ap.add_argument('after',type=Path)
ap.add_argument('output',type=Path)
ap.add_argument('--ledger',type=Path,help='Bind native changes and copper-delta locality to this explicit cleanup ledger.')
a=ap.parse_args()
before=json.loads(a.before.read_text());after=json.loads(a.after.read_text())
assert before['graphics_included'] and after['graphics_included']

def geo(item):
    return unary_union([make_valid(Polygon(p['shell'],p['holes'])) for p in item['polygons']])

def index(data,kinds):
    return {(i['uuid'],i['layer']):i for i in data['items'] if i['kind'] in kinds}

def differences(old,new):
    removed=sorted(set(old)-set(new));added=sorted(set(new)-set(old));changed=[]
    for key in sorted(set(old)&set(new)):
        if old[key] != new[key]:
            changed.append(dict(uuid=key[0],layer=key[1],before=old[key],after=new[key]))
    return dict(removed=removed,added=added,changed=changed)

def polygons(g):
    if g.geom_type=='Polygon':return [g]
    return sum([polygons(x) for x in getattr(g,'geoms',[])],[])

def components(g,minimum_area=1e-10):
    return [dict(area_mm2=p.area,bounds_mm=list(p.bounds),
                 maximum_inscribed_diameter_mm=2*maximum_inscribed_circle(p,tolerance=1e-8).length)
            for p in sorted(polygons(g),key=lambda x:-x.area) if p.area>minimum_area]

ledger=json.loads(a.ledger.read_text()) if a.ledger else None
if ledger:
    assert ledger['source_sha256']==before['pcb_sha256']
    assert ledger['final_sha256']==after['pcb_sha256']

def permitted_regions(layer,net):
    regions=[]
    for q in ledger['changes']:
        if q['layer']!=layer:continue
        if q['action']=='add_same_net_fillet':
            # Same-net copper is bounded tightly to the actual authored shape.
            # Ground fill beside it can also change within its normal clearance.
            if q['net']==net:regions.append(Polygon(q['points']).buffer(.002))
            elif net=='GND':regions.append(Polygon(q['points']).buffer(.5))
        elif net=='GND' and q['action']=='add_source_zone_hole':
            regions.append(Polygon(q['points']).buffer(.5))
        elif net=='GND' and q['action']=='trim_solid_RF_zone_to_preserve_thermals':
            regions.append(Polygon(q['before']).symmetric_difference(Polygon(q['after'])).buffer(.6))
    return unary_union(regions)

pads=differences(index(before,{'pad'}),index(after,{'pad'}))
tracks=differences(index(before,{'PCB_TRACK','PCB_ARC','PCB_VIA'}),index(after,{'PCB_TRACK','PCB_ARC','PCB_VIA'}))
footprints={ref:dict(before=before['footprints'].get(ref),after=after['footprints'].get(ref))
            for ref in set(before['footprints'])|set(after['footprints'])
            if before['footprints'].get(ref)!=after['footprints'].get(ref)}
changes=[]
keys={(i['layer'],i['net'])for d in[before,after]for i in d['items']}
for layer,net in sorted(keys):
    old=unary_union([geo(i)for i in before['items']if(i['layer'],i['net'])==(layer,net)])
    new=unary_union([geo(i)for i in after['items']if(i['layer'],i['net'])==(layer,net)])
    plus=new.difference(old);minus=old.difference(new)
    if plus.area+minus.area>1e-8:
        row=dict(layer=layer,net=net,added_area_mm2=plus.area,removed_area_mm2=minus.area,
                            added_bounds_mm=list(plus.bounds)if not plus.is_empty else None,
                            removed_bounds_mm=list(minus.bounds)if not minus.is_empty else None,
                            added_components=components(plus),removed_components=components(minus))
        if ledger:
            outside=unary_union([plus,minus]).difference(permitted_regions(layer,net))
            row['outside_declared_local_regions_area_mm2']=outside.area
            row['outside_declared_local_regions_components']=components(outside)
            row['outside_maximum_inscribed_diameter_mm']=max([x['maximum_inscribed_diameter_mm'] for x in components(outside)]+[0])
            assert outside.area<1e-5 and row['outside_maximum_inscribed_diameter_mm']<.00001,row
        changes.append(row)

def parse(text):
    stack=[];root=None
    for token in re.findall(r'"(?:\\.|[^"\\])*"|[()]|[^\s()]+',text):
        if token=='(':
            node=[]
            if stack:stack[-1].append(node)
            else:root=node
            stack.append(node)
        elif token==')':stack.pop()
        else:stack[-1].append(json.loads(token)if token.startswith('"')else token)
    return root

def one(node,kind):
    return next((x[1:]for x in node if isinstance(x,list)and x[0]==kind),None)

def without_fills(node):
    return [without_fills(x)if isinstance(x,list)else x for x in node
            if not(isinstance(x,list)and x[0]=='filled_polygon')]

native=None
if ledger:
    raw=[Path(d['source']).read_bytes()for d in[before,after]]
    assert [hashlib.sha256(x).hexdigest()for x in raw]==[before['pcb_sha256'],after['pcb_sha256']]
    trees=[parse(x.decode())for x in raw]
    def key(q):return tuple(one(q,'uuid') or [q[0]])
    indices=[{key(q):without_fills(q)for q in t if isinstance(q,list)}for t in trees]
    old,new=indices
    adds=set(new)-set(old);removes=set(old)-set(new)
    changed={k for k in set(old)&set(new)if old[k]!=new[k]}
    expected_adds={(q['uuid'],)for q in ledger['changes']if q['action']=='add_same_net_fillet'}
    expected_changed={(q['zone_uuid'],)for q in ledger['changes']if 'zone_uuid'in q}
    assert adds==expected_adds and not removes and changed==expected_changed
    def pts(node):return [[round(float(v),6)for v in x[1:]]for x in one(node,'pts')]
    def rounded(points):return [[round(float(v),6)for v in x]for x in points]
    for q in ledger['changes']:
        if q['action']=='add_same_net_fillet':
            node=new[(q['uuid'],)]
            assert node[0]=='gr_poly'and pts(node)==rounded(q['points'])
            assert one(node,'layer')==[q['layer']]and one(node,'net')==[q['net']]
    zone_details=[]
    for k in sorted(changed):
        o,n=old[k],new[k]
        assert o[0]==n[0]=='zone'
        # Only zone contours change. Connection policies and every other field stay exact.
        assert [q for q in o if not(isinstance(q,list)and q[0]=='polygon')]==[q for q in n if not(isinstance(q,list)and q[0]=='polygon')]
        op=[pts(q)for q in o if isinstance(q,list)and q[0]=='polygon']
        np=[pts(q)for q in n if isinstance(q,list)and q[0]=='polygon']
        expected=list(op)
        for q in ledger['changes']:
            if q.get('zone_uuid')!=k[0]:continue
            if q['action']=='add_source_zone_hole':expected.append(rounded(q['points']))
            elif q['action']=='trim_solid_RF_zone_to_preserve_thermals':
                assert op==[rounded(q['before'])]
                expected=[rounded(q['after'])]
        assert np==expected
        zone_details.append(dict(uuid=k[0],before_polygons=[q for q in o if isinstance(q,list)and q[0]=='polygon'],
                                 after_polygons=[q for q in n if isinstance(q,list)and q[0]=='polygon']))
    native=dict(added_graphic_uuids=sorted(k[0]for k in adds),removed_objects=[],changed_zone_contours=zone_details,
                all_other_native_nodes_exact=True,all_zone_connection_settings_exact=True,all_changed_contours_match_ledger_to_native_nanometre_grid=True)
result=dict(before_pcb_sha256=before['pcb_sha256'],after_pcb_sha256=after['pcb_sha256'],
            extraction_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest()for p in[a.before,a.after]},
            pad_changes=pads,track_changes=tracks,footprint_changes=footprints,
            stackup_equal=before['stackup']==after['stackup'],
            excluded_copper_text_equal=before['excluded_copper_text']==after['excluded_copper_text'],
            copper_union_changes=changes,
            native_scope=native,cleanup_ledger_sha256=hashlib.sha256(a.ledger.read_bytes()).hexdigest()if ledger else None,
            notes=['A human must bind the listed copper changes to the cleanup ledger and inspect their local geometry.',
                   'Ground-fill changes are measured, not exempted from review.',
                   'Locality regions include 0.5 mm zone-clearance response around source holes/foreign fillets and 0.6 mm around the trimmed zone. Same-net fillet copper itself is bounded to its exact polygon plus 2 micrometres.',
                   'Sub-grid copper-difference seams outside those regions are reported by area and maximum inscribed width, not treated as manufactured narrow features.',
                   'Native extraction uses requested 2 micrometre polygon approximation. This is not an EM model.'])
a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items()if k not in['extraction_hashes','pad_changes','track_changes']},indent=2))
