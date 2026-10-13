#!/usr/bin/env python3
"""Independent read-only source review; exports/DRC run on copied snapshots.

Run with KiCad Python and --candidate <project-directory>. Baseline libraries
are actual Git-pinned regular files, never links into a mutable checkout.
"""
from pathlib import Path
import argparse,copy,hashlib,json,re,shutil,subprocess,sys,zipfile
from collections import Counter
import pcbnew,wx

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];BASE='c3d70a4'
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-zones-20261012/review';CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as a
sys.path.insert(0,str(ROOT/'analysis/v1_1_microphone_20261012/review'))
from check_drc_delta import signature
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'))
from extract_native import contours

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def git(name):return subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT)
def run(args,log):
 p=subprocess.run(args,check=True,text=True,capture_output=True);log.write_text(p.stdout+p.stderr)
def stripped(obj,keys):return [x for x in obj if not (isinstance(x,list) and x and x[0] in keys)]
def normplot(s):return '\n'.join(x for x in s.splitlines() if 'CreationDate' not in x and not x.startswith(('G04 Created by','; DRILL file')))
def physical_set(conn,pad):
 return {pad.m_Uuid.AsString()}|{p.m_Uuid.AsString() for p in conn.GetConnectedItems(pad) if isinstance(p,pcbnew.PAD)}
def pads(board):return {p.m_Uuid.AsString():p for f in board.GetFootprints() for p in f.Pads()}
def libpad(p):
 return dict(number=p.GetNumber(),at=list(p.GetFPRelativePosition()),size=list(p.GetSize()),
  drill=list(p.GetDrillSize()),layers=p.GetLayerSet().FmtHex(),shape=p.GetShape(),
  mask=p.GetSolderMaskExpansion(pcbnew.F_Mask),rr=p.GetRoundRectRadiusRatio(),
  zone=p.GetLocalZoneConnection(),gap=p.GetLocalThermalGapOverride(),width=p.GetLocalThermalSpokeWidthOverride(),angle=p.GetThermalSpokeAngleDegrees())
def check_library_scope(base,new):
 aa,bb=[a.parse((p/'lib/PQFN50P200X200100-12N.kicad_mod').read_text()) for p in [base,new]]
 pa,pb=[{p[1]:p for p in a.nodes(x,'pad')} for x in [aa,bb]]
 assert pa.keys()==pb.keys() and len(pa)==12
 changes=[]
 for number in pa:
  if pa[number]==pb[number]:continue
  assert number in {'5','7','8'}
  assert [x for x in pb[number] if isinstance(x,list) and x[0]=='zone_connect']==[['zone_connect','0']]
  assert stripped(pa[number],{'zone_connect'})==stripped(pb[number],{'zone_connect'})
  pa[number][:]=stripped(pa[number],{'zone_connect'});pb[number][:]=stripped(pb[number],{'zone_connect'})
  changes.append(number)
 assert aa==bb and set(changes)=={'5','7','8'},'Reusable U7 library changed outside scoped pad settings'
 return changes

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);args=ap.parse_args()
 source=args.candidate.resolve(); assert (source/'stratolink.kicad_pcb').is_file()
 names=['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']
 protected={str(source/n):digest(source/n) for n in names}
 protected.update({str(p):digest(p) for p in (source/'lib').rglob('*') if p.is_file()})
 base=SCRATCH/'baseline';new=SCRATCH/'candidate'
 for p in [base,new]:
  if p.exists():shutil.rmtree(p)
  p.mkdir(parents=True,exist_ok=True)
 library_names=subprocess.check_output(['git','ls-tree','-r','--name-only',BASE+':hardware/pcb/lib'],cwd=ROOT,text=True).splitlines()
 for name in names+['lib/'+x for x in library_names]:
  p=base/name;p.parent.mkdir(parents=True,exist_ok=True)
  assert not p.is_symlink();p.write_bytes(git(name))
 for name in names:shutil.copyfile(source/name,new/name)
 if (new/'lib').exists():shutil.rmtree(new/'lib')
 shutil.copytree(source/'lib',new/'lib',symlinks=False)
 baseline_hashes={n:digest(base/n) for n in names+['lib/'+x for x in library_names]}
 (HERE/'baseline-manifest.json').write_text(json.dumps(dict(revision=subprocess.check_output(['git','rev-parse',BASE],cwd=ROOT,text=True).strip(),files=baseline_hashes),indent=2)+'\n')
 old,newtree=[a.parse((p/'stratolink.kicad_pcb').read_text()) for p in [base,new]]
 of,nf=[{a.prop(f,'Reference'):f for f in a.nodes(t,'footprint')} for t in [old,newtree]]
 assert of.keys()==nf.keys()
 allowed={('U7','5'),('U7','7'),('U7','8'),('J20','5')};fields={'zone_connect'}
 changed=[]
 for ref in of:
  aa,bb=copy.deepcopy(of[ref]),copy.deepcopy(nf[ref]);pa,pb=[a.keyed(a.nodes(x,'pad')) for x in [aa,bb]]
  assert pa.keys()==pb.keys()
  for key in pa:
   if pa[key]==pb[key]:continue
   node=(ref,pa[key][1]);assert node in allowed,('Unexpected pad change',node)
   assert stripped(pa[key],fields)==stripped(pb[key],fields),('Pad changed beyond thermal override',node)
   changed.append(dict(ref=ref,pad=node[1],before=[x for x in pa[key] if isinstance(x,list) and x[0] in fields],after=[x for x in pb[key] if isinstance(x,list) and x[0] in fields]))
   pa[key][:]=stripped(pa[key],fields);pb[key][:]=stripped(pb[key],fields)
  assert aa==bb,('Other footprint change',ref)
 assert {(x['ref'],x['pad']) for x in changed}==allowed
 for x in changed:
  assert x['after']==[['zone_connect','2' if x['ref']=='J20' else '0']],x
 oz,nz=[a.keyed(a.nodes(t,'zone')) for t in [old,newtree]]
 duplicate='e9b71a22-0a8a-41f9-b5c4-115945b7ef58';assert set(oz)-set(nz)=={duplicate} and not set(nz)-set(oz)
 for key in nz:
  assert stripped(oz[key],{'filled_polygon','filled_areas_thickness'})==stripped(nz[key],{'filled_polygon','filled_areas_thickness'}),('Zone configuration changed',key)
 assert stripped(old,{'footprint','zone'})==stripped(newtree,{'footprint','zone'}),'Other board object changed'
 for name in names[1:]:assert (base/name).read_bytes()==(new/name).read_bytes(),('Project/schematic/table change',name)
 changed_lib=[]
 for name in library_names:
  assert (new/'lib'/name).is_file(),('Missing library',name)
  if (base/'lib'/name).read_bytes()!=(new/'lib'/name).read_bytes():changed_lib.append(name)
 assert set(changed_lib)<= {'PQFN50P200X200100-12N.kicad_mod'},changed_lib
 assert set(str(p.relative_to(new/'lib')) for p in (new/'lib').rglob('*') if p.is_file())==set(library_names),'Unexpected new library file'
 library_pad_changes=check_library_scope(base,new)
 app=wx.App(False);ob,nb=[pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb')) for p in [base,new]]
 # Fresh native fills affect only in-memory objects, then copied snapshot files.
 for b in [ob,nb]:pcbnew.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity()
 op,np=pads(ob),pads(nb);assert op.keys()==np.keys() and len(op)==232
 conn=[]
 for uid in sorted(op):
  assert op[uid].GetNetname()==np[uid].GetNetname()
  before,after=physical_set(ob.GetConnectivity(),op[uid]),physical_set(nb.GetConnectivity(),np[uid])
  assert before==after,('Physical island changed',uid,sorted(before-after),sorted(after-before))
  conn.append(dict(uuid=uid,ref=np[uid].GetParentFootprint().GetReference(),pad=np[uid].GetNumber(),net=np[uid].GetNetname(),reachable_physical_pad_uuids=sorted(after)))
 assert nb.GetConnectivity().GetUnconnectedCount(False)==0
 (HERE/'physical-connectivity.json').write_text(json.dumps(conn,indent=2)+'\n')
 # The revised local reusable footprint must retain its pad overrides exactly.
 f=next(f for f in nb.GetFootprints() if f.GetReference()=='U7')
 lib=pcbnew.FootprintLoad(str(new/'lib'),'PQFN50P200X200100-12N')
 assert sorted([libpad(p) for p in f.Pads()],key=lambda x:x['number'])==sorted([libpad(p) for p in lib.Pads()],key=lambda x:x['number'])
 native={}
 for label,b,directory in [('baseline',ob,base),('candidate',nb,new)]:
  layers={}
  for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
   poly=pcbnew.SHAPE_POLY_SET();b.ConvertBrdLayerToPolygonalContours(layer,poly);poly.Simplify();layers[name]=contours(poly)
  zone_front=[]
  for z in b.Zones():
   if not z.GetIsRuleArea() and z.IsOnLayer(pcbnew.F_Cu):zone_front.extend(contours(z.GetFilledPolysList(pcbnew.F_Cu)))
  pad_shapes={}
  for fp in b.GetFootprints():
   if fp.GetReference() not in ['U7','J20']:continue
   for p in fp.Pads():
    if fp.GetReference()=='J20' and p.GetNumber()!='5':continue
    poly=pcbnew.SHAPE_POLY_SET();p.TransformShapeToPolygon(poly,pcbnew.F_Cu,0,1000,pcbnew.ERROR_OUTSIDE)
    pad_shapes[fp.GetReference()+'.'+p.GetNumber()]=dict(polygons=contours(poly),at_mm=[p.GetPosition().x/1e6,p.GetPosition().y/1e6],net=p.GetNetname())
  native[label]=dict(copper=layers,front_zone=zone_front,pads=pad_shapes,source_sha256=baseline_hashes['stratolink.kicad_pcb'] if label=='baseline' else protected[str(source/'stratolink.kicad_pcb')])
  pcbnew.SaveBoard(str(directory/'stratolink.kicad_pcb'),b)
 (HERE/'copper-native.json').write_text(json.dumps(native,separators=(',',':'))+'\n')
 drc={};exports={}
 for label,directory in [('baseline',base),('candidate',new)]:
  drc[label]={}
  for mode in ['project','diagnostic']:
   work=directory if mode=='project' else SCRATCH/(label+'-diagnostic')
   if mode=='diagnostic':
    if work.exists():shutil.rmtree(work)
    shutil.copytree(directory,work,symlinks=False)
    project=json.loads((work/'stratolink.kicad_pro').read_text());ds=project['board']['design_settings']
    assert ds['rules']['min_resolved_spokes']==2
    ds['rules']['min_clearance']=.15;ds['rules']['min_copper_edge_clearance']=.2
    ds['rule_severities']['clearance']='error';ds['rule_severities']['copper_edge_clearance']='error'
    (work/'stratolink.kicad_pro').write_text(json.dumps(project,indent=2)+'\n')
   output=HERE/(label+'-drc-'+mode+'.json')
   run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(output),str(work/'stratolink.kicad_pcb')],HERE/(label+'-'+mode+'.log'))
   drc[label][mode]=json.loads(output.read_text())
  export=SCRATCH/(label+'-exports');export.mkdir(exist_ok=True);exports[label]=export
  run([CLI,'pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts','--output',str(export),str(directory/'stratolink.kicad_pcb')],HERE/(label+'-gerber.log'))
  run([CLI,'pcb','export','drill','--format','excellon','--excellon-units','mm','--excellon-separate-th','--output',str(export),str(directory/'stratolink.kicad_pcb')],HERE/(label+'-drill.log'))
 deltas={}
 for mode in ['project','diagnostic']:
  deltas[mode]={}
  for category in ['violations','unconnected_items','schematic_parity']:
   aa,bb=[Counter(signature(x) for x in drc[k][mode][category]) for k in ['baseline','candidate']]
   added=list((bb-aa).elements());removed=list((aa-bb).elements());assert not added,(mode,category,added)
   deltas[mode][category]=dict(before=sum(aa.values()),after=sum(bb.values()),added=added,removed=[json.loads(x) for x in removed])
  assert not drc['candidate'][mode]['unconnected_items']
  assert not [v for v in drc['candidate'][mode]['violations'] if v['type'] in ['starved_thermal','zones_intersect']]
 unchanged=[]
 for name in ['stratolink-F_Mask.gts','stratolink-B_Mask.gbs','stratolink-F_Paste.gtp','stratolink-B_Paste.gbp','stratolink-Edge_Cuts.gm1','stratolink-PTH.drl','stratolink-NPTH.drl']:
  assert normplot((exports['baseline']/name).read_text())==normplot((exports['candidate']/name).read_text()),('Manufacturing plot changed',name)
  unchanged.append(name)
 with zipfile.ZipFile(HERE/'review-exports.zip','w',zipfile.ZIP_DEFLATED) as z:
  for label,directory in exports.items():
   for p in sorted(directory.iterdir()):
    if p.is_file():z.write(p,label+'/'+p.name)
 assert protected=={p:digest(Path(p)) for p in protected},'Review source changed during run'
 result=dict(status='native checks passed; run copper-delta review separately',baseline=BASE,candidate=str(source),source_hashes=protected,
  pad_changes=changed,deleted_zone=duplicate,all_other_board_objects_exact=True,physical_pad_checks=len(conn),unconnected=0,
  changed_library_files=changed_lib,baseline_libraries_frozen_regular_files=True,minimum_spokes_preserved=2,drc=deltas,
  library_only_changed_zone_connect_on_pads=library_pad_changes,
  unchanged_manufacturing_plots=unchanged,review_export_zip_sha256=digest(HERE/'review-exports.zip'))
 (HERE/'verification.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ['source_hashes','drc']},indent=2))

if __name__=='__main__':main()
