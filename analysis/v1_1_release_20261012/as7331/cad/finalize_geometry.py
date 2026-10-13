"""Post-route deterministic arc, explicit tenting and removal of obsolete zone caches."""
from pathlib import Path
import sys,json,uuid,math
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'finish'))
from build_green_mask import spans,parse,scalar,replace,set_child
P=Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/as7331/candidate/stratolink.kicad_pcb'
s=P.read_text();rr=json.loads((HERE/'routing-proposal.json').read_text())
def uid(k):return str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-as7331-route-'+k))
ids={uid(r['name']+'seg'+str(i)) for r in rr if r['name'].startswith('vstor-detour') for i in range(len(r['segments']))}
viaids={uid(r['name']+'via'+str(i)) for r in rr for i in range(len(r['vias']))}
ownkeys=['vstor-arc-join'+str(i) for i in range(8)]+['vstor-rounded-corner','c12-ground-spoke','r27-ground-ring','r27-ground-via0','r27-ground-via1','top-ground-via','top-ground-back','top-ground-front']
ids.update(uid(k) for k in ownkeys)
ed=[]
for a,b,d in spans(s):
 block=s[a:b]
 if d==2 and block.startswith('(filled_polygon'):ed.append((a,b,''))
 if d==1:
  n=parse(block)
  if scalar(n,'uuid') in ids:ed.append((a,b,''))
  elif n[0]=='via' and scalar(n,'uuid') in viaids:ed.append((a,b,set_child(block,'tenting','(tenting (front yes) (back yes))')))
s=replace(s,ed)
points=[(70.8,33.503),(70.575,33.503),(69.975,32.903),(69.975,32.375),(72.525,29.825),(74.327,29.825)]
segments=list(zip(points,points[1:]))+[[[76.247,31.745],[76.275,31.773]],[[76.275,31.773],[76.275,42.634911]],[[76.275,42.634911],[75.909911,43.0]]]
add=[]
for i,(a,b) in enumerate(segments):add.append(f'(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width .25) (layer "F.Cu") (net "VSTOR") (uuid "{uid("vstor-arc-join"+str(i))}"))')
add.append(f'(arc (start 74.327 29.825) (mid {74.327+1.920/math.sqrt(2):.6f} {31.745-1.920/math.sqrt(2):.6f}) (end 76.247 31.745) (width .25) (layer "F.Cu") (net "VSTOR") (uuid "{uid("vstor-rounded-corner")}"))')
# Restore local ground returns interrupted by the displaced UV/reference branches.
grounds=[('c12-ground-spoke',(71.156,41.142),(70.4,41.142),'F.Cu'),('r27-ground-ring',(71.9,33.1675),(74.327,31.745),'F.Cu'),('r27-ground-via0',(71.9,33.1675),(71.3875,32.655),'F.Cu'),('r27-ground-via1',(71.3875,32.655),(70.612,32.655),'F.Cu'),('top-ground-back',(71.67,33.664999),(73.025,35.1),'B.Cu'),('top-ground-front',(73.025,35.1),(73.5,35.525),'F.Cu')]
for key,a,b,side in grounds:add.append(f'(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width .2) (layer \"{side}\") (net \"GND\") (uuid \"{uid(key)}\"))')
add.append(f'(via (at 73.025 35.1) (size .5) (drill .3) (layers \"F.Cu\" \"B.Cu\") (tenting (front yes) (back yes)) (net \"GND\") (uuid \"{uid("top-ground-via")}\"))')
P.write_text(s.rstrip()[:-1]+'\n'+'\n'.join(add)+'\n)\n')
print('Cleared cached fills; installed native VSTOR arc and tented',len(viaids),'new vias')
