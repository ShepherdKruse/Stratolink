#!/usr/bin/env python3
"""Scoped header annulus experiments in scratch only; no global library refresh."""
from pathlib import Path
import subprocess,sys,json,hashlib
import pcbnew,wx
H=Path(__file__).resolve().parent;ROOT=H.parents[2];BASE='d70a53d2093454084c9b1ae989d0276a88395334';S=Path.home()/'Repositories/ai-working/scratch/stratolink-edges-20261012/rings';CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/layout'));import cad_helpers as a
helper=(ROOT/'analysis/v1_1_ground_20261012/thermals/build_trials.py').read_text();exec(helper[helper.index('def spans'):helper.index("if '--mixed-only'")])
def git(n):return subprocess.check_output(['git','show',BASE+':hardware/pcb/'+n],cwd=ROOT)
libs=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE+':hardware/pcb/lib'],cwd=ROOT,text=True).splitlines();app=wx.App(False);results=[]
for dia in [.88]:
 label=f'pad{dia:.2f}'.replace('.','p');out=S/label;out.mkdir(parents=True,exist_ok=True)
 for n in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']+['lib/'+l for l in libs]:
  p=out/n;p.parent.mkdir(parents=True,exist_ok=True);assert not p.is_symlink();p.write_bytes(git(n))
 libnames={ref:'Stratolink_Header_'+side+'_1x07_P1p00_D0p50_Pad'+f'{dia:.2f}'.replace('.','p') for ref,side in [('J3','Left'),('J4','Right')]}
 text=(out/'stratolink.kicad_pcb').read_text();changes=[]
 for s,e,d in spans(text):
  if d!=1:continue
  chunk=text[s:e];f=a.parse(chunk)
  if f[0]!='footprint' or a.prop(f,'Reference') not in ['J3','J4']:continue
  libname=libnames[a.prop(f,'Reference')];fpname='lib:'+libname
  pads=[]
  for ps,pe,pd in spans(chunk):
   if pd!=1:continue
   p=a.parse(chunk[ps:pe])
   if p[0]!='pad':continue
   assert a.one(p,'size')==['0.85','0.85'] and a.one(p,'drill')==['0.5']
   old=chunk[ps:pe];assert old.count('(size 0.85 0.85)')==1
   pads.append((ps,pe,old.replace('(size 0.85 0.85)',f'(size {dia} {dia})')))
  assert len(pads)==7;new=rewrite(chunk,pads);new=new.replace('"'+f[1]+'"','"'+fpname+'"',1);changes.append((s,e,new))
 assert len(changes)==2;(out/'stratolink.kicad_pcb').write_text(rewrite(text,changes))
 text=(out/'stratolink.kicad_sch').read_text();changes=[]
 for s,e,d in spans(text):
  if d!=1:continue
  ch=text[s:e];f=a.parse(ch)
  if f[0]!='symbol' or a.prop(f,'Reference') not in ['J3','J4']:continue
  fpname='lib:'+libnames[a.prop(f,'Reference')];prev=a.prop(f,'Footprint');assert prev=='Connector_PinHeader_1.00mm:PinHeader_1x07_P1.00mm_Vertical';ch=ch.replace('"'+prev+'"','"'+fpname+'"');changes.append((s,e,ch))
 assert len(changes)==2;(out/'stratolink.kicad_sch').write_text(rewrite(text,changes))
 # Derive library from the placed geometry, not a newly installed stock footprint.
 b=pcbnew.LoadBoard(str(out/'stratolink.kicad_pcb'))
 for ref,libname in libnames.items():
  f=next(f for f in b.GetFootprints() if f.GetReference()==ref);clone=pcbnew.FOOTPRINT(f);clone.SetPosition(pcbnew.VECTOR2I(0,0));clone.SetReference('REF**');clone.SetValue(libname)
  clone.SetLibDescription('Stratolink '+ref+' as-placed 1x07 1.00 mm pitch; 0.50 mm finished holes; '+f'{dia:.2f}'+' mm copper lands. Preserves placed v1 geometry; solder mask 1:1 under existing board settings.')
  pcbnew.FootprintSave(str(out/'lib'),clone)
  assert (out/'lib'/f'{libname}.kicad_mod').exists()
 # Remove only this script's superseded shared library from the earlier trial.
 oldlib=out/'lib'/('Stratolink_Header_1x07_P1p00_D0p50_Pad'+f'{dia:.2f}'.replace('.','p')+'.kicad_mod')
 if oldlib.exists():oldlib.unlink()
 r=subprocess.run([CLI,'pcb','drc','--refill-zones','--save-board','--schematic-parity','--format','json','--output',str(H/(label+'-drc-project.json')),str(out/'stratolink.kicad_pcb')],check=True,capture_output=True,text=True);(out/'drc.log').write_text(r.stdout+r.stderr)
 dr=json.loads((H/(label+'-drc-project.json')).read_text());results.append(dict(name=label,directory=str(out),land_mm=dia,annulus_mm=(dia-.5)/2,nominal_adjacent_gap_mm=1-dia,libraries=[v+'.kicad_mod' for v in libnames.values()],pcb_sha256=hashlib.sha256((out/'stratolink.kicad_pcb').read_bytes()).hexdigest(),counts={k:len(dr[k]) for k in ['violations','unconnected_items','schematic_parity']}))
(H/'candidates.json').write_text(json.dumps(dict(baseline=BASE,candidates=results),indent=2)+'\n');print(json.dumps(results,indent=2))
