#!/usr/bin/env python3
"""Short tented-via alternative joining U6 right ground bank to rear GND."""
from pathlib import Path
import argparse,importlib.util,hashlib,json,uuid
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('m',HERE.parents[1]/'identities/build_metadata.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pcb',type=Path,required=True);p=ap.parse_args().pcb;assert '/hardware/pcb/' not in str(p.resolve())
    t=p.read_text();before=hashlib.sha256(t.encode()).hexdigest();ed=[]
    for s,e,d in m.m.spans(t):
        if d==2 and t[s:e].split(None,1)[0]=='(filled_polygon':ed.append((s,e,''))
    t=m.m.replace(t,ed);pts=[(75.3,37.85),(75.7,38.25),(75.7,39.0)];add=[]
    for i,(s,e) in enumerate(zip(pts,pts[1:])):
        u=uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-review-right-ground-'+str(i))
        add.append(f'(segment (start {s[0]} {s[1]}) (end {e[0]} {e[1]}) (width .15) (layer "F.Cu") (net "GND") (uuid "{u}"))')
    u=uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-review-right-ground-via')
    add.append(f'(via (at 75.7 39.0) (size .5) (drill .3) (layers "F.Cu" "B.Cu") (tenting (front yes) (back yes)) (net "GND") (uuid "{u}"))')
    t=t.rstrip()[:-1]+'\n'+'\n'.join(add)+'\n)\n';p.write_text(t)
    r=dict(before_sha256=before,after_sha256=hashlib.sha256(t.encode()).hexdigest(),path_mm=pts,trace_width_mm=.15,via_diameter_mm=.5,via_drill_mm=.3,via_tenting='both')
    (p.parent/'right-ground-proposal.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
