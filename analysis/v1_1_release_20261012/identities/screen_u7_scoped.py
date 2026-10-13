#!/usr/bin/env python3
"""Check scoped clearance rule and an intentionally failing 0.13 mm control."""
from pathlib import Path
import shutil, json, subprocess
import build_u7 as u
HERE=Path(__file__).resolve().parent
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
src=u.OUT; dst=src.parent/'candidate-u7-scoped-0.15'; dst.mkdir(exist_ok=True)
for n in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','stratolink.kicad_dru','fp-lib-table','sym-lib-table']:
 shutil.copyfile(src/n,dst/n)
for name in ['fp-lib-table','sym-lib-table']:
 p=dst/name; p.write_text(p.read_text().replace('${KIPRJMOD}',str(src)))
p=dst/'stratolink.kicad_pro'; j=json.loads(p.read_text()); d=j['board']['design_settings']
d['rules']['min_clearance']=.1; d['rules']['min_copper_edge_clearance']=.2
d['rule_severities']['clearance']='error'; d['rule_severities']['copper_edge_clearance']='error'
for c in j['net_settings']['classes']: c['clearance']=.15
p.write_text(json.dumps(j))
rule=(dst/'stratolink.kicad_dru').read_text()
outputs={}
for name,content in [('scoped',rule),('negative-control',rule.replace('(min 0.12mm)','(min 0.13mm)'))]:
 (dst/'stratolink.kicad_dru').write_text(content)
 out=HERE/('candidate-u7-'+name+'-0.15.json')
 r=subprocess.run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(out),str(dst/'stratolink.kicad_pcb')],capture_output=True,text=True)
 (dst/(name+'.log')).write_text(r.stdout+r.stderr); assert r.returncode==0
 outputs[name]=json.loads(out.read_text())
(dst/'stratolink.kicad_dru').write_text(rule)
sig=lambda v:(v['type'],tuple(sorted(i['uuid'] for i in v.get('items',[]))))
base=json.loads((HERE/'baseline-u7-screen-0.15.json').read_text())
assert {sig(v) for v in base['violations']}=={sig(v) for v in outputs['scoped']['violations']}
added=[v for v in outputs['negative-control']['violations'] if sig(v) not in {sig(v) for v in outputs['scoped']['violations']}]
assert len(added)==2 and all("rule 'U7 escape SCL" in v['description'] and '0.1300' in v['description'] and '0.1280' in v['description'] for v in added)
assert not outputs['scoped']['unconnected_items'] and not outputs['scoped']['schematic_parity']
(HERE/'u7-scoped-rule-proof.json').write_text(json.dumps({'status':'PASS','baseline_violations':len(base['violations']),'candidate_scoped_violations':len(outputs['scoped']['violations']),'new_violations':0,'negative_control_new_violations':added},indent=2)+'\n')
print('PASS: exact baseline violations preserved; two expected failures at the 0.13 mm control.')
