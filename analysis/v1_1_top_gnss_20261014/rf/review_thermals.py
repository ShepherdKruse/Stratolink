#!/usr/bin/env python3
"""Read-only comparison of the pads affected by the RF reference-zone boundary.

Inputs are full saved-copper extract_rf.py outputs. The comparison measures
actual copper, including retained ground tracks, rather than only pad settings.
"""
from pathlib import Path
import argparse,json,hashlib
from shapely import make_valid
from shapely.geometry import Polygon
from shapely.ops import unary_union

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--baseline',type=Path,required=True)
p.add_argument('--routing',type=Path,required=True)
p.add_argument('--final',type=Path,required=True)
p.add_argument('--ledger',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
data=[json.loads(x.read_text())for x in[a.baseline,a.routing,a.final]]
ledger=json.loads(a.ledger.read_text())
assert [d['pcb_sha256']for d in data[1:]]==[ledger['source_sha256'],ledger['final_sha256']]
def geo(i):
    return unary_union([make_valid(Polygon(x['shell'],x['holes']))for x in i['polygons']])
def pad(d,ref,pin):
    rows=[i for i in d['items']if i['kind']=='pad'and i['layer']=='B.Cu'and i['ref']==ref and i['pin']==pin]
    assert len(rows)==1 and rows[0]['net']=='GND'
    return geo(rows[0])
ground=[unary_union([geo(i)for i in d['items']if i['layer']=='B.Cu'and i['net']=='GND'])for d in data]
trim=next(q for q in ledger['changes']if q['action']=='trim_solid_RF_zone_to_preserve_thermals')
zones=[Polygon(trim['before']),Polygon(trim['after'])]
results=[]
for ref,pin in [('C1','1'),('C2','2'),('R2','2'),('R25','2')]:
    pads=[pad(d,ref,pin)for d in data]
    assert all(pads[0].equals(x)for x in pads[1:])
    ring=pads[0].buffer(.05).difference(pads[0])
    coverage=[g.intersection(ring).area/ring.area for g in ground]
    halo=pads[0].buffer(.5)
    overlap=zones[-1].intersection(halo).area
    if ref!='R25':assert overlap<1e-10,(ref,overlap)
    else:assert zones[-1].covers(pads[-1])
    results.append(dict(ref=ref,pin=pin,pad_geometry_exact=True,
                        ground_fraction_in_50um_ring=dict(zip(['left_feed_baseline','routing_pretrim','final'],coverage)),
                        final_solid_zone_overlap_with_pad_and_0p5mm_halo_mm2=overlap,
                        final_solid_zone_distance_to_pad_mm=zones[-1].distance(pads[-1]),
                        disposition='Intentionally solid for rear RF reference'if ref=='R25'else
                        'New solid zone excludes full inherited 0.5 mm thermal neighborhood; retained routed ground connections remain'))
result=dict(final_pcb_sha256=data[-1]['pcb_sha256'],source_pcb_hashes=[d['pcb_sha256']for d in data],
            evidence_hashes={str(x):hashlib.sha256(x.read_bytes()).hexdigest()for x in[a.baseline,a.routing,a.final,a.ledger]},
            pads=results,
            limits=['50 micrometre ring fraction describes actual saved copper immediately outside the unchanged pad; it is not a thermal resistance or reflow simulation.',
                    'Reference-zone trimming restores inherited thermal policy. The entire surrounding ground fill need not match the older left-feed layout, because supply routing and the inductor position intentionally changed.',
                    'Pad and zone connection metadata are independently proven exact in cleanup-scope-review.json.'])
a.output.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({q['ref']:q['ground_fraction_in_50um_ring']for q in results},indent=2))
