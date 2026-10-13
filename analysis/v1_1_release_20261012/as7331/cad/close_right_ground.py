"""Join AS7331 right analog-ground island to H2's retained grounded annulus.

A local .5/.3 via is blocked by the unchanged rear solar strip and front VSTOR.
This .15 mm front return requires no extra via or changed board rule.
"""
from pathlib import Path
import sys,uuid
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parent/'finish'))
from build_green_mask import spans,parse,scalar,replace
out=Path(sys.argv[1]) if len(sys.argv)>1 else Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/as7331/candidate'
p=out/'stratolink.kicad_pcb';s=p.read_text();add=[];ids=set()
paths=[[(75.3,36.35),(75.8,36.35),(75.8,33.4),(74.327,31.745)],[(75.3,36.35),(75.3,36.85),(75.3,37.35),(75.3,37.85)]]
for j,pts in enumerate(paths):
 for i,(a,b) in enumerate(zip(pts,pts[1:])):
  ident=str(uuid.uuid5(uuid.NAMESPACE_URL,f'stratolink-as7331-right-ground-{j}-{i}'));ids.add(ident)
  add.append(f'(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width .15) (layer "F.Cu") (net "GND") (uuid "{ident}"))')
s=replace(s,[(a,b,'') for a,b,d in spans(s) if s[a:b].startswith('(filled_polygon') or (d==1 and scalar(parse(s[a:b]),'uuid') in ids)])
p.write_text(s.rstrip()[:-1]+'\n'+'\n'.join(add)+'\n)\n')
print('Joined right analog-ground island using',len(add),'front traces')
