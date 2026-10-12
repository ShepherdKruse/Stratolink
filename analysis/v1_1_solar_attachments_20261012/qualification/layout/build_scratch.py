#!/usr/bin/env python3
"""Build deeper bank-only solar lands in scratch; never write canonical CAD."""
from pathlib import Path
import re,json,uuid,subprocess,sys,hashlib
H=Path(__file__).resolve().parent;ROOT=H.parents[3]
sys.path.insert(0,str(H.parents[1]/'layout'));import cad_helpers as a
BASE='76ee6e87463b70519769750d6795988b2c202683'
UPPER_ONLY='--upper-only' in sys.argv
OUT=Path.home()/('Repositories/ai-working/scratch/stratolink-solar-depth2/upper-only' if UPPER_ONLY else 'Repositories/ai-working/scratch/stratolink-solar-depth2/candidate');OUT.mkdir(parents=True,exist_ok=True);(OUT/'lib').mkdir(exist_ok=True)
canon=ROOT/'hardware/pcb';before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [canon/'stratolink.kicad_pcb',canon/'lib/Solar_Notch_Left_1p0x1p5.kicad_mod',canon/'lib/Solar_Notch_Right_1p0x1p5.kicad_mod']}
def blob(path):return subprocess.check_output(['git','show',BASE+':hardware/pcb/'+path],cwd=ROOT)
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

def tops(t):return [(s,e,a.parse(t[s:e])) for s,e,d in spans(t) if d==1]
def rewrite(t,replacements):
 for s,e,v in sorted(replacements,reverse=True):t=t[:s]+v+t[e:]
 return t

def newpads(text,side,board):
 sgn=1 if side=='Left' else -1; repl=[]
 for s,e,n in tops(text):
  if n[0]!='pad' or n[1]!='2':continue
  layer=a.one(n,'layers')[0]; prefix=layer.split('.')[0]; rows=[]
  for idx,y in enumerate([-1.06] if UPPER_ONLY else [-1.06,1.06]):
   uid=a.scalar(n,'uuid') if idx==0 else str(uuid.uuid4())
   rows.append(f'(pad "2" smd rect (at {sgn*1.25} {y}) (size 2.1 .68) (layers "{prefix}.Cu" "{prefix}.Mask") '+('(net "GND") ' if board else '')+f'(pintype "passive") (zone_connect 2) (uuid "{uid}"))')
  repl.append((s,e,'\n'.join(rows)))
 result=rewrite(text,repl)
 result=result.replace('Manual solar panel ground notch lands, separate lower positive wire pad; unplated edge notch in board outline', 'Manual solar panel: 1.0 x 2.0 mm unplated notch, upper-bank GND lands on both faces, lower positive wire pad' if UPPER_ONLY else 'Manual solar panel: 1.0 x 2.0 mm unplated notch, separate upper/lower GND banks on both faces, lower positive wire pad')
 if UPPER_ONLY:result=result.replace('_1p0x1p5','_1p0x2p0')
 return result
for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:
 data=blob(name)
 if UPPER_ONLY and name=='stratolink.kicad_sch':data=data.replace(b'_1p0x1p5',b'_1p0x2p0')
 (OUT/name).write_bytes(data)
for p in (canon/'lib').iterdir():
 dst=OUT/'lib'/(p.name.replace('_1p0x1p5','_1p0x2p0') if UPPER_ONLY else p.name)
 if p.name in ['Solar_Notch_Left_1p0x1p5.kicad_mod','Solar_Notch_Right_1p0x1p5.kicad_mod']:
  if dst.is_symlink():dst.unlink()
  side='Left' if 'Left' in p.name else 'Right';dst.write_text(newpads(blob('lib/'+p.name).decode(),side,False))
 elif not dst.exists():dst.symlink_to(p)
if not (OUT/'3d').exists():(OUT/'3d').symlink_to(canon/'3d')
b=(OUT/'stratolink.kicad_pcb').read_text();repl=[];count=0
for s,e,n in tops(b):
 if UPPER_ONLY and n[0]=='via' and a.scalar(n,'net')=='GND' and a.floats(n,'at') in [[54.1665,55.55],[75.8255,55.55]]:
  repl.append((s,e,''))
 elif n[0]=='footprint' and a.prop(n,'Reference') in ['J1','J2']:
  side='Left' if a.prop(n,'Reference')=='J2' else 'Right';repl.append((s,e,newpads(b[s:e],side,True)))
 elif n[0] in ['gr_line','gr_arc'] and a.scalar(n,'layer')=='Edge.Cuts':
  fields={k:a.floats(n,k) for k in ['start','end','mid']};start,end=fields['start'],fields['end']
  if not start or not end or not all(54<=p[1]<=55 for p in [start,end]):continue
  if not any(abs(p[1]-54)<1e-6 or abs(p[1]-55)<1e-6 for p in [start,end]):continue
  isleft=sum(p[0] for p in [start,end])/2<65;edge=53.3165 if isleft else 76.6755;sign=1 if isleft else -1
  text=b[s:e]
  for k,p in fields.items():
   if p and abs(p[0]-edge)>.01:
    p[0]+=sign*.5;text=re.sub(r'\('+k+r'\s+[-\d.]+\s+[-\d.]+\)',f'({k} {p[0]:.6f} {p[1]:.6f})',text,count=1)
  if text!=b[s:e]:repl.append((s,e,text));count+=1
assert count==6,count
(OUT/'stratolink.kicad_pcb').write_text(rewrite(b,repl))
assert {p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}==before
(H/('upper-only-build.json' if UPPER_ONLY else 'rejected-split-banks-build.json')).write_text(json.dumps(dict(baseline=BASE,output=str(OUT),canonical_hashes_unchanged=before,edge_objects_changed=count,routes_changed=0,component_placements_changed=0,note='Upper-only variant renames footprints and schematic coherently to 1p0x2p0; both-bank rejected trial temporarily retains old names.'),indent=2)+'\n')
print(OUT)
