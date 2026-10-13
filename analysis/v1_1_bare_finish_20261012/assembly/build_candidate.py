#!/usr/bin/env python3
"""Straight-wire antenna documentation correction; frozen scratch CAD only."""
from pathlib import Path
import importlib.util,json,re,subprocess,uuid
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];BASE='41027a4'
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-bare-finish-20261012/assembly/wire-candidate'
spec=importlib.util.spec_from_file_location('prior',ROOT/'analysis/v1_1_ground_20261012/build_candidate.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
a=prior.cad;SOURCE='https://stratolink.org/docs/hardware#antennas-and-suspension'
PARTS={
 'AE1':dict(lib='Stratolink_LoRa_Wire_PTH_D1p0',length=82,courtyard_length=87,value='Enameled Cu wire 82mm (915MHz reference)',description='Hand-formed enamelled copper wire; 82 mm from feed for 915 MHz, 83 mm compromise or 86 mm for 868 MHz; diameter not yet measured'),
 'AE2':dict(lib='Stratolink_GNSS_Wire_PTH_D1p0',length=48,courtyard_length=49,value='Enameled Cu wire 48mm (GNSS L1)',description='Hand-formed enamelled copper wire; 48 mm from feed for GNSS L1; diameter not yet measured')}
for ref,p in PARTS.items():
 p['model']='Stratolink_Wire_%dmm_D0p321_Nominal.step'%p['length']
 p['points']=[[-1.25,-1.25],[p['courtyard_length'],-1.25],[p['courtyard_length'],1.25],[-1.25,1.25]]
def uid(ref,kind,i):return str(uuid.uuid5(uuid.NAMESPACE_URL,'stratolink-v1.1-'+ref+'-'+kind+'-'+str(i)))
def graphics(ref):
 p=PARTS[ref];pts=p['points'];lines=[]
 for i,x in enumerate(pts):lines.append('\t(fp_line (start %s %s) (end %s %s) (stroke (width 0.05) (type solid)) (layer "F.CrtYd") (uuid "%s"))'%(*x,*pts[(i+1)%len(pts)],uid(ref,'courtyard',i)))
 lines.append('\t(fp_line (start 0 0) (end %s 0) (stroke (width 0.321) (type solid)) (layer "F.Fab") (uuid "%s"))'%(p['length'],uid(ref,'wire-fab',0)))
 return '\n'.join(lines)
def properties(text,ref):
 p=PARTS[ref];changes=[]
 replacements={'Value':p['value'],'Datasheet':SOURCE,'Description':p['description'],'Footprint':'lib:'+p['lib']}
 for s,e,d in prior.spans(text):
  if d!=1:continue
  n=a.parse(text[s:e])
  if n[0]=='property' and n[1] in replacements:
   old='(property '+json.dumps(n[1])+' '+json.dumps(n[2]);new='(property '+json.dumps(n[1])+' '+json.dumps(replacements[n[1]])
   assert old in text[s:e];changes.append((s,e,text[s:e].replace(old,new,1)))
 return prior.replace(text,changes)
def adjust_fp(text,ref):
 p=PARTS[ref];edits=[]
 for s,e,d in prior.spans(text):
  if d!=1:continue
  n=a.parse(text[s:e])
  if n[0]=='fp_line' and a.scalar(n,'layer') in {'F.CrtYd','F.Fab'}:edits.append((s,e,''))
  elif n[0]=='descr':edits.append((s,e,'(descr '+json.dumps(p['description'])+')'))
  elif n[0]=='model':
   assert n[1]=='${KIPRJMOD}/lib/gps.step';edits.append((s,e,text[s:e].replace('${KIPRJMOD}/lib/gps.step','${KIPRJMOD}/lib/'+p['model'],1)))
 assert len(edits)==11,(ref,len(edits))
 text=prior.replace(text,edits).replace('(footprint "lib:4269"','(footprint "lib:'+p['lib']+'"',1)
 text=properties(text,ref)
 return text[:-1]+'\n'+graphics(ref)+'\n)'
def library_from_placed(text,ref):
 p=PARTS[ref];changes=[]
 for s,e,d in prior.spans(text):
  if d!=1:continue
  n=a.parse(text[s:e])
  if n[0] in {'at','uuid','path','sheetname','sheetfile'}:changes.append((s,e,''))
  elif n[0]=='pad':
   pt=text[s:e];rem=[]
   for ps,pe,pd in prior.spans(pt):
    if pd!=1:continue
    pn=a.parse(pt[ps:pe])
    if pn[0] in {'net','pinfunction','pintype'}:rem.append((ps,pe,''))
    elif pn[0]=='at':rem.append((ps,pe,'(at 0 0)'))
   changes.append((s,e,prior.replace(pt,rem)))
  elif n[0]=='property' and n[1]=='Reference':changes.append((s,e,text[s:e].replace('"'+ref+'"','"AE**"',1)))
 text=prior.replace(text,changes).replace('"lib:'+p['lib']+'"','"'+p['lib']+'"',1)
 return text.replace('(layer "F.Cu")','(version 20260101) (generator "pcbnew") (generator_version "10.0")\n\t(layer "F.Cu")',1)+'\n'
def main():
 protected={p:prior.sha(p) for p in (ROOT/'hardware/pcb').glob('stratolink.kicad_*') if p.suffix in {'.kicad_pcb','.kicad_sch','.kicad_pro'}}
 names=['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']
 libs=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE+':hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
 for n in names+['lib/'+n for n in libs]:
  p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True);assert not p.is_symlink();p.write_bytes(subprocess.check_output(['git','show',BASE+':hardware/pcb/'+n],cwd=ROOT))
 p=OUT/'stratolink.kicad_pcb';text=p.read_text();changes=[];newlibs=[]
 for s,e,d in prior.spans(text):
  if d!=1:continue
  n=a.parse(text[s:e]);ref=a.prop(n,'Reference') if n[0]=='footprint' else None
  if ref in PARTS:
   adjusted=adjust_fp(text[s:e],ref);changes.append((s,e,adjusted));part=PARTS[ref]
   lib='lib/'+part['lib']+'.kicad_mod';(OUT/lib).write_text(library_from_placed(adjusted,ref));newlibs.append(lib)
   # Existing analytic STEP is a 45.6 mm straight cylinder plus its 2 mm bend.
   # Only the five plane/vertex axial tip coordinates change; all diameters/bend geometry stay fixed.
   model=(OUT/'lib/gps.step').read_text();assert model.count('0.0456')==5
   model=model.replace('0.0456',format(part['length']/1000,'.4f'))
   model=model.replace("FILE_NAME('dump.step'", "FILE_NAME('"+part['model']+"'")
   dest='lib/'+part['model'];(OUT/dest).write_text(model);newlibs.append(dest)
 assert len(changes)==2;p.write_text(prior.replace(text,changes))
 p=OUT/'stratolink.kicad_sch';text=p.read_text();changes=[]
 for s,e,d in prior.spans(text):
  if d!=1:continue
  n=a.parse(text[s:e]);ref=a.prop(n,'Reference') if n[0]=='symbol' else None
  if ref in PARTS:changes.append((s,e,properties(text[s:e],ref)))
 assert len(changes)==2;p.write_text(prior.replace(text,changes))
 assert all(prior.sha(p)==sha for p,sha in protected.items())
 report=dict(baseline=subprocess.check_output(['git','rev-parse',BASE],cwd=ROOT,text=True).strip(),candidate=str(OUT),parts=PARTS,source=SOURCE,nominal_model_diameter_mm=.321,nominal_model_insertion_leg_mm=2,new_library_files=newlibs,files={n:prior.sha(OUT/n) for n in names+newlibs})
 (HERE/'candidate.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
