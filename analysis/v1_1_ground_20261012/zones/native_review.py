#!/usr/bin/env python3
"""Read-only exact-object, native connectivity and copper extraction review."""
from pathlib import Path
import sys,json,hashlib,subprocess,shutil,gzip
from collections import Counter
import pcbnew,wx
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'));import check_solar_attachments as a
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/materials'));from extract_native import contours
sys.path.insert(0,str(ROOT/'analysis/v1_1_microphone_20261012/review'));from check_drc_delta import signature
BASE='c3d70a4';MAIN='795c4093-4930-4bcb-9c07-8e31d04084fe';BACK='e9b71a22-0a8a-41f9-b5c4-115945b7ef58'
SCRATCH=Path.home()/'Repositories/ai-working/scratch/stratolink-zones-20261012/zone'
CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
app=wx.App(False);boards={};trees={};geometry={};reports={};hashes={}
for variant in ['baseline','front-only-main','single-two-layer']:
 folder=SCRATCH/variant;path=folder/'stratolink.kicad_pcb';raw=path.read_bytes();hashes[variant]=hashlib.sha256(raw).hexdigest()
 trees[variant]=a.parse(raw.decode());b=pcbnew.LoadBoard(str(path));boards[variant]=b
 layers={}
 for layer,name in [(pcbnew.F_Cu,'F.Cu'),(pcbnew.B_Cu,'B.Cu')]:
  poly=pcbnew.SHAPE_POLY_SET();b.ConvertBrdLayerToPolygonalContours(layer,poly);poly.Simplify();layers[name]=contours(poly)
 zones=[]
 for z in b.Zones():
  zones.append(dict(uuid=z.m_Uuid.AsString(),net=z.GetNetname(),priority=z.GetAssignedPriority(),rule_area=z.GetIsRuleArea(),layers=[b.GetLayerName(l) for l in z.GetLayerSet().Seq()],boundary=contours(z.Outline()),fill={b.GetLayerName(l):contours(z.GetFilledPolysList(l)) for l in z.GetLayerSet().Seq()}))
 geometry[variant]=dict(source_sha256=hashes[variant],copper=layers,zones=zones)
 # Keep project-native refill independent from diagnostic parameter changes.
 diagnostic=SCRATCH/(variant+'-diagnostic');diagnostic.mkdir(exist_ok=True)
 for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','fp-lib-table','sym-lib-table']:shutil.copy2(folder/name,diagnostic/name)
 shutil.copytree(folder/'lib',diagnostic/'lib',dirs_exist_ok=True)
 p=json.loads((folder/'stratolink.kicad_pro').read_text());settings=p['board']['design_settings']
 for rule in ['clearance','annular_width','copper_edge_clearance']:settings['rule_severities'][rule]='error'
 settings['rules'].update(min_clearance=.15,min_copper_edge_clearance=.20,min_track_width=.10)
 for cls in p['net_settings']['classes']:cls['clearance']=.15
 (diagnostic/'stratolink.kicad_pro').write_text(json.dumps(p,indent=2)+'\n')
 run=subprocess.run([CLI,'pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(HERE/f'{variant}-drc-diagnostic.json'),str(diagnostic/'stratolink.kicad_pcb')],check=True,capture_output=True,text=True)
 (diagnostic/'drc.log').write_text(run.stdout+run.stderr)
 assert path.read_bytes()==raw
old=trees['baseline'];og=a.pad_groups(boards['baseline']);oc=boards['baseline'].GetConnectivity()
oldzones={a.field(z,'uuid'):z for z in a.nodes(old,'zone')}
def settings(z):return [x for x in z if not(isinstance(x,list) and x[0] in ['filled_polygon','layer','layers'])]
for variant in ['front-only-main','single-two-layer']:
 new=trees[variant];nb=boards[variant];ng=a.pad_groups(nb);nc=nb.GetConnectivity()
 assert [x for x in old if not(isinstance(x,list) and x[0]=='zone')]==[x for x in new if not(isinstance(x,list) and x[0]=='zone')], 'A non-zone board object changed'
 nz={a.field(z,'uuid'):z for z in a.nodes(new,'zone')}
 assert set(nz)==(set(oldzones) if variant=='front-only-main' else set(oldzones)-{BACK})
 assert all(settings(oldzones[u])==settings(nz[u]) for u in nz)
 assert set(og)==set(ng);checked=0
 for node,pads in og.items():
  oldpads={p.m_Uuid.AsString():p for p in pads}
  for p in ng[node]:
   oldp=oldpads[p.m_Uuid.AsString()]
   assert oldp.GetNetname()==p.GetNetname()
   assert a.connected_keys(oc,oldp)==a.connected_keys(nc,p),(variant,node,'pad reachability changed')
   checked+=1
 assert nc.GetUnconnectedCount(False)==0
 assert (SCRATCH/variant/'stratolink.kicad_sch').read_bytes()==(SCRATCH/'baseline/stratolink.kicad_sch').read_bytes()
 assert (SCRATCH/variant/'stratolink.kicad_pro').read_bytes()==(SCRATCH/'baseline/stratolink.kicad_pro').read_bytes()
 deltas={}
 for screen in ['project','diagnostic']:
  before,after=[json.loads((HERE/f'{v}-drc-{screen}.json').read_text()) for v in ['baseline',variant]];deltas[screen]={}
  for cat in ['violations','schematic_parity','unconnected_items']:
   bb,aa=[Counter(signature(i) for i in rr[cat]) for rr in [before,after]]
   deltas[screen][cat]=dict(before=len(before[cat]),after=len(after[cat]),added=[json.loads(s) for s in (aa-bb).elements()],removed=[json.loads(s) for s in (bb-aa).elements()])
 reports[variant]=dict(non_zone_objects_exact=True,all_retained_zone_settings_and_boundaries_exact=True,physical_pad_checks=checked,logical_pad_nodes=len(og),native_opens=0,schematic_and_project_byte_identical=True,drc=deltas)
(HERE/'native_geometry.json.gz').write_bytes(gzip.compress((json.dumps(geometry,separators=(',',':'))+'\n').encode(),mtime=0))
(HERE/'native-review.json').write_text(json.dumps(dict(baseline=BASE,hashes=hashes,variants=reports),indent=2)+'\n')
print(json.dumps(dict(hashes=hashes,variants=reports),indent=2))
