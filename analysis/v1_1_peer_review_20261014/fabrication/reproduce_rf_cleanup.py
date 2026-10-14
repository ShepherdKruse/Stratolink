#!/usr/bin/env python3
"""Reproduce final copper/model/library cleanup from the frozen combined RF bundle."""
from pathlib import Path
import argparse,subprocess,shutil,hashlib,json
H=Path(__file__).resolve().parent;R=H.parent/'rf';P='/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9';CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
a=argparse.ArgumentParser();a.add_argument('--source',type=Path,required=True);a.add_argument('--output',type=Path,required=True);args=a.parse_args();source=args.source.resolve();out=args.output.resolve();assert '/ai-working/' in str(out) and not out.exists()
assert hashlib.sha256((source/'stratolink.kicad_pcb').read_bytes()).hexdigest()=='af8b32d61756642c1f63b12c7220c10bc17c62dec1fed5c53bf5796f92ab08ec'
shutil.copytree(source,out,symlinks=False);pcb=out/'stratolink.kicad_pcb';steps=[]
def run(script):
 with (out/(script.stem+'.log')).open('w')as log:subprocess.run([P,str(script),str(pcb)],check=True,stdout=log,stderr=subprocess.STDOUT)
 steps.append({'script':str(script),'pcb_sha256':hashlib.sha256(pcb.read_bytes()).hexdigest()})
def drc(name):
 report=out/(name+'-drc.json')
 with (out/(name+'-drc.log')).open('w')as log:subprocess.run([CLI,'pcb','drc','--refill-zones','--save-board','--schematic-parity','--severity-all','--format','json','-o',str(report),str(pcb)],check=True,stdout=log,stderr=subprocess.STDOUT)
 j=json.loads(report.read_text());assert not any(j[k] for k in ['violations','unconnected_items','schematic_parity']),j
run(H/'rf_round_routes.py');drc('rounded')
run(R/'apply_front_guard.py');drc('guard')
run(H/'fix_rf_library_metadata.py')
shutil.copy2(H/'rf-final/rf-fillet-plan.json',out/'rf-fillet-plan.json');run(H/'apply_rf_fillets.py');drc('fillets')
run(H/'fix_rf_seam.py');drc('final')
expected=json.loads((H/'rf-final/manifest.json').read_text())['files'];actual={k:hashlib.sha256((out/k).read_bytes()).hexdigest()for k in expected};assert actual==expected,(actual,expected)
report={'status':'PASS','source_pcb_sha256':'af8b32d61756642c1f63b12c7220c10bc17c62dec1fed5c53bf5796f92ab08ec','files':actual,'steps':steps};(H/'rf-final/reproduction.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
