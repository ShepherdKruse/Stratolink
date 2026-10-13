#!/usr/bin/env python3
"""Ground-zone-only scratch variants; canonical project is never written."""
from pathlib import Path
import subprocess,json,re,hashlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
BASE='c3d70a4'
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-zones-20261012/zone'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
MAIN='795c4093-4930-4bcb-9c07-8e31d04084fe';BACK='e9b71a22-0a8a-41f9-b5c4-115945b7ef58'
def git(p):return subprocess.check_output(['git','show',f'{BASE}:hardware/pcb/{p}'],cwd=ROOT)
def zones(text):
 stack=[];quoted=False;escape=False;out=[]
 for i,c in enumerate(text):
  if quoted:
   if escape:escape=False
   elif c=='\\':escape=True
   elif c=='"':quoted=False
  elif c=='"':quoted=True
  elif c=='(':stack.append(i)
  elif c==')':
   start=stack.pop()
   if len(stack)==1 and text[start:start+5]=='(zone':out.append((start,i+1,text[start:i+1]))
 return out
canonical=ROOT/'hardware/pcb/stratolink.kicad_pcb';before=canonical.read_bytes()
source=git('stratolink.kicad_pcb').decode()
paths=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE,'--','hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
report={'baseline_commit':BASE,'baseline_pcb_sha256':hashlib.sha256(source.encode()).hexdigest(),'variants':{}}
for variant in ['baseline','front-only-main','single-two-layer']:
 out=SCRATCH/variant;out.mkdir(parents=True,exist_ok=True)
 for file in ['stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:(out/file).write_bytes(git(file))
 for p in paths:
  dest=out/Path(p).relative_to('hardware/pcb');dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(subprocess.check_output(['git','show',f'{BASE}:{p}'],cwd=ROOT))
 board=source
 for start,end,z in reversed(zones(source)):
  if variant=='front-only-main' and MAIN in z:
   replacement,count=re.subn(r'\(layers\s+"F.Cu"\s+"B.Cu"\)','(layer "F.Cu")',z,count=1)
   assert count==1;board=board[:start]+replacement+board[end:]
  if variant=='single-two-layer' and BACK in z:board=board[:start]+board[end:]
 (out/'stratolink.kicad_pcb').write_text(board)
 output=HERE/f'{variant}-drc-project.json'
 cmd=[CLI,'pcb','drc','--schematic-parity','--format','json','--output',str(output)]
 if variant!='baseline':cmd+=['--refill-zones','--save-board']
 cmd+=[str(out/'stratolink.kicad_pcb')]
 run=subprocess.run(cmd,check=True,capture_output=True,text=True)
 (out/'drc.log').write_text(run.stdout+run.stderr)
 r=json.loads(output.read_text())
 report['variants'][variant]=dict(path=str(out),pcb_sha256=hashlib.sha256((out/'stratolink.kicad_pcb').read_bytes()).hexdigest(),project_counts={k:len(r[k]) for k in ['violations','unconnected_items','schematic_parity']})
assert canonical.read_bytes()==before
(HERE/'build.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
