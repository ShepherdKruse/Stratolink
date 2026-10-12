#!/usr/bin/env python3
"""Compare recorded solar revision reports to the pinned microphone revision."""
from collections import Counter
from pathlib import Path
import json
import math
import sys
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT/'analysis/v1_1_microphone_20261012/review'))
from check_drc_delta import parse, by_uuid, signature


def field(obj, name):
    return next(x[1:] for x in obj if isinstance(x,list) and x[0]==name)


def point_segment_distance(p, a, b):
    d=[b[i]-a[i] for i in range(2)]
    t=max(0,min(1,sum((p[i]-a[i])*d[i] for i in range(2))/sum(v*v for v in d)))
    return math.dist(p,[a[i]+t*d[i] for i in range(2)])


def compare(oldpath,newpath,oldobjects,newobjects):
    old,new=(json.loads(p.read_text()) for p in (oldpath,newpath))
    result={}
    for category in ('violations','schematic_parity','unconnected_items'):
        a,b=(Counter(signature(x) for x in d[category]) for d in (old,new))
        added=[json.loads(x) for x in (b-a).elements()]
        removed=[json.loads(x) for x in (a-b).elements()]
        for finding in added:
            assert finding['type']=='copper_edge_clearance', ('Unreviewed new finding',finding)
            ids=finding['item_uuids']
            track=next(u for u in ids if newobjects[u][0]=='segment')
            edge=next(u for u in ids if newobjects[u][0]=='gr_line')
            assert oldobjects[track]==newobjects[track], 'Previously flagged route changed'
            prior=next(x for x in old[category] if x['type']=='copper_edge_clearance' and track in [i['uuid'] for i in x['items']])
            oldedge=next(i['uuid'] for i in prior['items'] if i['uuid']!=track)
            oa,ob=(list(map(float,field(oldobjects[oldedge],k))) for k in ('start','end'))
            endpoints=[list(map(float,field(newobjects[edge],k))) for k in ('start','end')]
            displacement=max(point_segment_distance(p,oa,ob) for p in endpoints)
            assert displacement<.001, ('Outer boundary shifted',displacement)
            finding['classification']='inherited_route_against_resegmented_outer_edge'
            finding['maximum_edge_endpoint_displacement_mm']=displacement
            finding['reason']='Copper object is byte-equivalent as an S-expression; this same route was flagged before. The straight outer edge was split to form the separate solar notch.'
        result[category]={'before':len(old[category]),'after':len(new[category]),'added':added,'removed':removed}
    return result


def main():
    baseline=subprocess.check_output(['git','show','1aed52ff7af3d27aef6ff4b0ceba710c57dc6865:hardware/pcb/stratolink.kicad_pcb'],cwd=ROOT,text=True)
    oldobjects=by_uuid(parse(baseline))
    newobjects=by_uuid(parse((ROOT/'hardware/pcb/stratolink.kicad_pcb').read_text()))
    oldroot=ROOT/'analysis/v1_1_microphone_20261012'
    results={
        'project':compare(oldroot/'drc-project.json',HERE/'final/drc-project.json',oldobjects,newobjects),
        'diagnostic_0p15mm_clearance_0p20mm_edge':compare(oldroot/'review/clearance_screen/after/drc.json',HERE/'final/drc-diagnostic.json',oldobjects,newobjects),
    }
    erc=[]
    for p in [oldroot/'erc-project.json',HERE/'final/erc.json']:
        erc.append(Counter(signature(x) for sheet in json.loads(p.read_text())['sheets'] for x in sheet['violations']))
    added=[json.loads(x) for x in (erc[1]-erc[0]).elements()]
    assert not added, ('New ERC findings',added)
    results['erc']={'before':sum(erc[0].values()),'after':sum(erc[1].values()),'added':added,'removed':[json.loads(x) for x in (erc[0]-erc[1]).elements()]}
    results['status']='pass_no_new_unexplained_findings'
    (HERE/'drc-comparison.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps({k:{c:{q:r[q] for q in ('before','after')} for c,r in v.items()} for k,v in results.items() if k not in ('erc','status')},indent=2))
    print('ERC:',results['erc'])


if __name__=='__main__':main()
