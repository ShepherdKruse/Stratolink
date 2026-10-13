#!/usr/bin/env python3
from pathlib import Path
import json,subprocess,concurrent.futures,sys
H=Path(__file__).resolve().parent;d=json.loads((H/('mixed-trials.json' if '--mixed-only' in sys.argv else 'trials.json')).read_text());CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
def check(t):
 p=Path(t['directory']);r=subprocess.run([CLI,'pcb','drc','--refill-zones','--save-board','--schematic-parity','--format','json','--output',str(p/'drc.json'),str(p/'stratolink.kicad_pcb')],capture_output=True,text=True)
 (p/'drc.log').write_text(r.stdout+r.stderr);assert r.returncode==0,(t,r.stdout,r.stderr)
 dr=json.loads((p/'drc.json').read_text());thermals=[v for v in dr['violations'] if v['type']=='starved_thermal']
 return t|dict(violations=len(dr['violations']),opens=len(dr['unconnected_items']),parity=len(dr['schematic_parity']),thermals=thermals)
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
 results=list(pool.map(check,d['trials']))
(H/('mixed-trial-results.json' if '--mixed-only' in sys.argv else 'trial-results.json')).write_text(json.dumps(dict(baseline=d['baseline'],trials=results),indent=2)+'\n')
for r in results:print(r['name'],r['violations'],r['opens'],[(v['items'][1]['description'],v['description']) for v in r['thermals']])
