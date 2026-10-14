#!/usr/bin/env python3
"""Reproduce the frozen cleanup from the published git object, in fresh scratch."""
from pathlib import Path
import subprocess,tarfile,io,json,hashlib,shutil,sys
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
KPY='/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
p=Path(sys.argv[1]).expanduser().resolve();assert '/ai-working/scratch/' in str(p) and not p.exists();p.mkdir(parents=True)
commit='e6f5200208cf433aa2baf0dcad80d9d9ef26cd25'
raw=subprocess.check_output(['git','archive',commit,'hardware/pcb'],cwd=ROOT)
with tarfile.open(fileobj=io.BytesIO(raw)) as tf:
 for member in tf.getmembers():
  if not member.isfile():continue
  rel=Path(member.name).relative_to('hardware/pcb');assert '..' not in rel.parts
  dst=p/rel;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(tf.extractfile(member).read())
pro=p/'stratolink.kicad_pro';j=json.loads(pro.read_text());settings=j['board']['design_settings'];settings['rules']['min_groove_width']=.10;settings['rules']['min_connection']=.10
for name in ['connection_width','copper_sliver']:settings['rule_severities'][name]='error'
pro.write_text(json.dumps(j,indent=2)+'\n')
def run(*cmd):subprocess.run([str(x) for x in cmd],check=True,cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def drc():run(CLI,'pcb','drc','--refill-zones','--save-board','--schematic-parity','--severity-all','--format','json','-o',p/'drc.json',p/'stratolink.kicad_pcb')
run(KPY,HERE/'fix_copper.py',p/'stratolink.kicad_pcb');drc()
for name in ['fillet-plan.json','logo-hole.json']:shutil.copyfile(HERE/'candidate'/name,p/name)
run(KPY,HERE/'apply_fillets.py',p/'stratolink.kicad_pcb');run(KPY,HERE/'convert_text_and_seam.py',p/'stratolink.kicad_pcb');drc()
d=json.loads((p/'drc.json').read_text());assert not any(d[k] for k in ['violations','unconnected_items','schematic_parity'])
actual=hashlib.sha256((p/'stratolink.kicad_pcb').read_bytes()).hexdigest();expected=json.loads((HERE/'candidate/manifest.json').read_text())['candidate_pcb_sha256'];assert actual==expected,(actual,expected)
print(json.dumps({'status':'PASS','pcb_sha256':actual,'path':str(p)},indent=2))
