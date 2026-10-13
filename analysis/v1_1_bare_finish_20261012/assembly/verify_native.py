#!/usr/bin/env python3
"""Read-only native scope/connectivity/fabrication comparison for AE1 correction."""
from pathlib import Path
import copy, gzip, hashlib, importlib.util, json, re, subprocess,sys
from collections import Counter
import pcbnew,wx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'analysis/v1_1_ground_20261012/review'));import verify_native as prior
sys.path.insert(0,str(HERE));import build_candidate as build
SCRATCH=build.OUT.parent;BASE=SCRATCH/'baseline';NEW=build.OUT;CLI=build.prior.CLI;a=prior.a

def main():
 names=['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']
 libs=subprocess.check_output(['git','ls-tree','-r','--name-only',build.BASE+':hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
 for n in names+['lib/'+n for n in libs]:
  p=BASE/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(subprocess.check_output(['git','show',build.BASE+':hardware/pcb/'+n],cwd=ROOT))
 old,new=[a.parse((p/'stratolink.kicad_pcb').read_text()) for p in [BASE,NEW]]
 of,nf=[{a.prop(f,'Reference'):f for f in a.nodes(t,'footprint')} for t in [old,new]]
 assert of.keys()==nf.keys()
 def normalise(f):
  f=copy.deepcopy(f)
  f=[x for x in f if not (isinstance(x,list) and (x[0] in {'descr','model'} or x[0]=='fp_line' and a.field(x,'layer') in {'F.CrtYd','F.Fab'}))]
  f[1]='normalised'
  for x in a.nodes(f,'property'):
   if x[1] in {'Value','Datasheet','Description'}:x[2]='normalised'
  return f
 for ref in of:
  if ref not in build.PARTS:assert of[ref]==nf[ref],ref
  else:
   assert normalise(of[ref])==normalise(nf[ref]),ref
 assert prior.stripped(old,{'footprint'})==prior.stripped(new,{'footprint'})
 so,sn=[a.parse((p/'stratolink.kicad_sch').read_text()) for p in [BASE,NEW]]
 for t in [so,sn]:
  for fp in a.nodes(t,'symbol'):
   if a.prop(fp,'Reference') not in build.PARTS:continue
   for v in a.nodes(fp,'property'):
    if v[1] in {'Footprint','Value','Datasheet','Description'}:v[2]='normalised'
 assert so==sn
 for n in names[2:]+['lib/'+n for n in libs]:assert (BASE/n).read_bytes()==(NEW/n).read_bytes(),n
 assert {str(p.relative_to(NEW/'lib')) for p in (NEW/'lib').rglob('*') if p.is_file()}==set(libs)|{p['lib']+'.kicad_mod' for p in build.PARTS.values()}|{p['model'] for p in build.PARTS.values()}
 app=wx.App(False);boards=[pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb')) for p in [BASE,NEW]]
 for b in boards:pcbnew.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity()
 po,pn=[prior.pads(b) for b in boards];assert po.keys()==pn.keys() and len(pn)==232
 for u in po:assert prior.physical_set(boards[0].GetConnectivity(),po[u])==prior.physical_set(boards[1].GetConnectivity(),pn[u]),u
 assert boards[1].GetConnectivity().GetUnconnectedCount(False)==0
 for ref,part in build.PARTS.items():
  fp=next(f for f in boards[1].GetFootprints() if f.GetReference()==ref);lib=pcbnew.FootprintLoad(str(NEW/'lib'),part['lib'])
  assert [prior.libpad(p) for p in fp.Pads()]==[prior.libpad(p) for p in lib.Pads()],ref
 drcs={};exports={}
 for label,directory in [('baseline',BASE),('candidate',NEW)]:
  p=HERE/(label+'-drc-project.json')
  subprocess.run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(p),str(directory/'stratolink.kicad_pcb')],check=True,capture_output=True)
  drcs[label]=json.loads(p.read_text());out=SCRATCH/(label+'-exports');out.mkdir(exist_ok=True)
  subprocess.run([CLI,'pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts','--output',str(out),str(directory/'stratolink.kicad_pcb')],check=True,capture_output=True)
  subprocess.run([CLI,'pcb','export','drill','--format','excellon','--excellon-units','mm','--excellon-separate-th','--output',str(out),str(directory/'stratolink.kicad_pcb')],check=True,capture_output=True)
  exports[label]=out
 delta={}
 for k in ['violations','unconnected_items','schematic_parity']:
  aa,bb=[Counter(prior.signature(x) for x in drcs[l][k]) for l in ['baseline','candidate']]
  added,removed=list((bb-aa).elements()),list((aa-bb).elements());assert not added,(k,added)
  delta[k]=dict(before=sum(aa.values()),after=sum(bb.values()),added=[json.loads(x) for x in added],removed=[json.loads(x) for x in removed])
 assert {x['type'] for x in delta['violations']['removed']}=={'courtyards_overlap','lib_footprint_mismatch'}
 same=[]
 for n in ['stratolink-F_Cu.gtl','stratolink-B_Cu.gbl','stratolink-F_Mask.gts','stratolink-B_Mask.gbs','stratolink-F_Paste.gtp','stratolink-B_Paste.gbp','stratolink-Edge_Cuts.gm1','stratolink-PTH.drl','stratolink-NPTH.drl']:
  assert prior.normplot((exports['baseline']/n).read_text())==prior.normplot((exports['candidate']/n).read_text()),n;same.append(n)
 geometry={}
 for fp in boards[1].GetFootprints():
  if fp.GetReference() not in ['AE1','AE2','D1','D3']:continue
  geometry[fp.GetReference()]={'at_mm':[v/1e6 for v in fp.GetPosition()],'angle_degrees':fp.GetOrientationDegrees(),'pads':[{'number':p.GetNumber(),'at_mm':[v/1e6 for v in p.GetPosition()],'size_mm':[v/1e6 for v in p.GetSize()],'drill_mm':[v/1e6 for v in p.GetDrillSize()]} for p in fp.Pads()]}
 report=dict(pass_scope=True,unchanged_physical_pad_sets=232,opens=0,unchanged_fabrication_outputs=same,project_drc_delta=delta,geometry=geometry)
 (HERE/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
