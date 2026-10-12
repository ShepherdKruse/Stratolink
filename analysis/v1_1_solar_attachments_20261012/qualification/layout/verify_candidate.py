#!/usr/bin/env python3
"""Read-only scope and DRC regression verifier for frozen upper-bank candidate."""
from pathlib import Path
import hashlib,json,sys,subprocess
from collections import Counter
H=Path(__file__).resolve().parent;ROOT=H.parents[3]
sys.path.insert(0,str(H.parents[1]/'layout'));import cad_helpers as a
sys.path.insert(0,str(ROOT/'analysis/v1_1_microphone_20261012/review'));from check_drc_delta import signature
BASE='76ee6e87463b70519769750d6795988b2c202683'
OUT=Path.home()/'Repositories/ai-working/scratch/stratolink-solar-depth2/upper-only'
def git(name):return subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT)
old=a.parse(git('stratolink.kicad_pcb').decode());new=a.parse((OUT/'stratolink.kicad_pcb').read_text())
def bykind(tree,kind):return {a.scalar(o,'uuid'):o for o in a.nodes(tree,kind)}
assert bykind(old,'segment')==bykind(new,'segment'), 'Signal/GND track objects changed'
assert bykind(old,'arc')==bykind(new,'arc')
of={a.prop(f,'Reference'):f for f in a.nodes(old,'footprint')};nf={a.prop(f,'Reference'):f for f in a.nodes(new,'footprint')}
assert of.keys()==nf.keys()
retained=sorted(set(of)-{'J1','J2'})
assert all(of[r]==nf[r] for r in retained)
for r in ['J1','J2']:
 assert a.one(of[r],'at')==a.one(nf[r],'at')
 assert a.nodes(of[r],'model')==a.nodes(nf[r],'model')
 for layer in ['F.Cu','B.Cu']:
  pads=[p for p in a.nodes(nf[r],'pad') if p[1]=='2' and layer in a.one(p,'layers')]
  assert len(pads)==1
  p=pads[0];assert p[3]=='rect';assert a.floats(p,'size')==[2.1,.68];assert a.floats(p,'at')[1]==-1.06
 assert len(a.nodes(nf[r],'pad'))==3
ov,nv=bykind(old,'via'),bykind(new,'via');removed=set(ov)-set(nv)
assert len(removed)==2 and not set(nv)-set(ov)
assert sorted(a.floats(ov[u],'at') for u in removed)==[[54.1665,55.55],[75.8255,55.55]]
assert all(a.scalar(ov[u],'net')=='GND' for u in removed)
assert all(nv[u]==ov[u] for u in nv)
changed_edges=[]
for kind in ['gr_line','gr_arc','gr_circle','gr_text']:
 before,after=bykind(old,kind),bykind(new,kind)
 assert before.keys()==after.keys(),kind
 for u in before:
  if before[u]==after[u]:continue
  assert a.scalar(after[u],'layer')=='Edge.Cuts'
  assert kind in ['gr_line','gr_arc']
  changed_edges.append(u)
assert len(changed_edges)==6
os=git('stratolink.kicad_sch').replace(b'_1p0x1p5',b'_1p0x2p0')
assert (OUT/'stratolink.kicad_sch').read_bytes()==os
assert (OUT/'stratolink.kicad_pro').read_bytes()==git('stratolink.kicad_pro')
comp={}
for label,oldp,newp in [('project',H.parents[1]/'review/final/drc-project.json',H/'drc-upper-only.json'),('diagnostic',H.parents[1]/'review/final/drc-diagnostic.json',H/'drc-upper-only-diagnostic.json')]:
 od,nd=(json.loads(p.read_text()) for p in [oldp,newp]);comp[label]={}
 for k in ['violations','schematic_parity','unconnected_items']:
  aa,bb=(Counter(signature(v) for v in d[k]) for d in [od,nd]);added=list((bb-aa).elements());removed_findings=list((aa-bb).elements())
  assert not added,(label,k,added)
  comp[label][k]=dict(before=len(od[k]),after=len(nd[k]),added=added,removed=removed_findings)
con=json.loads((H/'upper-only-connectivity/comparison.json').read_text());assert con['status']=='pass'
files=['stratolink.kicad_pcb','stratolink.kicad_sch','lib/Solar_Notch_Left_1p0x2p0.kicad_mod','lib/Solar_Notch_Right_1p0x2p0.kicad_mod']
hashes={name:hashlib.sha256((OUT/name).read_bytes()).hexdigest() for name in files}
result=dict(status='pass',baseline_commit=BASE,promotion_source=str(OUT),candidate_sha256=hashes,retained_exact_footprints=retained,unchanged_tracks=len(bykind(new,'segment')),retained_exact_vias=len(nv),removed_ground_via_uuids=sorted(removed),changed_edge_uuids=changed_edges,schematic_electrical_change=False,model_references_unchanged=True,physical_pad_checks=con['physical_pad_connectivity_checks'],solar_pad_islands=con['solar_physical_pad_islands'],drc=comp,note='Project and diagnostic reference reports were frozen at the electrically identical 14d94de geometry; 76ee6e8 added only 3D references, independently verified by assembly/model-only-verification.json.')
(H/'upper-only-verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ['status','candidate_sha256','unchanged_tracks','retained_exact_vias','physical_pad_checks','drc']},indent=2))
