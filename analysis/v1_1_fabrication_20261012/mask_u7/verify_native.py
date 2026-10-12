#!/usr/bin/env python3
"""Independently verify U7-only mask edits, pad islands, library geometry and DRC delta."""
from pathlib import Path
import hashlib,json,sys,subprocess,collections
import pcbnew,wx
H=Path(__file__).resolve().parent;ROOT=H.parents[2];BASE='a9d6ed59ebd9ca6a4e04108afe0bbe3a827cddde';OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-u7-mask/candidate'
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/layout'));import cad_helpers as a
sys.path.insert(0,str(ROOT/'analysis/v1_1_microphone_20261012/review'));from check_drc_delta import signature
bp=OUT.parent/'baseline';bp.mkdir(exist_ok=True)
for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro']:
 (bp/name).write_bytes(subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT))
oldtext=(bp/'stratolink.kicad_pcb').read_text();newtext=(OUT/'stratolink.kicad_pcb').read_text();old,new=(a.parse(t) for t in [oldtext,newtext])
oldfp=next(o for o in a.nodes(old,'footprint') if a.prop(o,'Reference')=='U7');newfp=next(o for o in a.nodes(new,'footprint') if a.prop(o,'Reference')=='U7')
oldp={o[1]:o for o in a.nodes(oldfp,'pad')};newp={o[1]:o for o in a.nodes(newfp,'pad')};assert set(oldp)==set(newp) and len(newp)==12
for pin in oldp:
 assert a.scalar(oldp[pin],'solder_mask_margin')=='0.102';assert a.scalar(newp[pin],'solder_mask_margin')=='0'
 def nomask(p):return [o for o in p if not (isinstance(o,list) and o and o[0]=='solder_mask_margin')]
 assert nomask(oldp[pin])==nomask(newp[pin]),('Changed copper/paste/pin metadata',pin)
# Transform just the intended old mask fields in the parsed baseline and require full equality.
for p in a.nodes(oldfp,'pad'):
 for v in a.nodes(p,'solder_mask_margin'):v[1]='0'
assert old==new,'Additional PCB objects changed'
for name in ['stratolink.kicad_sch','stratolink.kicad_pro']:assert (OUT/name).read_bytes()==(bp/name).read_bytes()
app=wx.App(False);boards=[pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb')) for p in [bp,OUT]]
def key(p):return p.GetParentFootprint().GetReference(),p.GetNumber()
def connectivity(b):
 c=b.GetConnectivity();ret={}
 for f in b.GetFootprints():
  for p in f.Pads():ret[p.m_Uuid.AsString()]={'key':key(p),'net':p.GetNetname(),'nodes':sorted({key(p)}|{key(x) for x in c.GetConnectedItems(p) if isinstance(x,pcbnew.PAD)})}
 return ret,c.GetUnconnectedCount(False)
o,no=connectivity(boards[0]);n,nn=connectivity(boards[1]);assert o==n;assert nn==no==0
f=next(f for f in boards[1].GetFootprints() if f.GetReference()=='U7');lib=pcbnew.FootprintLoad(str(OUT/'lib'),'PQFN50P200X200100-12N')
def paddata(p):return dict(number=p.GetNumber(),relative_at=[p.GetFPRelativePosition().x,p.GetFPRelativePosition().y],size=[p.GetSize().x,p.GetSize().y],mask=p.GetSolderMaskExpansion(pcbnew.F_Mask),layers=p.GetLayerSet().FmtHex(),roundrect=p.GetRoundRectRadiusRatio())
assert sorted([paddata(p) for p in f.Pads()],key=lambda p:p['number'])==sorted([paddata(p) for p in lib.Pads()],key=lambda p:p['number']),'Library pad geometry differs'
comp={}
for label,before,after in [('project',ROOT/'analysis/v1_1_solar_attachments_20261012/qualification/drc-canonical.json',H/'drc-project.json'),('diagnostic',ROOT/'analysis/v1_1_solar_attachments_20261012/qualification/layout/drc-upper-only-diagnostic.json',H/'drc-diagnostic.json')]:
 od,nd=(json.loads(p.read_text()) for p in [before,after]);comp[label]={}
 for k in ['violations','schematic_parity','unconnected_items']:
  aa,bb=(collections.Counter(signature(v) for v in d[k]) for d in [od,nd]);added=list((bb-aa).elements());removed=list((aa-bb).elements());assert not added,(label,k,added)
  if k=='violations':
   rr=[json.loads(x) for x in removed];assert collections.Counter(x['type'] for x in rr)=={'solder_mask_bridge':8,'lib_footprint_mismatch':1},rr
  else:assert not removed
  comp[label][k]=dict(before=len(od[k]),after=len(nd[k]),added=added,removed=[json.loads(x) for x in removed])
files=['stratolink.kicad_pcb','lib/PQFN50P200X200100-12N.kicad_mod'];hashes={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in files}
result=dict(status='pass',baseline_commit=BASE,candidate_dir=str(OUT),candidate_sha256=hashes,PCB_delta='Only12U7padmaskmargins0.102to0; all other parsed objects exact',schematic_and_project_unchanged=True,physical_pad_checks=len(n),native_unconnected=nn,library_pad_geometry_and_mask_match=True,drc=comp)
(H/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
