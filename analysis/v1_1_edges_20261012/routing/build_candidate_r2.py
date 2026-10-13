#!/usr/bin/env python3
"""Revise two header-adjacent routes in a copy of the frozen combined candidate."""
from pathlib import Path
import subprocess,shutil,json,re,hashlib
from build_candidate import HERE,ROOT,SCRATCH,CLI,CHANGES,ADDED_UUID,top_blocks

SOURCE=SCRATCH.parent/'combined'
OUTPUT=SCRATCH/'candidate-r2'
EVIDENCE=HERE/'r2'
R2_CHANGES=dict(CHANGES)
R2_CHANGES.update({
 'c1227579-013e-4ffa-b72b-869589a0d2ea':((53.675,76.82),(53.675,65.104963)),
 'e9b21ab4-de4f-4bb7-a599-94cd191c0bc8':((54.301,77.446),(53.675,76.82)),
 '1e1073b6-2c7c-4ad4-a31b-c180809f6da6':((76.299,68.361),(76.299,69.75)),
 'cd6977b0-9d88-4014-8ee0-75e9feff1d59':((76.299,69.75),(75.891,70.158)),
 'b6acae82-f692-4c92-8407-867053d1eac9':((75.891,70.158),(75.531,70.158)),
})
R2_ADDED={ADDED_UUID:((53.73,65.049963),(53.675,65.104963))}

def main():
 EVIDENCE.mkdir(exist_ok=True);OUTPUT.mkdir(parents=True,exist_ok=True)
 canonical=(ROOT/'hardware/pcb/stratolink.kicad_pcb').read_bytes()
 raw=(SOURCE/'stratolink.kicad_pcb').read_bytes();source=raw.decode();candidate=source
 source_hash=hashlib.sha256(raw).hexdigest();assert source_hash.startswith('804094fb'),source_hash
 modified=[];all_edits={**R2_CHANGES,**R2_ADDED}
 for start,end,block in reversed(top_blocks(source,'segment')):
  uid=re.search(r'\(uuid "([^"]+)"\)',block).group(1)
  if uid not in all_edits:continue
  new=block
  for name,xy in zip(['start','end'],all_edits[uid]):
   new,n=re.subn(r'\('+name+r' [^)]*\)',f'({name} {xy[0]:.6f} {xy[1]:.6f})',new,count=1);assert n==1
  candidate=candidate[:start]+new+candidate[end:];modified.append(uid)
 assert set(modified)==set(all_edits)
 for name in ['stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:shutil.copy2(SOURCE/name,OUTPUT/name)
 shutil.copytree(SOURCE/'lib',OUTPUT/'lib',dirs_exist_ok=True)
 path=OUTPUT/'stratolink.kicad_pcb';path.write_text(candidate)
 run=subprocess.run([CLI,'pcb','drc','--refill-zones','--save-board','--schematic-parity','--format','json','--output',str(EVIDENCE/'candidate-r2-drc-project.json'),str(path)],check=True,capture_output=True,text=True)
 (OUTPUT/'drc-project.log').write_text(run.stdout+run.stderr)
 assert (SOURCE/'stratolink.kicad_pcb').read_bytes()==raw
 assert (ROOT/'hardware/pcb/stratolink.kicad_pcb').read_bytes()==canonical
 manifest=dict(baseline_commit='d70a53d',frozen_combined_source=str(SOURCE/'stratolink.kicad_pcb'),frozen_combined_sha256=source_hash,
  candidate=str(path),candidate_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
  route_only_patch_vs_d70a53d=dict(modified_segment_uuids=sorted(R2_CHANGES),added_segment_uuids=sorted(R2_ADDED),
   segment_coordinates_mm={k:{'start':v[0],'end':v[1]} for k,v in all_edits.items()}))
 (EVIDENCE/'build.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
