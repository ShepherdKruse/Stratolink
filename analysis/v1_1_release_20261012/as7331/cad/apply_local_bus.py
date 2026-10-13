"""Integrate independently native-checked U7/AS7331 bus/return topology.

The 0.125 mm middle ground neck passes the existing native .1 mm trace rule.
Endpoints are .15 mm; all new vias are .5/.3 and explicitly tented both faces.
"""
from pathlib import Path
import json,uuid,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'finish'))
from build_green_mask import spans,parse,scalar,replace
out=Path(sys.argv[1]) if len(sys.argv)>1 else Path.home()/'Repositories/ai-working/scratch/stratolink-release-20261012/as7331/candidate'
p=out/'stratolink.kicad_pcb';s=p.read_text();old=json.loads((HERE/'routing-proposal.json').read_text())
names={'sda-u7-via','sda-uv-via','sda-u7','sda-bus','u7-ground-via','u7-ground-bottom','scl','scl-local-bus'}
ids=set()
for rr in old:
 if rr['name'] in names:
  for ty in ('seg','via'):
   for i in range(len(rr['segments' if ty=='seg' else 'vias'])):ids.add(str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-as7331-route-'+rr['name']+ty+str(i))))
new=json.loads((HERE/'local_bus_routes.json').read_text());add=[]
for rr in new:
 for i,t in enumerate(rr['segments']):
  a,b=t['s'],t['e'];ident=str(uuid.uuid5(uuid.NAMESPACE_URL,rr['name']+str(i)));ids.add(ident)
  add.append(f'(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width {t["width"]}) (layer "{t["side"]}") (net "{t["net"]}") (uuid "{ident}"))')
 for i,a in enumerate(rr['vias']):
  ident=str(uuid.uuid5(uuid.NAMESPACE_URL,rr['name']+'via'+str(i)));ids.add(ident)
  add.append(f'(via (at {a[0]} {a[1]}) (size .5) (drill .3) (layers "F.Cu" "B.Cu") (tenting (front yes) (back yes)) (net "{rr["net"]}") (uuid "{ident}"))')
ident=str(uuid.uuid5(uuid.NAMESPACE_URL,'gnd-root7via'));ids.add(ident)
add.append(f'(via (at 72.2 39.16) (size .5) (drill .3) (layers "F.Cu" "B.Cu") (tenting (front yes) (back yes)) (net "GND") (uuid "{ident}"))')
ed=[]
for a,b,d in spans(s):
 if d==1 and scalar(parse(s[a:b]),'uuid') in ids:ed.append((a,b,''))
 elif s[a:b].startswith('(filled_polygon'):ed.append((a,b,''))
s=replace(s,ed);p.write_text(s.rstrip()[:-1]+'\n'+'\n'.join(add)+'\n)\n')
print('Integrated local bus/ground topology:',len(add),'items')
