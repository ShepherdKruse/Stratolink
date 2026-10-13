"""Remove superseded ADC sense copper and stale fill caches, not net drivers."""
from pathlib import Path
import importlib.util,json
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('build',HERE/'build_balancer_candidate.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=m.OUT/'stratolink.kicad_pcb';s=p.read_text();removed=set(json.loads((HERE/'adc-stub-removal.json').read_text())['removed_uuids']);removed.add('6cb4b0b4-5fa9-462d-95d3-a28344e6cc28');edits=[];seen=set()
for st,en,d in m.prior.spans(s):
 if d==1:
  n=m.a.parse(s[st:en])
  if n[0] in ['segment','via'] and m.a.scalar(n,'uuid') in removed:seen.add(m.a.scalar(n,'uuid'));edits.append((st,en,''))
 elif d==2 and s[st:en].startswith(('(filled_polygon','(filled_areas_thickness')):edits.append((st,en,''))
assert seen==removed-{'acc183ca-d474-44e8-bd3c-69ef8aaafa23'},seen^removed
s=m.prior.replace(s,edits)
# Local thermal dimensions preserve two-spoke fill with the integrated J4 land.
# Do not change zone defaults, connection style, or any pad's copper geometry.
edits=[]
for st,en,d in m.prior.spans(s):
 if d!=1:continue
 n=m.a.parse(s[st:en]);ref=m.a.prop(n,'Reference') if n[0]=='footprint' else None
 if ref not in ['D3','J4']:continue
 block=s[st:en];pe=[]
 for ps,pn,pd in m.prior.spans(block):
  if pd!=1:continue
  pad=m.a.parse(block[ps:pn])
  if pad[0]=='pad' and pad[1]=='1':
   assert not m.a.one(pad,'thermal_gap') and not m.a.one(pad,'thermal_bridge_width')
   pe.append((ps,pn,block[ps:pn-1]+'(thermal_gap 0.25) (thermal_bridge_width 0.25))'))
 assert len(pe)==1
 edits.append((st,en,m.prior.replace(block,pe)))
assert len(edits)==2
s=m.prior.replace(s,edits);s='\n'.join('' if not line.strip() else line for line in s.splitlines())+'\n';p.write_text(s);print('Finalized',len(seen),'superseded objects; cached fill removed; D3/J4 local thermals .25/.25')
