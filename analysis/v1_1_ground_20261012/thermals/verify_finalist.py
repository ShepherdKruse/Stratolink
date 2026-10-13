#!/usr/bin/env python3
import gzip
"""Read-only native geometry/connectivity, scope, and fabrication evidence for local ground fix."""
from pathlib import Path
import sys,json,subprocess,hashlib,shutil
from collections import Counter
import pcbnew,wx
H=Path(__file__).resolve().parent;ROOT=H.parents[2];S=Path.home()/'Repositories/ai-working/scratch/stratolink-zones-20261012/thermal';BASE='c3d70a429a95591607341d57bf16ee153972da71';C=S/'trace_only_5_7_8';B=S/'baseline';CLI='/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli'
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'));import check_solar_attachments as a
sys.path.insert(0,str(ROOT/'analysis/v1_1_microphone_20261012/review'));from check_drc_delta import signature
B.mkdir(exist_ok=True)
for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:(B/name).write_bytes(subprocess.check_output(['git','show',BASE+':hardware/pcb/'+name],cwd=ROOT))
for name in ['lib','3d']:
 if not (B/name).exists():(B/name).symlink_to(ROOT/'hardware/pcb'/name)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,out):
 r=subprocess.run([CLI]+args,check=True,capture_output=True,text=True);out.write_text(r.stdout+r.stderr)
def stripfill(z):return [v for v in z if not (isinstance(v,list) and v and v[0] in ['filled_polygon','filled_areas_thickness'])]
run(['pcb','drc','--refill-zones','--save-board','--format','json','--output',str(H/'drc-baseline-refill.json'),str(B/'stratolink.kicad_pcb')],H/'drc-baseline-refill.log')
old,new=[a.parse((p/'stratolink.kicad_pcb').read_text()) for p in [B,C]]
of,nf=[{a.prop(f,'Reference'):f for f in a.nodes(t,'footprint')} for t in [old,new]]
assert of.keys()==nf.keys()
expected={('U7','5'):'0',('U7','7'):'0',('U7','8'):'0',('J20','5'):'2'};observed=[]
for ref,f in of.items():
 n=nf[ref]
 for p in a.nodes(n,'pad'):
  key=(ref,p[1]);fields=a.nodes(p,'zone_connect')
  if key in expected:
   assert fields==[['zone_connect',expected[key]]],(key,fields)
   p.remove(fields[0]);observed.append(key)
 assert f==n,('Other footprint changes',ref)
assert set(observed)==set(expected)
oz,nz=[a.keyed(a.nodes(t,'zone')) for t in [old,new]];assert oz.keys()==nz.keys()
assert all(stripfill(oz[k])==stripfill(nz[k]) for k in oz)
for t in [old,new]:
 for z in a.nodes(t,'zone'):t[t.index(z)]=stripfill(z)
assert old==new,'Unexpected board differences beyond four zone-connect overrides and refill'
for name in ['stratolink.kicad_sch','stratolink.kicad_pro','fp-lib-table','sym-lib-table']:assert (B/name).read_bytes()==(C/name).read_bytes()
app=wx.App(False);boards=[pcbnew.LoadBoard(str(p/'stratolink.kicad_pcb')) for p in [B,C]]
og,ng=[a.pad_groups(b) for b in boards];assert og.keys()==ng.keys();checked=0
for key in og:
 ps={p.m_Uuid.AsString():p for p in og[key]}
 for p in ng[key]:
  q=ps[p.m_Uuid.AsString()];assert p.GetNetname()==q.GetNetname();assert a.connected_keys(boards[0].GetConnectivity(),q)==a.connected_keys(boards[1].GetConnectivity(),p),(key,'connectivity');checked+=1
assert checked==232
# Capture native polygons at 0.1um approximation, suitable for actual fill and pad-contact measurements.
def chains(poly):
 def pts(c):return [[c.CPoint(i).x/1e6,c.CPoint(i).y/1e6] for i in range(c.PointCount())]
 return [dict(shell=pts(poly.Outline(i)),holes=[pts(poly.Hole(i,j)) for j in range(poly.HoleCount(i))]) for i in range(poly.OutlineCount())]
def shape(item,layer):
 p=pcbnew.SHAPE_POLY_SET();item.TransformShapeToPolygon(p,layer,0,100,pcbnew.ERROR_OUTSIDE);return chains(p)
regions={}
for label,b in zip(['baseline','selected'],boards):
 item=[]
 for f in b.GetFootprints():
  for p in f.Pads():
   if p.IsOnLayer(pcbnew.F_Cu):item.append(dict(type='pad',ref=f.GetReference(),pin=p.GetNumber(),net=p.GetNetname(),uuid=p.m_Uuid.AsString(),at=[p.GetPosition().x/1e6,p.GetPosition().y/1e6],polygons=shape(p,pcbnew.F_Cu)))
 for t in b.GetTracks():
  if t.IsOnLayer(pcbnew.F_Cu):item.append(dict(type='track',net=t.GetNetname(),uuid=t.m_Uuid.AsString(),width=(t.GetWidth(pcbnew.F_Cu) if isinstance(t,pcbnew.PCB_VIA) else t.GetWidth())/1e6,polygons=shape(t,pcbnew.F_Cu)))
 zones={str(l):[] for l in [pcbnew.F_Cu,pcbnew.B_Cu]}
 for z in b.Zones():
  for l in [pcbnew.F_Cu,pcbnew.B_Cu]:
   if z.IsOnLayer(l) and z.GetNetname()=='GND':zones[str(l)].extend(chains(z.GetFilledPolysList(l)))
 regions[label]=dict(zones=zones,items=item)
(H/'selected-regions.json.gz').write_bytes(gzip.compress((json.dumps(regions,separators=(',',':'))+'\n').encode(),mtime=0))
# Deliberately remove all zone objects in memory to establish the retained dedicated copper route.
source=(H/'build_trials.py').read_text();exec(source[source.index('def spans'):source.index("if '--mixed-only'")])
text=(C/'stratolink.kicad_pcb').read_text();parts=[(s,e,'') for s,e,d in spans(text) if d==1 and text[s:e].startswith('(zone')];track_file=S/'track-only-diagnostic.kicad_pcb';track_file.write_text(rewrite(text,parts))
b=pcbnew.LoadBoard(str(track_file));cc=b.GetConnectivity();groups=a.pad_groups(b);trackonly={}
for key in [('U7',p) for p in ['3','5','6','7','8']]:
 p=groups[key][0];connected=list(cc.GetConnectedItems(p));pads=sorted(a.connected_keys(cc,p));tracks=[x for x in connected if isinstance(x,pcbnew.PCB_TRACK)];vias=[x for x in connected if x.Type()==pcbnew.PCB_VIA_T]
 assert {('U7',p) for p in ['3','5','6','7','8']}<=set(pads)
 trackonly['.'.join(key)]=dict(reached_pads=pads,track_count=len(tracks),widths_mm=sorted(set(x.GetWidth()/1e6 for x in tracks if x.Type()!=pcbnew.PCB_VIA_T)),via_uuids=[x.m_Uuid.AsString() for x in vias])
# Fresh normal and widened diagnostic rule sets; minimum4 test keeps filled copper unchanged.
run(['pcb','drc','--refill-zones','--schematic-parity','--format','json','--output',str(H/'drc-baseline.json'),str(B/'stratolink.kicad_pcb')],H/'drc-baseline.log')
delta={}
for label,folder,project in [('project',C,C/'stratolink.kicad_pro'),('diagnostic',S/'selected-diagnostic',ROOT/'analysis/v1_1_solar_attachments_20261012/layout/validation/screen-settings.kicad_pro'),('minimum-four',S/'selected-four-spokes',C/'stratolink.kicad_pro')]:
 if folder!=C:
  folder.mkdir(exist_ok=True)
  for name in ['stratolink.kicad_pcb','stratolink.kicad_sch','fp-lib-table','sym-lib-table']:shutil.copyfile(C/name,folder/name)
  pro=json.loads(project.read_text())
  if label=='minimum-four':pro['board']['design_settings']['rules']['min_resolved_spokes']=4
  (folder/'stratolink.kicad_pro').write_text(json.dumps(pro,indent=2)+'\n')
  for name in ['lib','3d']:
   if not (folder/name).exists():(folder/name).symlink_to(ROOT/'hardware/pcb'/name)
 args=['pcb','drc','--schematic-parity','--format','json','--output',str(H/f'drc-selected-{label}.json'),str(folder/'stratolink.kicad_pcb')]
 if label!='minimum-four':args.insert(2,'--refill-zones')
 run(args,H/f'drc-selected-{label}.log')
 dr=json.loads((H/f'drc-selected-{label}.json').read_text());delta[label]=dict(violations=len(dr['violations']),opens=len(dr['unconnected_items']),parity=len(dr['schematic_parity']))
 if label=='minimum-four':delta[label]['U7_thermal_findings']=[v for v in dr['violations'] if v['type']=='starved_thermal' and any('of U7' in i['description'] for i in v['items'])];continue
 prior=H/'drc-baseline.json' if label=='project' else ROOT/'analysis/v1_1_fabrication_20261012/integration/drc-diagnostic.json';od=json.loads(prior.read_text())
 for cat in ['violations','unconnected_items','schematic_parity']:
  ac,bc=[Counter(signature(v) for v in d[cat]) for d in [od,dr]];added=list((bc-ac).elements());removed=list((ac-bc).elements());assert not added,(label,cat,added)
  if cat=='violations':assert len(removed)==3 and all(json.loads(x)['type']=='starved_thermal' for x in removed)
  else:assert not removed
  delta[label][cat+'_delta']=dict(added=[],removed=[json.loads(x) for x in removed])
 assert delta[label]['opens']==0 and delta[label]['parity']==11
 assert not any(v['type']=='starved_thermal' for v in dr['violations'])
# Exports: every mask, paste, bottom copper, outline and drill identical; only front fill changes.
export={}
for label,folder in [('baseline',B),('selected',C)]:
 out=H/'fabrication'/label;out.mkdir(parents=True,exist_ok=True)
 run(['pcb','export','gerbers','--layers','F.Cu,B.Cu,F.Mask,B.Mask,F.Paste,B.Paste,Edge.Cuts','--output',str(out),str(folder/'stratolink.kicad_pcb')],out/'gerber.log')
 run(['pcb','export','drill','--format','excellon','--excellon-units','mm','--excellon-separate-th','--output',str(out),str(folder/'stratolink.kicad_pcb')],out/'drill.log')
def normalized(p):return '\n'.join(l for l in p.read_text().splitlines() if 'CreationDate' not in l and not l.startswith('G04 Created by') and not l.startswith('; DRILL file'))
for suffix in ['F_Cu.gtl','B_Cu.gbl','F_Mask.gts','B_Mask.gbs','F_Paste.gtp','B_Paste.gbp','Edge_Cuts.gm1','PTH.drl','NPTH.drl']:
 name='stratolink-'+suffix;equal=normalized(H/'fabrication/baseline'/name)==normalized(H/'fabrication/selected'/name)
 assert equal==(suffix!='F_Cu.gtl'),(suffix,equal);export[suffix]='identical' if equal else 'changed_front_ground_fill_only'
result=dict(status='pass',baseline=BASE,candidate=str(C/'stratolink.kicad_pcb'),candidate_sha256=digest(C/'stratolink.kicad_pcb'),allowed_pad_changes=[dict(ref=r,pad=p,zone_connect=int(v)) for (r,p),v in expected.items()],unchanged_schematic_project_tables=True,all_other_board_objects_unchanged_except_refill=True,physical_pad_connectivity_checks=checked,track_only_U7=trackonly,drc=delta,exports=export,library_change_recommendation='Board-position-dependent choices: root combined candidate mirrors U7 pads5/7/8 local no-zone in the existing project-local U7 library to preserve update consistency. This is not generic ST package geometry guidance. Keep J20.5 override board-local; mask/paste/copper dimensions remain unchanged.')
(H/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
