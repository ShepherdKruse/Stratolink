#!/usr/bin/env python3
"""Native scratch-only thermal experiments, with fixed source checkpoint."""
from pathlib import Path
import json,sys,subprocess,hashlib

H=Path(__file__).resolve().parent;ROOT=H.parents[2];BASE='c3d70a429a95591607341d57bf16ee153972da71';S=Path.home()/'Repositories/ai-working/scratch/stratolink-zones-20261012/thermal';S.mkdir(parents=True,exist_ok=True)
trials=[
 dict(name='u7_g150_w250_a90',gap=.15,width=.25,angle=90,jgap=.5,jwidth=.5,jangle=45),
 dict(name='u7_g200_w250_a90',gap=.20,width=.25,angle=90,jgap=.5,jwidth=.5,jangle=45),
 dict(name='u7_g250_w250_a90',gap=.25,width=.25,angle=90,jgap=.5,jwidth=.5,jangle=45),
 dict(name='u7_g150_w250_a45',gap=.15,width=.25,angle=45,jgap=.5,jwidth=.5,jangle=45),
 dict(name='u7_g200_w250_a45',gap=.20,width=.25,angle=45,jgap=.5,jwidth=.5,jangle=45),
 dict(name='u7_g250_w250_a45',gap=.25,width=.25,angle=45,jgap=.5,jwidth=.5,jangle=45),
 dict(name='j20_g500_w500_a0',gap=.20,width=.25,angle=90,jgap=.5,jwidth=.5,jangle=0),
 dict(name='j20_g250_w250_a0',gap=.20,width=.25,angle=90,jgap=.25,jwidth=.25,jangle=0),
 dict(name='j20_g250_w250_a45',gap=.20,width=.25,angle=90,jgap=.25,jwidth=.25,jangle=45),
 dict(name='j20_g300_w250_a0',gap=.20,width=.25,angle=90,jgap=.3,jwidth=.25,jangle=0),
 dict(name='j20_direct',gap=.20,width=.25,angle=90,jdirect=True),
 dict(name='mixed_g150_w250_j20angle',gap=.15,width=.25,angle=90,angle5=45,jangle_only=0),
 dict(name='mixed_g200_w250_j20angle',gap=.20,width=.25,angle=90,angle5=45,jangle_only=0),
 dict(name='mixed_g250_w250_j20angle',gap=.25,width=.25,angle=90,angle5=45,jangle_only=0),
 dict(name='mixed_g200_w250_j20direct',gap=.20,width=.25,angle=90,angle5=45,jdirect=True),
]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/layout'));import cad_helpers as a
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
def rewrite(t,repls):
 for s,e,v in sorted(repls,reverse=True):t=t[:s]+v+t[e:]
 return t

if '--mixed-only' in sys.argv:trials=[t for t in trials if t['name'].startswith('mixed_')]
for trial in trials:
 out=S/trial['name'];out.mkdir(exist_ok=True)
 for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:(out/name).write_bytes(subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT))
 for name in ['lib','3d']:
  if not (out/name).exists():(out/name).symlink_to(ROOT/'hardware/pcb'/name)
 text=(out/'stratolink.kicad_pcb').read_text();fps=[]
 for st,en,depth in spans(text):
  if depth!=1:continue
  fptext=text[st:en];f=a.parse(fptext)
  if f[0]!='footprint' or a.prop(f,'Reference') not in ['U7','J20']:continue
  ref=a.prop(f,'Reference');pads=[]
  for ps,pe,pd in spans(fptext):
   if pd!=1:continue
   p=a.parse(fptext[ps:pe])
   if p[0]!='pad':continue
   if ref=='U7' and p[1] in ['5','8']:
    fields=f"(thermal_gap {trial['gap']}) (thermal_bridge_width {trial['width']}) (thermal_bridge_angle {trial.get('angle5',trial['angle']) if p[1]=='5' else trial['angle']})"
   elif ref=='J20' and p[1]=='5':
    fields=f"(thermal_bridge_angle {trial['jangle_only']})" if 'jangle_only' in trial else '(zone_connect 2)' if trial.get('jdirect') else f"(thermal_gap {trial['jgap']}) (thermal_bridge_width {trial['jwidth']}) (thermal_bridge_angle {trial['jangle']})"
   else:continue
   pads.append((ps,pe,fptext[ps:pe].rstrip()[:-1]+' '+fields+')'))
  fps.append((st,en,rewrite(fptext,pads)))
 (out/'stratolink.kicad_pcb').write_text(rewrite(text,fps))
 trial['directory']=str(out)
(H/('mixed-trials.json' if '--mixed-only' in sys.argv else 'trials.json')).write_text(json.dumps(dict(baseline=BASE,trials=trials),indent=2)+'\n');print(len(trials),'scratch variants created')
