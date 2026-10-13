#!/usr/bin/env python3
"""Native, read-only scope/connectivity/DRC audit; output only evidence and scratch."""
from pathlib import Path
import sys,json,hashlib,subprocess,shutil,gzip,math
from collections import Counter
import pcbnew,wx
from build_candidate import HERE,ROOT,SCRATCH,CLI,CHANGES,ADDED_UUID
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as a
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'))
from extract_native import contours
sys.path.insert(0,str(ROOT/'analysis/v1_1_microphone_20261012/review'))
from check_drc_delta import signature

app=wx.App(False);boards={};trees={};geometry={};hashes={}
for variant in ['baseline','candidate']:
 folder=SCRATCH/variant;path=folder/'stratolink.kicad_pcb';raw=path.read_bytes()
 hashes[variant]=hashlib.sha256(raw).hexdigest();trees[variant]=a.parse(raw.decode())
 b=pcbnew.LoadBoard(str(path));boards[variant]=b;layers={}
 for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
  poly=pcbnew.SHAPE_POLY_SET();b.ConvertBrdLayerToPolygonalContours(layer,poly);poly.Simplify();layers[name]=contours(poly)
 poly=pcbnew.SHAPE_POLY_SET();assert b.GetBoardPolygonOutlines(poly,False,None,False,False)
 relevant=[]
 for t in b.GetTracks():
  if t.GetClass()=='PCB_VIA':continue
  if t.GetClass()=='PCB_ARC':continue
  p,q=t.GetStart(),t.GetEnd()
  relevant.append(dict(uuid=t.m_Uuid.AsString(),net=t.GetNetname(),layer=b.GetLayerName(t.GetLayer()),width_mm=t.GetWidth()/1e6,start_mm=[p.x/1e6,p.y/1e6],end_mm=[q.x/1e6,q.y/1e6]))
 pads=[]
 for f in b.GetFootprints():
  for p in f.Pads():
   for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
    if not p.IsOnLayer(layer):continue
    pp=pcbnew.SHAPE_POLY_SET();p.TransformShapeToPolygon(pp,layer,0,1000,pcbnew.ERROR_OUTSIDE)
    pads.append(dict(ref=f.GetReference(),number=p.GetNumber(),net=p.GetNetname(),layer=name,shape=contours(pp)))
 geometry[variant]=dict(source_sha256=hashes[variant],copper=layers,outline=contours(poly),segments=relevant,pads=pads)
 for screen in ['prior','retained-netclass']:
  diagnostic=SCRATCH/(variant+'-'+screen);diagnostic.mkdir(exist_ok=True)
  for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','fp-lib-table','sym-lib-table']:shutil.copy2(folder/name,diagnostic/name)
  shutil.copytree(folder/'lib',diagnostic/'lib',dirs_exist_ok=True)
  p=json.loads((folder/'stratolink.kicad_pro').read_text());settings=p['board']['design_settings']
  for rule in ['clearance','annular_width','copper_edge_clearance']:settings['rule_severities'][rule]='error'
  settings['rules'].update(min_clearance=.15,min_copper_edge_clearance=.20,min_track_width=.10)
  if screen=='prior':
   for cls in p['net_settings']['classes']:cls['clearance']=.15
  (diagnostic/'stratolink.kicad_pro').write_text(json.dumps(p,indent=2)+'\n')
  run=subprocess.run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(HERE/f'{variant}-drc-{screen}.json'),str(diagnostic/'stratolink.kicad_pcb')],check=True,capture_output=True,text=True)
  (diagnostic/'drc.log').write_text(run.stdout+run.stderr)
 assert path.read_bytes()==raw

old,new=[trees[k] for k in ['baseline','candidate']]
assert [x for x in old if not(isinstance(x,list) and x[0] in ['zone','segment'])]==[x for x in new if not(isinstance(x,list) and x[0] in ['zone','segment'])]
def settings(z):return [x for x in z if not(isinstance(x,list) and x[0]=='filled_polygon')]
assert [settings(z) for z in a.nodes(old,'zone')]==[settings(z) for z in a.nodes(new,'zone')]
def segments(tree):return {a.field(x,'uuid'):x for x in a.nodes(tree,'segment')}
oldseg,newseg=segments(old),segments(new)
assert set(newseg)==set(oldseg)|{ADDED_UUID}
assert {uid for uid in oldseg if oldseg[uid]!=newseg[uid]}==set(CHANGES)
for uid in CHANGES:
 for key in ['width','layer','net']:assert a.field(oldseg[uid],key)==a.field(newseg[uid],key)
ob,nb=boards['baseline'],boards['candidate'];og,ng=a.pad_groups(ob),a.pad_groups(nb);oc,nc=ob.GetConnectivity(),nb.GetConnectivity()
assert set(og)==set(ng);checked=0
for node,pads in og.items():
 oldpads={p.m_Uuid.AsString():p for p in pads}
 for p in ng[node]:
  oldp=oldpads[p.m_Uuid.AsString()];assert oldp.GetNetname()==p.GetNetname()
  assert a.connected_keys(oc,oldp)==a.connected_keys(nc,p),(node,'pad reachability changed')
  checked+=1
assert nc.GetUnconnectedCount(False)==0
for suffix in ['kicad_sch','kicad_pro']:
 assert (SCRATCH/'baseline'/f'stratolink.{suffix}').read_bytes()==(SCRATCH/'candidate'/f'stratolink.{suffix}').read_bytes()
deltas={}
for screen in ['project','prior','retained-netclass']:
 before,after=[json.loads((HERE/f'{v}-drc-{screen}.json').read_text()) for v in ['baseline','candidate']];deltas[screen]={}
 for cat in ['violations','schematic_parity','unconnected_items']:
  bb,aa=[Counter(signature(i) for i in rr[cat]) for rr in [before,after]]
  deltas[screen][cat]=dict(before=len(before[cat]),after=len(after[cat]),added=[json.loads(s) for s in (aa-bb).elements()],removed=[json.loads(s) for s in (bb-aa).elements()])
 deltas[screen]['types']={v:dict(Counter(x['type'] for x in rr['violations'])) for v,rr in [('before',before),('after',after)]}
report=dict(hashes=hashes,physical_pad_checks=checked,logical_pad_nodes=len(og),native_opens=0,all_footprints_vias_arcs_outline_and_nonroute_objects_exact=True,all_zone_settings_and_boundaries_exact=True,schematic_and_project_byte_identical=True,changed_segment_uuids=sorted(CHANGES),added_segment_uuids=[ADDED_UUID],drc=deltas)
(HERE/'native_geometry.json.gz').write_bytes(gzip.compress((json.dumps(geometry,separators=(',',':'))+'\n').encode(),mtime=0))
(HERE/'native-review.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
