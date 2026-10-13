#!/usr/bin/env python3
"""Independent bounded check of the agreed edge/ring candidate; copied CAD only.

Run with KiCad's bundled Python and --candidate <project directory>.
approved-scope.json is a reviewed inventory, not inferred permission to edit.
The baseline and source candidate remain unchanged; evaluated copies live in
the external task scratch directory.
"""
from pathlib import Path
import argparse,copy,gzip,hashlib,json,shutil,subprocess,sys,zipfile
from collections import Counter
import pcbnew,wx

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-edges-20261012/review'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
sys.path.insert(0,str(ROOT/'analysis/v1_1_ground_20261012/review'))
import verify_native as prior
from verify_native import a,signature,contours,digest,normplot,physical_set,pads,stripped

def copy_project(source,dest):
 if dest.exists():shutil.rmtree(dest)
 dest.mkdir(parents=True)
 for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:
  shutil.copyfile(source/name,dest/name)
 shutil.copytree(source/'lib',dest/'lib',symlinks=False)

def check_scope(base,new,scope):
 old,cur=[a.parse((p/'stratolink.kicad_pcb').read_text()) for p in [base,new]]
 of,nf=[{a.prop(f,'Reference'):f for f in a.nodes(t,'footprint')} for t in [old,cur]]
 assert of.keys()==nf.keys();changed_pads=[]
 for ref in of:
  aa,bb=copy.deepcopy(of[ref]),copy.deepcopy(nf[ref])
  if ref not in scope.get('footprints',{}):assert aa==bb,('Unscoped footprint change',ref);continue
  spec=scope['footprints'][ref]
  if 'library_id' in spec:
   assert bb[1]==spec['library_id'];aa[1]=bb[1]
  pa,pb=[a.keyed(a.nodes(x,'pad')) for x in [aa,bb]];assert pa.keys()==pb.keys()
  for uid in pa:
   if pa[uid]==pb[uid]:continue
   number=pa[uid][1];assert number in spec['pads'];fields=set(spec['pads'][number]['fields'])
   assert stripped(pa[uid],fields)==stripped(pb[uid],fields),('Pad beyond scope',ref,number)
   changed_pads.append(dict(ref=ref,pad=number,before=[x for x in pa[uid] if isinstance(x,list) and x[0] in fields],after=[x for x in pb[uid] if isinstance(x,list) and x[0] in fields]))
   pa[uid][:]=stripped(pa[uid],fields);pb[uid][:]=stripped(pb[uid],fields)
  assert aa==bb,('Other footprint change',ref)
 os,ns=[a.keyed(a.nodes(t,'segment')) for t in [old,cur]]
 assert set(os)-set(ns)==set(scope.get('removed_segments',[]))
 assert set(ns)-set(os)==set(scope.get('added_segments',[]))
 for uid in set(ns)-set(os):
  assert a.field(ns[uid],'width')=='0.25'
  net=a.field(ns[uid],'net');assert net in {'+SOLAR','VSTOR','PA9'}
  assert a.field(ns[uid],'layer')==('B.Cu' if net=='PA9' else 'F.Cu')
 changes=[]
 for uid in os.keys() & ns.keys():
  if os[uid]==ns[uid]:continue
  assert uid in scope['changed_segments'],('Unscoped segment',uid)
  assert stripped(os[uid],{'start','end'})==stripped(ns[uid],{'start','end'}),('Segment width/layer/net changed',uid)
  changes.append(dict(uuid=uid,before=os[uid],after=ns[uid]))
 assert {x['uuid'] for x in changes}==set(scope['changed_segments'])
 oz,nz=[a.keyed(a.nodes(t,'zone')) for t in [old,cur]];assert oz.keys()==nz.keys()
 for uid in oz:assert stripped(oz[uid],{'filled_polygon','filled_areas_thickness'})==stripped(nz[uid],{'filled_polygon','filled_areas_thickness'})
 assert stripped(old,{'footprint','segment','zone'})==stripped(cur,{'footprint','segment','zone'}),'Unscoped board object change'
 sch_old,sch_new=[a.parse((p/'stratolink.kicad_sch').read_text()) for p in [base,new]]
 so,sn=[{a.prop(s,'Reference'):s for s in a.nodes(t,'symbol')} for t in [sch_old,sch_new]]
 assert so.keys()==sn.keys();schematic_changes=[]
 for ref in so:
  if so[ref]==sn[ref]:continue
  assert ref in scope.get('schematic_footprints',{}),('Unscoped schematic symbol',ref)
  po,pn=[next(x for x in a.nodes(s,'property') if x[1]=='Footprint') for s in [so[ref],sn[ref]]]
  assert pn[2]==scope['schematic_footprints'][ref]
  schematic_changes.append(dict(ref=ref,before=po[2],after=pn[2]));po[2]=pn[2]
  assert so[ref]==sn[ref],('Schematic change beyond footprint metadata',ref)
 assert sch_old==sch_new,'Other schematic object changed'
 assert {x['ref'] for x in schematic_changes}==set(scope.get('schematic_footprints',{}))
 for name in ['stratolink.kicad_pro','fp-lib-table','sym-lib-table']:
  assert (base/name).read_bytes()==(new/name).read_bytes(),('Schematic/project/table changed',name)
 oldlib={str(p.relative_to(base/'lib')):digest(p) for p in (base/'lib').rglob('*') if p.is_file()}
 newlib={str(p.relative_to(new/'lib')):digest(p) for p in (new/'lib').rglob('*') if p.is_file()}
 assert not oldlib.keys()-newlib.keys()
 changedlib=[n for n in newlib if n not in oldlib or oldlib[n]!=newlib[n]]
 assert set(changedlib)==set(scope.get('library_files',[])),('Unexpected library delta',changedlib)
 return dict(changed_pads=changed_pads,changed_segments=changes,changed_libraries=changedlib,schematic_footprint_metadata_changes=schematic_changes)

def run(command,log):
 r=subprocess.run(command,check=True,text=True,capture_output=True);log.write_text(r.stdout+r.stderr)

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--candidate',required=True,type=Path)
 ap.add_argument('--collect-drc-inventory',action='store_true',help='Collect expected local clearance findings for explicit review; never marks DRC passed')
 args=ap.parse_args()
 source=args.candidate.resolve();manifest=json.loads((HERE/'baseline-manifest.json').read_text());base=Path(manifest['snapshot_path'])
 for name,sha in manifest['files'].items():assert digest(base/name)==sha,('Frozen baseline altered',name)
 scope=json.loads((HERE/'approved-scope.json').read_text())
 protected={str(p):digest(p) for p in source.rglob('*') if p.is_file() and (p.suffix in ['.kicad_pcb','.kicad_sch','.kicad_pro','.kicad_mod','.kicad_sym'] or p.name in ['fp-lib-table','sym-lib-table'])}
 report=check_scope(base,source,scope)
 work={name:SCRATCH/(name+'-evaluated') for name in ['baseline','candidate']}
 for label,s in [('baseline',base),('candidate',source)]:copy_project(s,work[label])
 app=wx.App(False);boards={k:pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb')) for k,p in work.items()}
 for b in boards.values():pcbnew.ZONE_FILLER(b).Fill(b.Zones());b.BuildConnectivity()
 for fp in boards['candidate'].GetFootprints():
  if fp.GetReference() not in scope.get('footprints',{}):continue
  assert fp.GetFPID().GetLibNickname()=='lib'
  lib=pcbnew.FootprintLoad(str(source/'lib'),fp.GetFPID().GetLibItemName())
  assert lib is not None
  assert sorted([prior.libpad(p) for p in fp.Pads()],key=lambda x:x['number'])==sorted([prior.libpad(p) for p in lib.Pads()],key=lambda x:x['number']),('Placed/local-library pad mismatch',fp.GetReference())
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
  copper={}
  for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
   poly=pcbnew.SHAPE_POLY_SET();b.ConvertBrdLayerToPolygonalContours(layer,poly);poly.Simplify();copper[name]=contours(poly)
  rings=[];individual=[]
  for fp in b.GetFootprints():
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
  for z in b.Zones():
   if z.GetIsRuleArea():continue
   for layer in [pcbnew.F_Cu,pcbnew.B_Cu]:
    if z.IsOnLayer(layer):individual.append(dict(kind='zone',uuid=z.m_Uuid.AsString(),net=z.GetNetname(),layer=b.GetLayerName(layer),polygons=contours(z.GetFilledPolysList(layer))))
  for fp in b.GetFootprints():
   if fp.GetReference() not in ['J3','J4']:continue
   for p in fp.Pads():
    mask={}
    for layer in [pcbnew.F_Mask,pcbnew.B_Mask]:
     m=p.GetSolderMaskExpansion(layer);q=p.Duplicate();q.SetSize(pcbnew.VECTOR2I(p.GetSize().x+2*m,p.GetSize().y+2*m))
     poly=pcbnew.SHAPE_POLY_SET();q.TransformShapeToPolygon(poly,pcbnew.F_Cu,0,100,pcbnew.ERROR_OUTSIDE)
     mask[b.GetLayerName(layer)]=dict(expansion_mm=m/1e6,polygons=contours(poly))
    rings.append(dict(ref=fp.GetReference(),number=p.GetNumber(),uuid=p.m_Uuid.AsString(),net=p.GetNetname(),at_mm=[v/1e6 for v in p.GetPosition()],size_mm=[v/1e6 for v in p.GetSize()],drill_mm=[v/1e6 for v in p.GetDrillSize()],offset_mm=[v/1e6 for v in p.GetOffset()],shape=p.GetShape(),mask=mask,nominal_minimum_ring_mm=(min(p.GetSize())-max(p.GetDrillSize()))/2e6))
  routes=[]
  for t in b.GetTracks():
   if not isinstance(t,pcbnew.PCB_TRACK) or isinstance(t,pcbnew.PCB_VIA):continue
   if t.GetNetname() not in ['+SOLAR','VSTOR','PA9']:continue
   routes.append(dict(uuid=t.m_Uuid.AsString(),net=t.GetNetname(),layer=b.GetLayerName(t.GetLayer()),start_mm=[v/1e6 for v in t.GetStart()],end_mm=[v/1e6 for v in t.GetEnd()],width_mm=t.GetWidth()/1e6))
  edges=[]
  for e in b.GetDrawings():
   if e.GetLayer()!=pcbnew.Edge_Cuts or e.GetShape()!=pcbnew.SHAPE_T_SEGMENT:continue
   edges.append(dict(uuid=e.m_Uuid.AsString(),start_mm=[v/1e6 for v in e.GetStart()],end_mm=[v/1e6 for v in e.GetEnd()]))
  native[label]=dict(copper=copper,rings=rings,routes=routes,straight_edges=edges,individual_copper=individual)
  pcbnew.SaveBoard(str(work[label]/'stratolink.kicad_pcb'),b)
 (HERE/'native-geometry.json.gz').write_bytes(gzip.compress((json.dumps(native,separators=(',',':'))+'\n').encode(),mtime=0))
 drc={};exports={}
 for label,directory in work.items():
  drc[label]={}
  for mode in ['project','prior-uniform','retained-netclasses','original-edge-policy']:
   target=directory if mode=='project' else SCRATCH/(label+'-'+mode)
   if mode!='project':
    copy_project(directory,target)
    p=json.loads((directory/'stratolink.kicad_pro').read_text())
    if mode=='prior-uniform':p=json.loads((ROOT/'analysis/v1_1_solar_attachments_20261012/layout/validation/screen-settings.kicad_pro').read_text())
    elif mode=='retained-netclasses':
     ds=p['board']['design_settings'];ds['rules']['min_clearance']=.15;ds['rules']['min_copper_edge_clearance']=.2
     ds['rule_severities']['clearance']='error';ds['rule_severities']['copper_edge_clearance']='error'
    else:
     assert p['board']['design_settings']['rules']['min_copper_edge_clearance']==.5
     p['board']['design_settings']['rule_severities']['copper_edge_clearance']='error'
    assert p['board']['design_settings']['rules']['min_resolved_spokes']==2
    (target/'stratolink.kicad_pro').write_text(json.dumps(p,indent=2)+'\n')
   out=HERE/(label+'-drc-'+mode+'.json')
   run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(out),str(target/'stratolink.kicad_pcb')],target/'drc.log')
   drc[label][mode]=json.loads(out.read_text())
  export=SCRATCH/(label+'-exports');export.mkdir(exist_ok=True);exports[label]=export
  run([CLI,'pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts','--output',str(export),str(directory/'stratolink.kicad_pcb')],export/'gerber.log')
  run([CLI,'pcb','export','drill','--format','excellon','--excellon-units','mm','--excellon-separate-th','--output',str(export),str(directory/'stratolink.kicad_pcb')],export/'drill.log')
 delta={}
 for mode in drc['baseline']:
  delta[mode]={}
  for category in ['violations','unconnected_items','schematic_parity']:
   aa,bb=[Counter(signature(x) for x in drc[k][mode][category]) for k in ['baseline','candidate']]
   added=list((bb-aa).elements());removed=list((aa-bb).elements())
   # Original-policy clearances may improve but remain below0.50; compare
   # those findings by item identities as well as literal numeric messages.
   if mode!='original-edge-policy':
    expected=[json.dumps(v,sort_keys=True) for v in scope.get('expected_new_drc',{}).get(mode,{}).get(category,[])]
    if not args.collect_drc_inventory:assert Counter(added)==Counter(expected),(mode,category,'New findings differ from reviewed local inventory',added,expected)
   else:
    for item in [json.loads(v) for v in added]:
     assert category=='violations' and item['type']=='copper_edge_clearance'
     assert set(item['item_uuids']) & (set(scope['changed_segments'])|set(scope['added_segments'])),('Unexpected stricter-policy finding',item)
   delta[mode][category]=dict(before=sum(aa.values()),after=sum(bb.values()),added=[json.loads(x) for x in added],removed=[json.loads(x) for x in removed])
  assert not drc['candidate'][mode]['unconnected_items']
 unchanged=[]
 for name in ['stratolink-F_Paste.gtp','stratolink-B_Paste.gbp','stratolink-Edge_Cuts.gm1','stratolink-PTH.drl','stratolink-NPTH.drl']:
  assert normplot((exports['baseline']/name).read_text())==normplot((exports['candidate']/name).read_text()),('Unscoped fabrication change',name)
  unchanged.append(name)
 for name in ['stratolink-F_Mask.gts','stratolink-B_Mask.gbs']:
  if not scope.get('footprints'):
   assert normplot((exports['baseline']/name).read_text())==normplot((exports['candidate']/name).read_text()),('Unscoped mask change',name)
   unchanged.append(name)
 with zipfile.ZipFile(HERE/'review-exports.zip','w',zipfile.ZIP_DEFLATED) as z:
  for label,folder in exports.items():
   for p in sorted(folder.iterdir()):
    if p.is_file() and p.suffix!='.log':z.write(p,label+'/'+p.name)
 assert protected=={p:digest(Path(p)) for p in protected},'Candidate changed during review'
 for name,sha in manifest['files'].items():assert digest(base/name)==sha,('Baseline altered',name)
 report.update(status='native scope/connectivity/exports passed; DRC inventory and geometry review pending' if args.collect_drc_inventory else 'native checks passed; independent geometry review pending',candidate=str(source),source_hashes=protected,baseline_revision=manifest['revision'],all_physical_pad_sets_checked=232,unconnected=0,drc=delta,unchanged_manufacturing_plots=unchanged,export_zip_sha256=digest(HERE/'review-exports.zip'))
 (HERE/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k not in ['source_hashes','drc','changed_segments']},indent=2))

if __name__=='__main__':main()
