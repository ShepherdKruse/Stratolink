#!/usr/bin/env python3
"""Read-only independent scope/connectivity verification of frozen .88 mm header candidate."""
from pathlib import Path
import json,sys,subprocess,hashlib,shutil
from collections import Counter
import pcbnew,wx
H=Path(__file__).resolve().parent;ROOT=H.parents[2];BASE='d70a53d2093454084c9b1ae989d0276a88395334';C=Path.home()/'Repositories/ai-working/scratch/stratolink-edges-20261012/rings/pad0p88';D=C.parent/'diagnostic';CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'));import check_solar_attachments as a
sys.path.insert(0,str(ROOT/'analysis/v1_1_microphone_20261012/review'));from check_drc_delta import signature
expected_sha='194705abb2dc3151d6cf067892d350fda43a495820eb89e202c78e2a616d5ec1'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(n):return subprocess.check_output(['git','show',BASE+':hardware/pcb/'+n],cwd=ROOT)
def stripfill(z):return [x for x in z if not(isinstance(x,list) and x and x[0] in ['filled_polygon','filled_areas_thickness'])]
assert sha(C/'stratolink.kicad_pcb')==expected_sha
old,new=[a.parse(s) for s in [git('stratolink.kicad_pcb').decode(),(C/'stratolink.kicad_pcb').read_text()]]
fpids={r:'lib:Stratolink_Header_'+side+'_1x07_P1p00_D0p50_Pad0p88' for r,side in [('J3','Left'),('J4','Right')]};changes=[]
for t in [old,new]:
 for z in a.nodes(t,'zone'):t[t.index(z)]=stripfill(z)
of,nf=[{a.prop(f,'Reference'):f for f in a.nodes(t,'footprint')} for t in [old,new]]
for ref,fp in fpids.items():
 assert nf[ref][1]==fp;nf[ref][1]=of[ref][1]
 for p in a.nodes(nf[ref],'pad'):
  size=a.nodes(p,'size');assert size==[['size','0.88','0.88']];size[0][1:]=['0.85','0.85'];changes.append(dict(ref=ref,pad=p[1],uuid=a.field(p,'uuid'),net=a.field(p,'net'),old_size_mm=[.85,.85],new_size_mm=[.88,.88],drill_mm=.5))
assert old==new,'Unexpected board changes beyond14 land sizes,2 identities and refill'
oldsch,newsch=[a.parse(s) for s in [git('stratolink.kicad_sch').decode(),(C/'stratolink.kicad_sch').read_text()]]
for sym in a.nodes(newsch,'symbol'):
 ref=a.prop(sym,'Reference')
 if ref in fpids:
  prop=next(p for p in a.nodes(sym,'property') if p[1]=='Footprint');assert prop[2]==fpids[ref];prop[2]='Connector_PinHeader_1.00mm:PinHeader_1x07_P1.00mm_Vertical'
assert oldsch==newsch
for n in ['stratolink.kicad_pro','fp-lib-table','sym-lib-table']:assert (C/n).read_bytes()==git(n)
base_lib=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE+':hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
for n in base_lib:assert (C/'lib'/n).read_bytes()==git('lib/'+n)
newlib={p.relative_to(C/'lib').as_posix() for p in (C/'lib').rglob('*') if p.is_file()}-set(base_lib)
assert newlib=={v.split(':',1)[1]+'.kicad_mod' for v in fpids.values()}
app=wx.App(False);B=C.parent/'baseline.kicad_pcb';B.write_bytes(git('stratolink.kicad_pcb'));ob,nb=[pcbnew.LoadBoard(str(p)) for p in [B,C/'stratolink.kicad_pcb']];og,ng=[a.pad_groups(b) for b in [ob,nb]];assert og.keys()==ng.keys();checked=0
for key in og:
 ps={p.m_Uuid.AsString():p for p in og[key]}
 for p in ng[key]:
  q=ps[p.m_Uuid.AsString()];assert q.GetNetname()==p.GetNetname();assert a.connected_keys(ob.GetConnectivity(),q)==a.connected_keys(nb.GetConnectivity(),p),(key,'connectivity');assert q.GetPosition()==p.GetPosition() and q.GetDrillSize()==p.GetDrillSize() and q.GetShape()==p.GetShape();checked+=1
assert checked==232 and nb.GetConnectivity().GetUnconnectedCount(False)==0
for ref,fp in fpids.items():
 lib=pcbnew.FootprintLoad(str(C/'lib'),fp.split(':',1)[1]);f=next(f for f in nb.GetFootprints() if f.GetReference()==ref)
 def pd(p):return (p.GetNumber(),p.GetFPRelativePosition().x,p.GetFPRelativePosition().y,p.GetSize().x,p.GetSize().y,p.GetDrillSize().x,p.GetDrillSize().y,p.GetShape(),p.GetLayerSet().FmtHex(),p.GetSolderMaskExpansion(pcbnew.F_Mask))
 assert sorted(pd(p) for p in f.Pads())==sorted(pd(p) for p in lib.Pads())
D.mkdir(exist_ok=True)
for n in ['stratolink.kicad_pcb','stratolink.kicad_sch','fp-lib-table','sym-lib-table']:shutil.copyfile(C/n,D/n)
shutil.copyfile(ROOT/'analysis/v1_1_solar_attachments_20261012/layout/validation/screen-settings.kicad_pro',D/'stratolink.kicad_pro')
if not (D/'lib').exists():(D/'lib').symlink_to(C/'lib')
r=subprocess.run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(H/'selected-drc-diagnostic.json'),str(D/'stratolink.kicad_pcb')],check=True,capture_output=True,text=True);(H/'selected-diagnostic.log').write_text(r.stdout+r.stderr)
deltas={}
for label,before,after in [('project',ROOT/'analysis/v1_1_ground_20261012/canonical-drc-project.json',H/'pad0p88-drc-project.json'),('diagnostic',ROOT/'analysis/v1_1_ground_20261012/candidate-drc-prior-screen.json',H/'selected-drc-diagnostic.json')]:
 od,nd=[json.loads(p.read_text()) for p in [before,after]];deltas[label]={}
 for cat in ['violations','unconnected_items','schematic_parity']:
  oc,nc=[Counter(signature(v) for v in d[cat]) for d in [od,nd]];added=[json.loads(x) for x in (nc-oc).elements()];removed=[json.loads(x) for x in (oc-nc).elements()]
  if cat!='violations':assert not added and not removed
  deltas[label][cat]=dict(before=len(od[cat]),after=len(nd[cat]),added=added,removed=removed)
 assert not nd['unconnected_items']
 assert not any(v['type']=='lib_footprint_mismatch' and any('J3' in i['description'] or 'J4' in i['description'] for i in v['items']) for v in nd['violations'])
assert not deltas['project']['violations']['added'];assert len(deltas['project']['violations']['removed'])==2
assert sha(C/'stratolink.kicad_pcb')==expected_sha
result=dict(status='pass_scoped_candidate_not_manufacturing_release',baseline=BASE,candidate=str(C),pcb_sha256=expected_sha,schematic_sha256=sha(C/'stratolink.kicad_sch'),changes=changes,footprint_identities=fpids,new_libraries={n:sha(C/'lib'/n) for n in sorted(newlib)},baseline_libraries_unchanged=len(base_lib),all_other_geometry_routing_and_project_settings_unchanged=True,physical_pad_connectivity_checks=checked,holes_and_centers_unchanged=True,mask_margin_unchanged_zero=True,native_drc_delta=deltas,limits='Uniform0.15mm diagnostic intentionally rejects the ~0.12mm PTH pad gaps; those are explicit fabrication-screen findings, not suppressed. Independent combined review must check edge-route changes and local manufacturing minima.')
(H/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(sha=expected_sha,checked=checked,libraries=sorted(newlib),counts={k:{c:v[c]['after'] for c in ['violations','unconnected_items','schematic_parity']} for k,v in deltas.items()}),indent=2))
