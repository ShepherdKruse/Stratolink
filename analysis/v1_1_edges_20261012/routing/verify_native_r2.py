#!/usr/bin/env python3
"""Verify the second routing revision against both frozen source and Git baseline."""
import sys,json,hashlib,subprocess,shutil,gzip
from collections import Counter
import pcbnew,wx
from build_candidate import HERE,ROOT,SCRATCH,CLI,ADDED_UUID
from build_candidate_r2 import SOURCE,OUTPUT,EVIDENCE,R2_CHANGES
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as a
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'))
from extract_native import contours
sys.path.insert(0,str(ROOT/'analysis/v1_1_microphone_20261012/review'))
from check_drc_delta import signature
app=wx.App(False)
paths={'baseline':SCRATCH/'baseline/stratolink.kicad_pcb','combined-r1':SOURCE/'stratolink.kicad_pcb','candidate-r2':OUTPUT/'stratolink.kicad_pcb'}
raw={k:p.read_bytes() for k,p in paths.items()};boards={k:pcbnew.LoadBoard(str(p)) for k,p in paths.items()};trees={k:a.parse(v.decode()) for k,v in raw.items()}
source,final=[trees[k] for k in ['combined-r1','candidate-r2']]
assert [x for x in source if not(isinstance(x,list) and x[0] in ['zone','segment'])]==[x for x in final if not(isinstance(x,list) and x[0] in ['zone','segment'])]
def settings(z):return [x for x in z if not(isinstance(x,list) and x[0]=='filled_polygon')]
assert [settings(z) for z in a.nodes(source,'zone')]==[settings(z) for z in a.nodes(final,'zone')]
def segments(tree):return {a.field(x,'uuid'):x for x in a.nodes(tree,'segment')}
oldseg,newseg=segments(trees['baseline']),segments(final)
assert set(newseg)==set(oldseg)|{ADDED_UUID}
assert {uid for uid in oldseg if oldseg[uid]!=newseg[uid]}==set(R2_CHANGES)
for uid in R2_CHANGES:
 for key in ['width','layer','net']:assert a.field(oldseg[uid],key)==a.field(newseg[uid],key)
oc=boards['baseline'].GetConnectivity();og=a.pad_groups(boards['baseline']);checked={}
for key in ['combined-r1','candidate-r2']:
 nb=boards[key];ng=a.pad_groups(nb);nc=nb.GetConnectivity();assert set(og)==set(ng);count=0
 for node,pads in og.items():
  oldpads={p.m_Uuid.AsString():p for p in pads}
  for p in ng[node]:
   oldp=oldpads[p.m_Uuid.AsString()];assert oldp.GetNetname()==p.GetNetname()
   assert a.connected_keys(oc,oldp)==a.connected_keys(nc,p),(key,node,'pad reachability changed');count+=1
 assert nc.GetUnconnectedCount(False)==0;checked[key]=count
for name in ['stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:assert (SOURCE/name).read_bytes()==(OUTPUT/name).read_bytes()
for p in (SOURCE/'lib').rglob('*'):
 if p.is_file():assert p.read_bytes()==(OUTPUT/'lib'/p.relative_to(SOURCE/'lib')).read_bytes()
for screen in ['prior','retained-netclass']:
 diagnostic=SCRATCH/('candidate-r2-'+screen);diagnostic.mkdir(exist_ok=True)
 for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','fp-lib-table','sym-lib-table']:shutil.copy2(OUTPUT/name,diagnostic/name)
 shutil.copytree(OUTPUT/'lib',diagnostic/'lib',dirs_exist_ok=True)
 p=json.loads((OUTPUT/'stratolink.kicad_pro').read_text());settings=p['board']['design_settings']
 for rule in ['clearance','annular_width','copper_edge_clearance']:settings['rule_severities'][rule]='error'
 settings['rules'].update(min_clearance=.15,min_copper_edge_clearance=.20,min_track_width=.10)
 if screen=='prior':
  for cls in p['net_settings']['classes']:cls['clearance']=.15
 (diagnostic/'stratolink.kicad_pro').write_text(json.dumps(p,indent=2)+'\n')
 run=subprocess.run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(EVIDENCE/f'candidate-r2-drc-{screen}.json'),str(diagnostic/'stratolink.kicad_pcb')],check=True,capture_output=True,text=True)
 (diagnostic/'drc.log').write_text(run.stdout+run.stderr)
deltas={}
for screen in ['project','prior','retained-netclass']:
 before=json.loads((HERE/f'baseline-drc-{screen}.json').read_text());after=json.loads((EVIDENCE/f'candidate-r2-drc-{screen}.json').read_text());deltas[screen]={}
 for cat in ['violations','schematic_parity','unconnected_items']:
  bb,aa=[Counter(signature(i) for i in rr[cat]) for rr in [before,after]]
  deltas[screen][cat]=dict(before=len(before[cat]),after=len(after[cat]),added=[json.loads(s) for s in (aa-bb).elements()],removed=[json.loads(s) for s in (bb-aa).elements()])
 deltas[screen]['types']={v:dict(Counter(x['type'] for x in rr['violations'])) for v,rr in [('before',before),('after',after)]}
geometry={}
for variant in ['baseline','candidate-r2']:
 b=boards[variant];layers={}
 for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
  poly=pcbnew.SHAPE_POLY_SET();b.ConvertBrdLayerToPolygonalContours(layer,poly);poly.Simplify();layers[name]=contours(poly)
 poly=pcbnew.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(poly,False,None,False,False)
 relevant=[]
 for t in b.GetTracks():
  if t.GetClass() in ['PCB_VIA','PCB_ARC']:continue
  p,q=t.GetStart(),t.GetEnd()
  relevant.append(dict(uuid=t.m_Uuid.AsString(),net=t.GetNetname(),layer=b.GetLayerName(t.GetLayer()),width_mm=t.GetWidth()/1e6,start_mm=[p.x/1e6,p.y/1e6],end_mm=[q.x/1e6,q.y/1e6]))
 pads=[]
 for f in b.GetFootprints():
  for p in f.Pads():
   for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
    if not p.IsOnLayer(layer):continue
    pp=pcbnew.SHAPE_POLY_SET();p.TransformShapeToPolygon(pp,layer,0,1000,pcbnew.ERROR_OUTSIDE)
    pads.append(dict(ref=f.GetReference(),number=p.GetNumber(),net=p.GetNetname(),layer=name,shape=contours(pp)))
 geometry['candidate' if variant=='candidate-r2' else variant]=dict(source_sha256=hashlib.sha256(raw[variant]).hexdigest(),copper=layers,outline=contours(poly),segments=relevant,pads=pads)
assert all(p.read_bytes()==raw[k] for k,p in paths.items())
report=dict(hashes={k:hashlib.sha256(v).hexdigest() for k,v in raw.items()},physical_pad_checks=checked,logical_pad_nodes=len(og),native_opens=0,
 all_combined_nonroute_objects_exact=True,all_combined_zone_settings_and_boundaries_exact=True,combined_schematic_project_libraries_byte_identical=True,
 modified_route_uuids_vs_d70a53d=sorted(R2_CHANGES),added_route_uuids_vs_d70a53d=[ADDED_UUID],drc=deltas)
(EVIDENCE/'native_geometry.json.gz').write_bytes(gzip.compress((json.dumps(geometry,separators=(',',':'))+'\n').encode(),mtime=0))
(EVIDENCE/'native-review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
