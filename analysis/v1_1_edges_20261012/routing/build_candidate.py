#!/usr/bin/env python3
"""Reproduce the bounded edge-routing candidate from Git; never write canonical CAD."""
from pathlib import Path
import subprocess, json, re, hashlib, uuid, shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = 'd70a53d'
SCRATCH = Path.home() / 'Repositories/ai-working/scratch/stratolink-edges-20261012/routing'
CLI = '/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'

# Width, layer, net and UUID remain fixed. Diagonals remain 45 degrees.
CHANGES = {
 '18c9a067-24a5-4625-8e36-1a2ab661e9bc': ((53.73,64.947713),(53.73,62.842332)),
 '2727baf4-a20e-4dc4-8d56-2cae36ad27a0': ((53.73,62.842332),(55.961085,60.611247)),
 'a2cfd543-5b76-494b-9bcc-1e523f422c16': ((53.73,65.049963),(53.73,64.947713)),
 # Shorten only the upper tip of this existing long trace to permit the transition.
 'c1227579-013e-4ffa-b72b-869589a0d2ea': ((53.683171,76.828171),(53.683171,65.096792)),
 'bfbfa6f4-1dbe-4095-a771-3fb9a012fb75': ((75.187,67.249),(76.299,68.361)),
 '1e1073b6-2c7c-4ad4-a31b-c180809f6da6': ((76.299,68.361),(76.299,69.723097)),
 'cd6977b0-9d88-4014-8ee0-75e9feff1d59': ((76.299,69.723097),(75.864097,70.158)),
 'a379a696-fdc3-4f66-808c-ae939631c307': ((53.675,68.584999),(54.111648,68.148353)),
 '91c5ca5e-308e-4f8b-8d63-7c761c4637bd': ((53.675,70.581084),(53.675,68.584999)),
 '91541222-310a-48bc-b525-2eec1e0cb20f': ((54.267917,71.174001),(53.675,70.581084)),
}
ADDED_UUID = str(uuid.uuid5(uuid.NAMESPACE_URL, 'stratolink-v1.1-edge-solar-transition-20261012'))

def top_blocks(text, kind):
 stack=[]; quoted=False; escape=False; out=[]
 for i,c in enumerate(text):
  if quoted:
   if escape: escape=False
   elif c=='\\': escape=True
   elif c=='"': quoted=False
  elif c=='"': quoted=True
  elif c=='(': stack.append(i)
  elif c==')':
   start=stack.pop()
   if len(stack)==1 and text[start:].startswith('('+kind+'\n'): out.append((start,i+1,text[start:i+1]))
 return out

def git(path):
 return subprocess.check_output(['git','show',f'{BASE}:hardware/pcb/{path}'],cwd=ROOT)

def main():
 canonical=ROOT/'hardware/pcb/stratolink.kicad_pcb'; before=canonical.read_bytes()
 source=git('stratolink.kicad_pcb').decode(); candidate=source; changed=[]
 for start,end,block in reversed(top_blocks(source,'segment')):
  uid=re.search(r'\(uuid "([^"]+)"\)',block).group(1)
  if uid not in CHANGES: continue
  new=block
  for name,xy in zip(['start','end'],CHANGES[uid]):
   new,n=re.subn(r'\('+name+r' [^)]*\)',f'({name} {xy[0]:.6f} {xy[1]:.6f})',new,count=1); assert n==1
  candidate=candidate[:start]+new+candidate[end:]; changed.append(uid)
 assert set(changed)==set(CHANGES)
 extra=f'''\n\t(segment
\t\t(start 53.73 65.049963)
\t\t(end 53.683171 65.096792)
\t\t(width 0.25)
\t\t(layer "F.Cu")
\t\t(net "+SOLAR")
\t\t(uuid "{ADDED_UUID}")
\t)\n'''
 candidate=candidate.rstrip()[:-1]+extra+')\n'
 paths=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE,'--','hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
 results={}
 for variant,board in [('baseline',source),('candidate',candidate)]:
  out=SCRATCH/variant; out.mkdir(parents=True,exist_ok=True)
  for name in ['stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']: (out/name).write_bytes(git(name))
  for p in paths:
   dest=out/Path(p).relative_to('hardware/pcb');dest.parent.mkdir(parents=True,exist_ok=True)
   dest.write_bytes(subprocess.check_output(['git','show',f'{BASE}:{p}'],cwd=ROOT))
  path=out/'stratolink.kicad_pcb';path.write_text(board)
  cmd=[CLI,'pcb','drc','--schematic-parity','--format','json','--output',str(HERE/f'{variant}-drc-project.json')]
  if variant=='candidate':cmd+=['--refill-zones','--save-board']
  run=subprocess.run(cmd+[str(path)],check=True,capture_output=True,text=True)
  (out/'drc-project.log').write_text(run.stdout+run.stderr)
  results[variant]={'path':str(path),'pcb_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
 assert canonical.read_bytes()==before
 report=dict(baseline_commit=BASE,variants=results,changed_segment_uuids=sorted(CHANGES),added_segment_uuids=[ADDED_UUID])
 (HERE/'build.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__': main()
