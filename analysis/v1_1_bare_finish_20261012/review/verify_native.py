#!/usr/bin/env python3
"""Independent native scope, connectivity, DRC and fabrication review.

Run with KiCad's bundled Python. All evaluations use regular scratch copies;
source candidate and frozen baseline are hash-guarded. approved-scope.json
must contain the independently reviewed, explicit object/field inventory.
"""
from pathlib import Path
import argparse,copy,gzip,hashlib,importlib.util,json,re,shutil,subprocess,sys,zipfile
from collections import Counter
import pcbnew,wx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-bare-finish-20261012/review'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
spec=importlib.util.spec_from_file_location('prior_ground_review',ROOT/'analysis/v1_1_ground_20261012/review/verify_native.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
a=prior.a;signature=prior.signature;contours=prior.contours;digest=prior.digest;normplot=prior.normplot;physical_set=prior.physical_set;pads=prior.pads;stripped=prior.stripped

def copy_project(source,dest):
 if dest.exists():shutil.rmtree(dest)
 dest.mkdir(parents=True)
 for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:shutil.copyfile(source/name,dest/name)
 shutil.copytree(source/'lib',dest/'lib',symlinks=False)

def layernode(setup,name):return next(x for x in a.nodes(next(x for x in a.nodes(setup,'stackup')),'layer') if x[1]==name)

def check_scope(base,new,scope):
 old,cur=[a.parse((p/'stratolink.kicad_pcb').read_text()) for p in [base,new]]
 of,nf=[{a.prop(f,'Reference'):f for f in a.nodes(t,'footprint')} for t in [old,cur]];assert of.keys()==nf.keys();changes=[]
 for ref in of:
  aa,bb=copy.deepcopy(of[ref]),copy.deepcopy(nf[ref]);spec=scope.get('footprints',{}).get(ref,{})
  if not spec:assert aa==bb,('Unscoped footprint',ref);continue
  fields=set(spec.get('fields',[]))
  if 'library_id' in spec:
   assert bb[1]==spec['library_id'];aa[1]=bb[1]
  if 'courtyard_before' in spec:
   ca,cb=[[x for x in a.nodes(f,'fp_line') if a.field(x,'layer')=='F.CrtYd'] for f in [aa,bb]]
   assert ca==spec['courtyard_before'];assert cb==spec['courtyard_after']
   for obj in ca:aa.remove(obj)
   for obj in cb:bb.remove(obj)
  for field in fields:
   before=[x for x in aa if isinstance(x,list) and x[0]==field];after=[x for x in bb if isinstance(x,list) and x[0]==field]
   expected_before,expected_after=spec['before'][field],spec['after'][field]
   if field=='fp_line':before,after,expected_before,expected_after=[a.keyed(x) for x in [before,after,expected_before,expected_after]]
   assert before==expected_before,('Unexpected initial footprint field',ref,field)
   assert after==expected_after,('Unexpected final footprint field',ref,field)
  assert stripped(aa,fields)==stripped(bb,fields),('Unscoped footprint geometry/metadata',ref)
  changes.append(dict(ref=ref,fields=sorted(fields),before=spec['before'],after=spec['after']))
 os,ns=[a.keyed(a.nodes(t,'segment')) for t in [old,cur]]
 assert set(os)-set(ns)==set(scope.get('removed_segments',[]));assert set(ns)-set(os)==set(scope.get('added_segments',[]))
 segment_changes=[]
 for uid in os.keys() & ns.keys():
  if os[uid]==ns[uid]:continue
  assert uid in scope.get('changed_segments',[]),('Unscoped segment',uid)
  assert stripped(os[uid],{'start','end'})==stripped(ns[uid],{'start','end'}),('Track net/layer/width altered',uid)
  segment_changes.append(dict(uuid=uid,before=os[uid],after=ns[uid]))
 assert {x['uuid'] for x in segment_changes}==set(scope.get('changed_segments',[]))
 for uid in scope.get('removed_segments',[]):assert os[uid]==scope['removed_segment_objects'][uid]
 oz,nz=[a.keyed(a.nodes(t,'zone')) for t in [old,cur]];assert oz.keys()==nz.keys()
 for uid in oz:assert stripped(oz[uid],{'filled_polygon','filled_areas_thickness'})==stripped(nz[uid],{'filled_polygon','filled_areas_thickness'}),('Zone configuration altered',uid)
 og,ng=[a.keyed(a.nodes(t,'gr_rect')) for t in [old,cur]]
 assert not set(og)-set(ng);assert set(ng)-set(og)==set(scope['mask_graphics'])
 for uid in og:assert og[uid]==ng[uid]
 for uid in scope['mask_graphics']:assert ng[uid]==scope['mask_graphics'][uid]
 aa,bb=[copy.deepcopy(a.nodes(t,'setup')[0]) for t in [old,cur]]
 for name,thickness in [('F.Mask','0'),('B.Mask','0'),('dielectric 1','0.33')]:
  p,q=layernode(aa,name),layernode(bb,name)
  assert a.field(q,'thickness')==thickness,(name,q)
  assert stripped(p,{'thickness'})==stripped(q,{'thickness'})
  p[:]=stripped(p,{'thickness'});q[:]=stripped(q,{'thickness'})
 assert a.nodes(aa,'tenting')==[['tenting',['front','yes'],['back','yes']]]
 assert a.nodes(bb,'tenting')==[['tenting',['front','no'],['back','no']]]
 assert stripped(aa,{'tenting'})==stripped(bb,{'tenting'}),'Unscoped setup change'
 assert stripped(old,{'footprint','segment','zone','gr_rect','setup'})==stripped(cur,{'footprint','segment','zone','gr_rect','setup'}),'Unscoped board top-level object'
 so,sn=[a.parse((p/'stratolink.kicad_sch').read_text()) for p in [base,new]]
 for ref,properties in scope.get('schematic_properties',{}).items():
  symbols=[next(x for x in a.nodes(t,'symbol') if a.prop(x,'Reference')==ref) for t in [so,sn]]
  for name,expected in properties.items():
   pa,pb=[next(x for x in a.nodes(t,'property') if x[1]==name) for t in symbols]
   assert pa[2]==expected['before'] and pb[2]==expected['after'];pa[2]=pb[2]
 assert so==sn,'Schematic modified beyond reviewed AE1/AE2 metadata values'
 po,pn=[json.loads((p/'stratolink.kicad_pro').read_text()) for p in [base,new]]
 assert pn['board']['design_settings']['rule_severities']['solder_mask_bridge']=='ignore'
 po['board']['design_settings']['rule_severities']['solder_mask_bridge']='ignore'
 assert po==pn,'Unscoped project settings change'
 for name in ['fp-lib-table','sym-lib-table']:
  assert (base/name).read_bytes()==(new/name).read_bytes(),('Library table altered',name)
 oldlib={str(p.relative_to(base/'lib')):digest(p) for p in (base/'lib').rglob('*') if p.is_file()};newlib={str(p.relative_to(new/'lib')):digest(p) for p in (new/'lib').rglob('*') if p.is_file()}
 assert oldlib.keys()<=newlib.keys();assert all(newlib[n]==sha for n,sha in oldlib.items()),'Existing reusable libraries changed'
 assert set(newlib)-set(oldlib)==set(scope.get('new_library_files',[]))
 for name,sha in scope.get('new_library_files',{}).items():assert newlib[name]==sha,('New library/model differs from reviewed source',name)
 return dict(footprint_changes=changes,changed_segments=segment_changes,deleted_segment_objects={u:os[u] for u in scope.get('removed_segments',[])},new_mask_graphics=scope['mask_graphics'],all_82_existing_libraries_exact=True,library_tables_exact=True,schematic_change='Named AE1/AE2 metadata property values only',project_change='solder_mask_bridge ignore because no bridges are specified; raw enabled diagnostics retained',stackup='0.4 mm total; 0.33 mm nominal core plus two 0.035 mm copper layers; no modeled mask')

def run(cmd,log):
 result=subprocess.run(cmd,text=True,capture_output=True,check=True);log.write_text(result.stdout+result.stderr)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--candidate',required=True,type=Path);ap.add_argument('--collect-drc-inventory',action='store_true');args=ap.parse_args()
 source=args.candidate.resolve();manifest=json.loads((HERE/'baseline-manifest.json').read_text());base=Path(manifest['snapshot_path']);scope=json.loads((HERE/'approved-scope.json').read_text())
 for name,sha in manifest['files'].items():assert digest(base/name)==sha,('Baseline changed',name)
 protected={str(p):digest(p) for p in source.rglob('*') if p.is_file() and (p.suffix.lower() in ['.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_mod','.kicad_sym','.step','.stp','.wrl'] or p.name in ['fp-lib-table','sym-lib-table'])}
 report=check_scope(base,source,scope);work={k:SCRATCH/(k+'-evaluated') for k in ['baseline','candidate']}
 for label,d in [('baseline',base),('candidate',source)]:copy_project(d,work[label])
 app=wx.App(False);boards={k:pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb')) for k,p in work.items()}
 for b in boards.values():pcbnew.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity()
 for fp in boards['candidate'].GetFootprints():
  if fp.GetReference() not in ['AE1','AE2']:continue
  assert fp.GetFPID().GetLibNickname()=='lib'
  lib=pcbnew.FootprintLoad(str(source/'lib'),fp.GetFPID().GetLibItemName());assert lib is not None
  assert sorted([prior.libpad(p) for p in fp.Pads()],key=lambda x:x['number'])==sorted([prior.libpad(p) for p in lib.Pads()],key=lambda x:x['number']),('Placed/library pads differ',fp.GetReference())
 op,np=[pads(boards[k]) for k in ['baseline','candidate']];assert op.keys()==np.keys() and len(op)==232
 connectivity=[]
 for uid in sorted(op):
  assert op[uid].GetNetname()==np[uid].GetNetname()
  before,after=[physical_set(boards[k].GetConnectivity(),p) for k,p in [('baseline',op[uid]),('candidate',np[uid])]]
  assert before==after,('Physical island changed',uid,before-after,after-before)
  connectivity.append(dict(uuid=uid,ref=np[uid].GetParentFootprint().GetReference(),pad=np[uid].GetNumber(),net=np[uid].GetNetname(),reachable_pad_uuids=sorted(after)))
 assert boards['candidate'].GetConnectivity().GetUnconnectedCount(False)==0
 (HERE/'physical-connectivity.json').write_text(json.dumps(connectivity,indent=2)+'\n')
 native={}
 for label,b in boards.items():
  copper={};individual=[];assembly={};outline=pcbnew.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(outline,False)
  for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
   poly=pcbnew.SHAPE_POLY_SET();b.ConvertBrdLayerToPolygonalContours(layer,poly);poly.Simplify();copper[name]=contours(poly)
  for fp in b.GetFootprints():
   if fp.GetReference() in ['D1','AE1']:
    fp.BuildCourtyardCaches();assembly[fp.GetReference()]=dict(position_mm=[v/1e6 for v in fp.GetPosition()],courtyard=contours(fp.GetCourtyard(pcbnew.F_CrtYd)),courtyard_lines=[dict(start_mm=[v/1e6 for v in g.GetStart()],end_mm=[v/1e6 for v in g.GetEnd()],width_mm=g.GetWidth()/1e6) for g in fp.GraphicalItems() if isinstance(g,pcbnew.PCB_SHAPE) and g.GetLayer()==pcbnew.F_CrtYd])
   for p in fp.Pads():
    for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
     if not p.IsOnLayer(layer):continue
     poly=pcbnew.SHAPE_POLY_SET();p.TransformShapeToPolygon(poly,layer,0,100,pcbnew.ERROR_OUTSIDE)
     individual.append(dict(kind='pad',uuid=p.m_Uuid.AsString(),ref=fp.GetReference(),number=p.GetNumber(),net=p.GetNetname(),layer=b.GetLayerName(layer),polygons=contours(poly)))
  for t in b.GetTracks():
   for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
    if not t.IsOnLayer(layer):continue
    poly=pcbnew.SHAPE_POLY_SET();t.TransformShapeToPolygon(poly,layer,0,100,pcbnew.ERROR_OUTSIDE)
    individual.append(dict(kind='via' if isinstance(t,pcbnew.PCB_VIA) else 'track',uuid=t.m_Uuid.AsString(),net=t.GetNetname(),layer=b.GetLayerName(layer),polygons=contours(poly)))
  native[label]=dict(copper=copper,outline=contours(outline),individual_copper=individual,assembly=assembly)
  pcbnew.SaveBoard(str(work[label]/'stratolink.kicad_pcb'),b)
 (HERE/'native-geometry.json.gz').write_bytes(gzip.compress((json.dumps(native,separators=(',',':'))+'\n').encode(),mtime=0))
 drc={};exports={}
 for label,directory in work.items():
  drc[label]={}
  for mode in ['project','prior-uniform','retained-netclasses','original-edge-policy','mask-bridge-enabled']:
   target=directory if mode=='project' else SCRATCH/(label+'-'+mode)
   if mode!='project':
    copy_project(directory,target);p=json.loads((directory/'stratolink.kicad_pro').read_text())
    if mode=='prior-uniform':p=json.loads((ROOT/'analysis/v1_1_solar_attachments_20261012/layout/validation/screen-settings.kicad_pro').read_text())
    elif mode=='retained-netclasses':
     ds=p['board']['design_settings'];ds['rules']['min_clearance']=.15;ds['rules']['min_copper_edge_clearance']=.2;ds['rule_severities']['clearance']='error';ds['rule_severities']['copper_edge_clearance']='error'
    elif mode=='original-edge-policy':
     assert p['board']['design_settings']['rules']['min_copper_edge_clearance']==.5;p['board']['design_settings']['rule_severities']['copper_edge_clearance']='error'
    else:p['board']['design_settings']['rule_severities']['solder_mask_bridge']='error'
    assert p['board']['design_settings']['rules']['min_resolved_spokes']==2
    (target/'stratolink.kicad_pro').write_text(json.dumps(p,indent=2)+'\n')
   out=HERE/(label+'-drc-'+mode+'.json');run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(out),str(target/'stratolink.kicad_pcb')],target/'drc.log');drc[label][mode]=json.loads(out.read_text())
  export=SCRATCH/(label+'-exports')
  if export.exists():shutil.rmtree(export)
  export.mkdir();exports[label]=export
  run([CLI,'pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts','--output',str(export),str(directory/'stratolink.kicad_pcb')],export/'gerber.log')
  run([CLI,'pcb','export','drill','--format','excellon','--excellon-units','mm','--excellon-separate-th','--output',str(export),str(directory/'stratolink.kicad_pcb')],export/'drill.log')
 delta={}
 for mode in drc['baseline']:
  delta[mode]={}
  for category in ['violations','unconnected_items','schematic_parity']:
   aa,bb=[Counter(signature(x) for x in drc[k][mode][category]) for k in ['baseline','candidate']];added=list((bb-aa).elements());removed=list((aa-bb).elements())
   if not args.collect_drc_inventory:
    expected=[json.dumps(x,sort_keys=True) for x in scope.get('expected_new_drc',{}).get(mode,{}).get(category,[])]
    bridges=[x for x in added if json.loads(x)['type']=='solder_mask_bridge']
    for item in bridges:
     issue=json.loads(item);assert category=='violations' and set(issue['item_uuids']) & set(scope['mask_graphics']),('Mask finding unrelated to full-board opening',issue)
    nonbridges=[x for x in added if x not in bridges]
    assert Counter(nonbridges)==Counter(expected),(mode,category,'New non-mask findings differ from reviewed no-mask inventory',nonbridges,expected)
   delta[mode][category]=dict(before=sum(aa.values()),after=sum(bb.values()),added=[json.loads(x) for x in added],removed=[json.loads(x) for x in removed])
  assert not drc['candidate'][mode]['unconnected_items']
 unchanged=[]
 for name in ['stratolink-F_Paste.gtp','stratolink-B_Paste.gbp','stratolink-Edge_Cuts.gm1','stratolink-PTH.drl','stratolink-NPTH.drl']:
  assert normplot((exports['baseline']/name).read_text())==normplot((exports['candidate']/name).read_text()),('Unscoped manufacturing change',name);unchanged.append(name)
 # Assembly correction is courtyard-only; both stencil programs are exact.
 with zipfile.ZipFile(HERE/'review-exports.zip','w',zipfile.ZIP_DEFLATED) as z:
  for label,folder in exports.items():
   for p in sorted(folder.iterdir()):
    if p.is_file() and p.suffix!='.log':z.write(p,label+'/'+p.name)
 assert protected=={p:digest(Path(p)) for p in protected},'Candidate changed during review'
 for name,sha in manifest['files'].items():assert digest(base/name)==sha,('Baseline changed',name)
 report.update(status='native checks passed; independent geometry review pending' if not args.collect_drc_inventory else 'inventory only; pending review',candidate=str(source),source_hashes=protected,baseline_revision=manifest['revision'],all_physical_pad_sets_checked=232,unconnected=0,drc=delta,unchanged_manufacturing_plots=unchanged,export_zip_sha256=digest(HERE/'review-exports.zip'))
 (HERE/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ['source_hashes','drc','changed_segments','new_mask_graphics','footprint_changes','deleted_segment_objects']},indent=2))

if __name__=='__main__':main()
