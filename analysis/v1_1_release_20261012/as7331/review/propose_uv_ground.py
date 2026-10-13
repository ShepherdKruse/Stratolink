#!/usr/bin/env python3
"""Apply the explicit U6.11-to-U6.14 front bridge on a disposable bus-native7 copy."""
from pathlib import Path
import argparse, importlib.util, uuid, hashlib, json
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('m',HERE.parents[1]/'identities/build_metadata.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);a=m.a
def uid(name):return str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-as7331-route-'+name))
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pcb',type=Path,required=True);p=ap.parse_args().pcb
    assert '/hardware/pcb/' not in str(p.resolve())
    text=p.read_text();before=hashlib.sha256(text.encode()).hexdigest()
    remove={uid('supply-joinseg0'):'+3.3V',uid('uv-ground-viavia0'):'GND',uid('uv-digital-groundseg0'):'GND',uid('uv-digital-groundseg1'):'GND'}
    edits=[];seen=set();cleared=0
    for s,e,d in m.m.spans(text):
        n=a.parse(text[s:e])
        if d==1 and n[0] in ['via','segment'] and a.scalar(n,'uuid') in remove:
            key=a.scalar(n,'uuid');assert a.scalar(n,'net')==remove[key],(key,a.scalar(n,'net'))
            seen.add(key);edits.append((s,e,''))
        if d==2 and n[0]=='filled_polygon':edits.append((s,e,''));cleared+=1
    assert seen==set(remove),(seen,remove)
    text=m.m.replace(text,edits)
    paths=[('+3.3V',[(74.5,35.525),(74.5,35.8),(74.75,36.05),(74.75,38.20),(74.5,38.45),(74.5,38.675)]),
           ('GND',[(73.2,37.35),(74.325,37.35),(74.325,38.19),(74.0,38.515),(74.0,38.675)])]
    items=[]
    for j,(net,pts) in enumerate(paths):
        for i,(s,e) in enumerate(zip(pts,pts[1:])):
            width=.125 if net=='GND' else .15
            items.append(f'(segment (start {s[0]} {s[1]}) (end {e[0]} {e[1]}) (width {width}) (layer "F.Cu") (net "{net}") (uuid "{uid("review-UV-ground-"+str(j)+"-"+str(i))}"))')
    text=text.rstrip()[:-1]+'\n'+'\n'.join(items)+'\n)\n';p.write_text(text)
    out=dict(source_sha256=before,proposal_sha256=hashlib.sha256(text.encode()).hexdigest(),removed=remove,added_paths=paths,width_mm={'+3.3V':.15,'GND':.125},layer='F.Cu',removed_stale_fills=cleared)
    (p.parent/'uv-ground-proposal.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
