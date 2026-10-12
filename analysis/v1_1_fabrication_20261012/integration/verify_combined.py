#!/usr/bin/env python3
"""Read-only independent canonical integration verification.

Allowed changes from a9d6ed5: H1/H2 plus their two removed Edge.Cuts
circles and ground refill; twelve U7 mask-margin edits; only the matching
U7/H1/H2 reusable libraries. Native DRC and exports run without saving CAD.
Run with KiCad's bundled Python only after parent promotion.
"""
from pathlib import Path
import hashlib,json,re,sys,subprocess,shutil,zipfile
from collections import Counter
import pcbnew,wx
H=Path(__file__).resolve().parent;ROOT=H.parents[2];CAN=ROOT/'hardware/pcb';BASE='a9d6ed59ebd9ca6a4e04108afe0bbe3a827cddde'
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-combined-fab-review';BEFORE=SCRATCH/'baseline';DIAG=SCRATCH/'diagnostic';EXPORT=SCRATCH/'exports'
SUSP=Path.home()/'Repositories/ai-working/scratch/stratolink-suspension-pth/candidate'
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'));import check_solar_attachments as a
sys.path.insert(0,str(ROOT/'analysis/v1_1_microphone_20261012/review'));from check_drc_delta import signature
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/layout'));import cad_helpers as q
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'

def git(name):return subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(cmd,log):
 r=subprocess.run(cmd,check=True,text=True,capture_output=True);log.write_text(r.stdout+r.stderr)
def strip_filled(zone):return [x for x in zone if not (isinstance(x,list) and x and x[0] in ['filled_polygon','filled_areas_thickness'])]
def pad_data(p):return dict(number=p.GetNumber(),at=[p.GetFPRelativePosition().x,p.GetFPRelativePosition().y],size=[p.GetSize().x,p.GetSize().y],drill=[p.GetDrillSize().x,p.GetDrillSize().y],layers=p.GetLayerSet().FmtHex(),maskF=p.GetSolderMaskExpansion(pcbnew.F_Mask),maskB=p.GetSolderMaskExpansion(pcbnew.B_Mask),shape=p.GetShape(),rr=p.GetRoundRectRadiusRatio())
def normalized_gerber(s):return '\n'.join(l for l in s.splitlines() if 'CreationDate' not in l and not l.startswith('G04 Created by'))

for p in [BEFORE,DIAG,EXPORT]:p.mkdir(parents=True,exist_ok=True)
protected=[CAN/'stratolink.kicad_pcb',CAN/'stratolink.kicad_sch',CAN/'stratolink.kicad_pro',CAN/'lib/PQFN50P200X200100-12N.kicad_mod',CAN/'lib/Suspension_PTH_D2p0_OD3p2.kicad_mod']
beforehash={str(p):digest(p) for p in protected}
for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro']:(BEFORE/name).write_bytes(git(name))
old,new=[a.parse(p.read_text()) for p in [BEFORE/'stratolink.kicad_pcb',CAN/'stratolink.kicad_pcb']]
of,nf=[{a.prop(f,'Reference'):f for f in a.nodes(t,'footprint')} for t in [old,new]]
assert set(nf)-set(of)=={'H1','H2'} and not set(of)-set(nf)
assert all(of[r]==nf[r] for r in of if r!='U7'),'Existing footprint besides U7 changed'
oldU,newU=of['U7'],nf['U7'];assert len(a.nodes(oldU,'pad'))==len(a.nodes(newU,'pad'))==12
for pad in a.nodes(oldU,'pad'):
 margins=a.nodes(pad,'solder_mask_margin');assert len(margins)==1 and margins[0][1]=='0.102';margins[0][1]='0'
assert oldU==newU,'U7 changed beyond12maskmargins'
for kind in ['segment','arc','via','gr_text','gr_line','gr_arc']:
 assert a.keyed(a.nodes(old,kind))==a.keyed(a.nodes(new,kind)),kind
oc,nc=[a.keyed(a.nodes(t,'gr_circle')) for t in [old,new]];removed=set(oc)-set(nc)
assert removed=={'107f8202-1fe1-4511-99bb-472b3941de6c','d8863d69-e0c5-455b-8892-eb88fd120483'}
assert not set(nc)-set(oc) and all(oc[u]==nc[u] for u in nc)
oz,nz=[a.keyed(a.nodes(t,'zone')) for t in [old,new]];assert oz.keys()==nz.keys()
assert all(strip_filled(oz[u])==strip_filled(nz[u]) for u in oz),'Zone rules/outline changed beyond refill'
skip={'footprint','gr_circle','zone'}
assert [x for x in old if not (isinstance(x,list) and x and x[0] in skip)]==[x for x in new if not (isinstance(x,list) and x and x[0] in skip)],'Other root objects changed'
for name in ['stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:assert (CAN/name).read_bytes()==git(name),name
for ref in ['H1','H2']:
 assert set(a.nodes(nf[ref],'attr')[0][1:])=={'through_hole','board_only','exclude_from_pos_files','exclude_from_bom'}
 assert q.one(nf[ref],'at')==(['55.665','31.745'] if ref=='H1' else ['74.327','31.745'])
 pads=a.nodes(nf[ref],'pad');assert len(pads)==1;p=pads[0]
 assert q.floats(p,'drill')==[2.0] and q.floats(p,'size')==[3.2,3.2] and a.field(p,'net')=='GND' and a.field(p,'zone_connect')=='2'
 assert q.one(p,'layers')==['*.Cu','*.Mask']
# Only one existing reusable library may change; exactly one is added.
base_lib=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE+':hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
changed_lib=[]
for name in base_lib:
 p=CAN/'lib'/name;assert p.is_file(),('Missing library file',name)
 if p.read_bytes()!=git('lib/'+name):changed_lib.append(name)
assert changed_lib==['PQFN50P200X200100-12N.kicad_mod'],changed_lib
base_mod={n for n in base_lib if n.endswith('.kicad_mod')};new_mod={p.name for p in (CAN/'lib').glob('*.kicad_mod')}
assert new_mod-base_mod=={'Suspension_PTH_D2p0_OD3p2.kicad_mod'}
assert (CAN/'lib/Suspension_PTH_D2p0_OD3p2.kicad_mod').read_bytes()==(SUSP/'lib/Suspension_PTH_D2p0_OD3p2.kicad_mod').read_bytes()
# Canonical should also equal the reviewed suspension candidate except the12mask fields.
st=a.parse((SUSP/'stratolink.kicad_pcb').read_text());su=next(f for f in a.nodes(st,'footprint') if a.prop(f,'Reference')=='U7')
for p in a.nodes(su,'pad'):
 for m in a.nodes(p,'solder_mask_margin'):assert m[1]=='0.102';m[1]='0'
assert st==new,'Combined board differs from reviewed suspension plus mask-only edit'

app=wx.App(False);ob,nb=[pcbnew.LoadBoard(str(p)) for p in [BEFORE/'stratolink.kicad_pcb',CAN/'stratolink.kicad_pcb']]
og,ng=a.pad_groups(ob),a.pad_groups(nb);extras={('H1','1'),('H2','1')}
assert set(ng)-set(og)==extras and not set(og)-set(ng)
cc0,cc1=ob.GetConnectivity(),nb.GetConnectivity();checked=0
for node,pads in og.items():
 oldpads={p.m_Uuid.AsString():p for p in pads}
 for p in ng[node]:
  prior=oldpads[p.m_Uuid.AsString()];assert prior.GetNetname()==p.GetNetname()
  assert a.connected_keys(cc0,prior)==a.connected_keys(cc1,p)-extras,(node,p.m_Uuid.AsString(),'changed connectivity');checked+=1
original_ground={node for node,pads in og.items() if all(p.GetNetname()=='GND' for p in pads)};ground={}
for node in extras:
 assert len(ng[node])==1;p=ng[node][0];reached=a.connected_keys(cc1,p);assert reached-extras==original_ground
 assert p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH and p.GetDrillSize()==pcbnew.VECTOR2I(2000000,2000000)
 ground['.'.join(node)]=dict(original_ground_nodes=len(reached-extras),all_ground_nodes=len(reached));checked+=1
assert checked==232 and cc1.GetUnconnectedCount(False)==0
for ref,libname in [('U7','PQFN50P200X200100-12N'),('H1','Suspension_PTH_D2p0_OD3p2'),('H2','Suspension_PTH_D2p0_OD3p2')]:
 fp=next(f for f in nb.GetFootprints() if f.GetReference()==ref);lib=pcbnew.FootprintLoad(str(CAN/'lib'),libname)
 assert sorted([pad_data(p) for p in fp.Pads()],key=lambda p:p['number'])==sorted([pad_data(p) for p in lib.Pads()],key=lambda p:p['number']),(ref,'Library differs')
po,pn=a.poly_summary(ob),a.poly_summary(nb);assert po['valid'] and pn['valid'] and po['hole_count']==2 and pn['hole_count']==0 and po['bounds_mm']==pn['bounds_mm']
# Fresh canonical project DRC is read-only. Diagnostic overrides stay in scratch.
run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(H/'drc-project.json'),str(CAN/'stratolink.kicad_pcb')],H/'project.log')
for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','fp-lib-table','sym-lib-table']:shutil.copyfile(CAN/name,DIAG/name)
shutil.copyfile(ROOT/'analysis/v1_1_solar_attachments_20261012/layout/validation/screen-settings.kicad_pro',DIAG/'stratolink.kicad_pro')
for name in ['lib','3d']:
 p=DIAG/name
 if not p.exists():p.symlink_to(CAN/name)
run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(H/'drc-diagnostic.json'),str(DIAG/'stratolink.kicad_pcb')],H/'diagnostic.log')
expected=json.loads((H.parent/'mask_u7/verification.json').read_text())['drc'];deltas={}
for label,before in [('project',ROOT/'analysis/v1_1_solar_attachments_20261012/qualification/drc-canonical.json'),('diagnostic',ROOT/'analysis/v1_1_solar_attachments_20261012/qualification/layout/drc-upper-only-diagnostic.json')]:
 od,nd=[json.loads(p.read_text()) for p in [before,H/f'drc-{label}.json']];deltas[label]={}
 assert len(nd['violations'])==(61 if label=='project' else 74) and len(nd['schematic_parity'])==11 and not nd['unconnected_items']
 for cat in ['violations','unconnected_items','schematic_parity']:
  aa,bb=[Counter(signature(v) for v in d[cat]) for d in [od,nd]];added=list((bb-aa).elements());removed_findings=list((aa-bb).elements());assert not added
  got=[json.loads(x) for x in removed_findings]
  assert Counter(json.dumps(x,sort_keys=True) for x in got)==Counter(json.dumps(x,sort_keys=True) for x in expected[label][cat]['removed']),(label,cat,got)
  deltas[label][cat]=dict(before=len(od[cat]),after=len(nd[cat]),added=[],removed=got)
# Exact plot comparison with previously independently checked suspension export.
run([CLI,'pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts','--output',str(EXPORT),str(CAN/'stratolink.kicad_pcb')],H/'export.log')
run([CLI,'pcb','export','drill','--format','excellon','--excellon-units','mm','--excellon-separate-th','--output',str(EXPORT),str(CAN/'stratolink.kicad_pcb')],H/'drill.log')
oldex=ROOT/'analysis/v1_1_suspension_20261012/layout/fabrication';export_delta={}
for suffix in ['F_Cu.gtl','B_Cu.gbl','F_Paste.gtp','B_Paste.gbp','B_Mask.gbs','Edge_Cuts.gm1']:
 name='stratolink-'+suffix;assert normalized_gerber((oldex/name).read_text())==normalized_gerber((EXPORT/name).read_text()),('Unexpected plot change',name);export_delta[name]='identical_except_creation_timestamp'
for name in ['stratolink-PTH.drl','stratolink-NPTH.drl']:
 def trim(s):return '\n'.join(l for l in s.splitlines() if not l.startswith('; DRILL file') and 'CreationDate' not in l)
 assert trim((oldex/name).read_text())==trim((EXPORT/name).read_text()),('Drill change',name);export_delta[name]='identical_except_creation_timestamp'
a0,b0=[normalized_gerber((p/'stratolink-F_Mask.gts').read_text()) for p in [oldex,EXPORT]]
macro=lambda s:{int(m.group(1)):m.group(0) for m in re.finditer(r'%ADD(\d+)RoundRect,[^\n]+',s)}
ma,mb=macro(a0),macro(b0);changed=[i for i in ma if ma[i]!=mb[i]];assert len(changed)==2
patt=r'%ADD(?:'+'|'.join(str(i) for i in changed)+r')RoundRect,[^\n]+'
assert re.sub(patt,'U7MASK',a0)==re.sub(patt,'U7MASK',b0),'Other front mask changes'
ref=None;ap=None;flashes=[]
for line in b0.splitlines():
 m=re.fullmatch(r'%TO.C,([^*]+)\*%',line)
 if m:ref=m[1]
 if line=='%TD*%':ref=None
 m=re.fullmatch(r'D(\d+)\*',line)
 if m:ap=int(m[1])
 if 'D03*' in line and ap in changed:flashes.append(dict(ref=ref,aperture=ap,command=line))
assert len(flashes)==12 and all(p['ref']=='U7' for p in flashes)
export_delta['stratolink-F_Mask.gts']=dict(only_changed_aperture_ids=changed,U7_flashes=flashes)
assert beforehash=={str(p):digest(p) for p in protected},'Canonical changed during read-only verification'
with zipfile.ZipFile(H/'review-exports.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(EXPORT.iterdir()):
  if p.is_file():z.write(p,p.name)
result=dict(status='pass',baseline=BASE,kicad_version=pcbnew.GetBuildVersion(),canonical_unchanged_by_review=True,canonical_hashes=beforehash,existing_footprints=59,unchanged_footprints=58,U7_only_twelve_mask_margins=True,added_footprints=['H1','H2'],existing_pad_connectivity_checks=230,total_pad_connectivity_checks=checked,new_mount_ground_connectivity=ground,native_unconnected=0,unchanged_segments=879,unchanged_track_arcs=3,unchanged_vias=142,removed_edge_circles=sorted(removed),zone_configuration_unchanged=True,schematic_project_lib_tables_unchanged=True,modified_library_files=changed_lib,new_library_files=['Suspension_PTH_D2p0_OD3p2.kicad_mod'],drc=deltas,export_comparison=export_delta,export_sha256={p.name:digest(p) for p in EXPORT.iterdir() if p.is_file()},archive_sha256=digest(H/'review-exports.zip'),limits='Scope, connectivity, native DRC delta and manufacturing exports verified. JLC1:1 mask supported; ST positive mask/stencil/land-pattern review remains unresolved. Mechanical/string and RF testing remain physical checks.')
(H/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
