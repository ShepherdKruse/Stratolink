#!/usr/bin/env python3
"""Read-only native scope/connectivity review; diagnostic copy stays in scratch."""
from pathlib import Path
import json,hashlib,subprocess,sys,shutil
from collections import Counter
import pcbnew,wx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as a
sys.path.insert(0,str(ROOT/'analysis/v1_1_microphone_20261012/review'))
from check_drc_delta import signature
BASE='a9d6ed5'
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-suspension-pth'
OUT=SCRATCH/'candidate';BEFORE=SCRATCH/'baseline';DIAG=SCRATCH/'diagnostic'
BEFORE.mkdir(exist_ok=True);DIAG.mkdir(exist_ok=True)
def git(name):return subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT)
for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro']:(BEFORE/name).write_bytes(git(name))
for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','fp-lib-table','sym-lib-table']:shutil.copy2(OUT/name,DIAG/name)
shutil.copytree(OUT/'lib',DIAG/'lib',dirs_exist_ok=True)
shutil.copy2(ROOT/'analysis/v1_1_solar_attachments_20261012/layout/validation/screen-settings.kicad_pro',DIAG/'stratolink.kicad_pro')
cli='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
run=subprocess.run([cli,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(HERE/'drc-diagnostic.json'),str(DIAG/'stratolink.kicad_pcb')],capture_output=True,text=True,check=True)
(HERE/'diagnostic.log').write_text(run.stdout+run.stderr)
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [OUT/'stratolink.kicad_pcb',OUT/'stratolink.kicad_sch',ROOT/'hardware/pcb/stratolink.kicad_pcb']}
old,new=[a.parse(p.read_text()) for p in [BEFORE/'stratolink.kicad_pcb',OUT/'stratolink.kicad_pcb']]
of,nf=[{a.prop(f,'Reference'):f for f in a.nodes(t,'footprint')} for t in [old,new]]
assert set(nf)-set(of)=={'H1','H2'} and not set(of)-set(nf)
assert all(of[r]==nf[r] for r in of), 'Retained footprint changed'
for kind in ['segment','arc','via','gr_text','gr_line','gr_arc']:
 assert a.keyed(a.nodes(old,kind))==a.keyed(a.nodes(new,kind)),kind
oc,nc=[a.keyed(a.nodes(t,'gr_circle')) for t in [old,new]]
removed=set(oc)-set(nc)
assert removed=={'107f8202-1fe1-4511-99bb-472b3941de6c','d8863d69-e0c5-455b-8892-eb88fd120483'}
assert not set(nc)-set(oc) and all(oc[k]==nc[k] for k in nc)
assert (OUT/'stratolink.kicad_sch').read_bytes()==git('stratolink.kicad_sch')
assert (OUT/'stratolink.kicad_pro').read_bytes()==git('stratolink.kicad_pro')
for ref in ['H1','H2']:
 assert set(a.nodes(nf[ref],'attr')[0][1:])=={'through_hole','board_only','exclude_from_pos_files','exclude_from_bom'}
 pads=a.nodes(nf[ref],'pad');assert len(pads)==1
 p=pads[0];assert a.nodes(p,'drill')[0][1:]==['2'];assert a.nodes(p,'size')[0][1:]==['3.2','3.2']
 assert a.field(p,'net')=='GND' and a.field(p,'zone_connect')=='2'
 assert a.nodes(p,'layers')[0][1:]==['*.Cu','*.Mask']
app=wx.App(False);ob,nb=[pcbnew.LoadBoard(str(p)) for p in [BEFORE/'stratolink.kicad_pcb',OUT/'stratolink.kicad_pcb']]
og,ng=a.pad_groups(ob),a.pad_groups(nb);extras={('H1','1'),('H2','1')}
assert set(ng)-set(og)==extras and not set(og)-set(ng)
cc0,cc1=ob.GetConnectivity(),nb.GetConnectivity();checked=0
for node,pads in og.items():
 oldpads={p.m_Uuid.AsString():p for p in pads}
 for pad in ng[node]:
  before=oldpads[pad.m_Uuid.AsString()]
  assert before.GetNetname()==pad.GetNetname()
  assert a.connected_keys(cc0,before)==a.connected_keys(cc1,pad)-extras,(node,'physical connectivity')
  checked+=1
original_ground={node for node,pads in og.items() if all(p.GetNetname()=='GND' for p in pads)}
ground_details={}
for node in extras:
 pads=ng[node];assert len(pads)==1
 reached=a.connected_keys(cc1,pads[0]);assert reached-extras==original_ground
 ground_details['.'.join(node)]={'original_GND_nodes_reached':len(reached-extras),'all_GND_nodes_including_H1_H2':len(reached)}
assert cc1.GetUnconnectedCount(False)==0
po,pn=a.poly_summary(ob),a.poly_summary(nb)
assert po['valid'] and pn['valid'] and po['hole_count']==2 and pn['hole_count']==0
assert po['bounds_mm']==pn['bounds_mm']
deltas={}
for label,base in [('project','drc-canonical.json'),('diagnostic','layout/drc-upper-only-diagnostic.json')]:
 oldr=json.loads((ROOT/'analysis/v1_1_solar_attachments_20261012/qualification'/base).read_text());newr=json.loads((HERE/f'drc-{label}.json').read_text());deltas[label]={}
 for category in ['violations','unconnected_items','schematic_parity']:
  b,c=[Counter(signature(i) for i in r[category]) for r in [oldr,newr]]
  added=list((c-b).elements());removed_findings=list((b-c).elements())
  deltas[label][category]=dict(before=len(oldr[category]),after=len(newr[category]),added=added,removed=removed_findings)
  assert not added,(label,category,added)
assert hashes=={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in hashes}
result=dict(status='pass',baseline=BASE,candidate=str(OUT),hashes=hashes,retained_exact_footprints=len(of),tracks_unchanged=len(a.nodes(old,'segment')),track_arcs_unchanged=len(a.nodes(old,'arc')),vias_unchanged=len(a.nodes(old,'via')),removed_circle_uuids=sorted(removed),schematic_byte_identical=True,project_byte_identical=True,physical_existing_pad_connectivity_checks=checked,ground_connectivity=ground_details,native_opens=0,outline_before=po,outline_after=pn,drc=deltas)
(HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
