#!/usr/bin/env python3
"""U7-only mask repair in scratch, pinned to Git a9d6ed5. No canonical writes."""
from pathlib import Path
import hashlib,subprocess,re,json,sys
H=Path(__file__).resolve().parent;ROOT=H.parents[2]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/layout'));import cad_helpers as a
BASE='a9d6ed59ebd9ca6a4e04108afe0bbe3a827cddde';OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-u7-mask/candidate';OUT.mkdir(parents=True,exist_ok=True);(OUT/'lib').mkdir(exist_ok=True)
def blob(p):return subprocess.check_output(['git','show',BASE+':hardware/pcb/'+p],cwd=ROOT)
def spans(t):
 stack=[];q=False;esc=False;out=[]
 for i,c in enumerate(t):
  if q:
   if esc:esc=False
   elif c=='\\':esc=True
   elif c=='"':q=False
  elif c=='"':q=True
  elif c=='(':stack.append(i)
  elif c==')':out.append((stack.pop(),i+1,len(stack)))
 return out
for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:(OUT/name).write_bytes(blob(name))
for p in (ROOT/'hardware/pcb/lib').iterdir():
 dst=OUT/'lib'/p.name
 if p.name=='PQFN50P200X200100-12N.kicad_mod':
  if dst.is_symlink():dst.unlink()
  lib=blob('lib/'+p.name).decode();assert lib.count('(solder_mask_margin 0.102)')==12;dst.write_text(lib.replace('(solder_mask_margin 0.102)','(solder_mask_margin 0)'))
 elif not dst.exists():dst.symlink_to(p)
if not (OUT/'3d').exists():(OUT/'3d').symlink_to(ROOT/'hardware/pcb/3d')
b=(OUT/'stratolink.kicad_pcb').read_text();edited=0
for s,e,dep in spans(b):
 if dep!=1:continue
 obj=a.parse(b[s:e])
 if obj[0]=='footprint' and a.prop(obj,'Reference')=='U7':
  sub=b[s:e];assert sub.count('(solder_mask_margin 0.102)')==12
  b=b[:s]+sub.replace('(solder_mask_margin 0.102)','(solder_mask_margin 0)')+b[e:];edited+=1;break
assert edited==1;(OUT/'stratolink.kicad_pcb').write_text(b)
(H/'scratch-build.json').write_text(json.dumps(dict(baseline=BASE,scratch=str(OUT),changed='Explicit U7 pad solder_mask_margin 0.102 -> 0; twelve pads, no other PCB changes. Native reusable-library reconciliation follows.'),indent=2)+'\n')
print(OUT)
