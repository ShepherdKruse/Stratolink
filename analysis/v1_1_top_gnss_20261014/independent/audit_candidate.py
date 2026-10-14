#!/usr/bin/env python3
"""Read-only, hash-bound independent PCB audit. Run with the analysis Python runtime.
The destination must be new. Exact allowed footprint poses/metadata are supplied
by a reviewed declaration; they are never inferred from the edited board.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,subprocess,sys
from shapely import make_valid
from shapely.geometry import Polygon
from shapely.ops import unary_union

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p):return json.loads(p.read_text())
def dump(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def mod(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
p=argparse.ArgumentParser(description=__doc__)
for n in ['repo','before','after','expected-poses','expected-edits','output']:p.add_argument('--'+n,type=Path,required=True)
p.add_argument('--before-sha256',required=True);p.add_argument('--after-sha256',required=True)
p.add_argument('--native-python',type=Path,default=Path('/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3.9'))
p.add_argument('--allowed-route-net',action='append',default=[])
a=p.parse_args();assert sha(a.before)==a.before_sha256;assert sha(a.after)==a.after_sha256
assert not a.output.exists(),('Refusing to replace audit evidence',a.output)
a.output.mkdir(parents=True);out=a.output
root=a.repo/'analysis/v1_1_peer_review_20261014';local=Path(__file__).resolve().parent
used=[Path(__file__).resolve(),local/'extract_full_union.py',root/'digital/verify_rf_scope.py',root/'digital/extract_rf_reference.py',root/'digital/check_rf_reference.py',root/'fabrication/extract_geometry.py',root/'fabrication/screen_geometry.py',a.expected_poses,a.expected_edits]
commands=[]
def run(argv,label):
 argv=[str(v)for v in argv];commands.append(argv)
 r=subprocess.run(argv,capture_output=True,text=True);(out/(label+'.log')).write_text(r.stdout+r.stderr)
 if r.returncode:raise RuntimeError(f'{label} failed; see {out/(label+".log")}')
run([a.native_python,root/'digital/verify_rf_scope.py','--before',a.before,'--after',a.after,'--expected-poses',a.expected_poses,'--expected-edits',a.expected_edits,'--report',out/'scope.json'],'scope')
for name,path in [('before',a.before),('after',a.after)]:
 run([a.native_python,root/'digital/extract_rf_reference.py','--pcb',path,'--output',out/(name+'-reference-geometry.json')],name+'-reference-extraction')
run([sys.executable,root/'digital/check_rf_reference.py','--geometry',out/'after-reference-geometry.json','--output',out/'reference.json'],'reference')
run([a.native_python,local/'extract_full_union.py','--repo',a.repo,'--pcb',a.after,'--output',out/'candidate-geometry.json'],'full-union-extraction')
screen=mod('etch_screen',root/'fabrication/screen_geometry.py');screen.HERE=out;etch=screen.screen('candidate');dump(out/'etch-screen.json',etch)
geom=[load(out/(name+'-reference-geometry.json'))for name in ['before','after']]
assert [g['pcb_sha256']for g in geom]==[a.before_sha256,a.after_sha256]
def key(i):return(i['uuid'],i['layer'])
def shape(i):return unary_union([make_valid(Polygon(p['shell'],p['holes']))for p in i['polygons']])
tracks=[{key(i):i for i in g['items']if i['kind']in['PCB_TRACK','PCB_ARC','PCB_VIA']}for g in geom]
route_changes=[]
for k in sorted(tracks[0].keys()|tracks[1].keys()):
 old,new=(s.get(k)for s in tracks)
 if old!=new:route_changes.append({'uuid':k[0],'layer':k[1],'before_net':old['net']if old else None,'after_net':new['net']if new else None})
changed_nets=sorted({r[n]for r in route_changes for n in ['before_net','after_net']if r[n]is not None})
unknown=set(changed_nets)-set(a.allowed_route_net)
items=[dict(i,g=shape(i))for i in geom[1]['items']]
# Whole-board physical copper graph. A touching pair of orphan graphic islands
# cannot certify one another: a component must lead to an actual same-net pad.
def pieces(g):
 if g.geom_type=='Polygon':return[g]
 if hasattr(g,'geoms'):return[p for q in g.geoms for p in pieces(q)]
 return[]
anchor_by_item={}
for net in sorted({i['net']for i in items if i['kind']=='board_graphic'and i['net']}):
 ni=[i for i in items if i['net']==net]
 comps=[(layer,g)for layer in ['F.Cu','B.Cu']for g in pieces(unary_union([i['g']for i in ni if i['layer']==layer]))]
 parent=list(range(len(comps)))
 def find(n):
  while parent[n]!=n:parent[n]=parent[parent[n]];n=parent[n]
  return n
 def join(ids):
  for n in ids[1:]:parent[find(n)]=find(ids[0])
 touches={key(i):[n for n,(layer,g)in enumerate(comps)if layer==i['layer']and i['g'].intersection(g).area>1e-8]for i in ni if i['kind']in['pad','PCB_VIA','board_graphic']}
 plated={}
 for i in ni:
  if i['kind']in['pad','PCB_VIA']:plated.setdefault(i['uuid'],[]).append(i)
 for group in plated.values():
  if {i['layer']for i in group}=={'F.Cu','B.Cu'}:join(sorted({n for i in group for n in touches[key(i)]}))
 pads_by_root={}
 for i in ni:
  if i['kind']=='pad':
   for n in touches[key(i)]:pads_by_root.setdefault(find(n),set()).add(i['ref']+'.'+i['pin'])
 for i in ni:
  if i['kind']=='board_graphic':anchor_by_item[key(i)]=[sorted(pads_by_root.get(find(n),set()))for n in touches[key(i)]]
contact=[]
for i in items:
 if i['kind']!='board_graphic'or not i['net']:continue
 other=unary_union([j['g']for j in items if j['layer']==i['layer']and j['net']==i['net']and key(i)!=key(j)])
 overlap=i['g'].intersection(other).area;anchors=anchor_by_item[key(i)]
 contact.append({'uuid':i['uuid'],'net':i['net'],'layer':i['layer'],'same_net_overlap_mm2':overlap,'positive_area_contact':overlap>1e-8,'every_physical_component_reaches_same_net_pad':bool(anchors)and all(anchors),'pad_anchors_by_component':anchors})
route_lengths=[]
for net in ['SCL','SDA']:
 net_names=[net,'Net-(U3-'+net+')']
 totals=[sum(i.get('length_mm',0)for i in g['items']if i['net']in net_names and i['kind']in['PCB_TRACK','PCB_ARC'])for g in geom]
 route_lengths.append({'bus':net,'included_nets':net_names,'before_mm':totals[0],'after_mm':totals[1],'delta_mm':totals[1]-totals[0]})
dump(out/'routing-and-graphics.json',{'before_pcb_sha256':a.before_sha256,'pcb_sha256':a.after_sha256,'allowed_changed_route_nets':a.allowed_route_net,'actual_changed_route_nets':changed_nets,'undeclared_route_nets':sorted(unknown),'changes':route_changes,'net_assigned_graphic_contact':contact,'bus_route_lengths':route_lengths})
ref=load(out/'reference.json');scope=load(out/'scope.json')
counts={l:{k:len(v)for k,v in c.items()if isinstance(v,list)}for l,c in etch['layers'].items()}
proj=ref['projection']['trace_beyond_antenna_pad_and_0_15mm_transition']
# Do not collapse RF metrics into a blanket RF performance claim.
checks={'exact_declared_pad_and_pose_scope':True,'expected_259_physical_pads':scope['physical_pad_uuid_net_local_shape_and_transform_checks']==259,'expected_250_logical_connections':scope['logical_pad_connectivity_checks']==250,'native_zero_opens':scope['native_opens']==[0,0],'changed_route_nets_declared':not unknown,'no_screened_etch_candidates':all(n==0 for l in counts.values()for n in l.values()),'all_net_assigned_graphics_have_positive_contact':all(r['positive_area_contact']for r in contact),'all_net_assigned_graphics_reach_same_net_pad':all(r['every_physical_component_reaches_same_net_pad']for r in contact),'sampled_nonpad_front_ground_on_both_sides':all(ref['lateral_front_ground']['summary']['trace_outside_pad_transitions'][side]['no_ground_within_1_5mm_count']==0 for side in ['left','right']),'no_foreign_copper_under_feed_outside_transition':proj['opposite_non_GND_overlap_mm2']<1e-8,'rear_GND_covers_feed_outside_transition_with_5um_polygon_tolerance':proj['rear_GND_missing_beyond_5um_mm2']<1e-8,'receiver_ground_network_connected':ref['receiver_ground_pads_share_return_network'],'nearby_ground_network_connected':ref['all_corridor_ground_connected_to_receiver']}
assert sha(a.before)==a.before_sha256 and sha(a.after)==a.after_sha256
summary={'before_pcb_sha256':a.before_sha256,'pcb_sha256':a.after_sha256,'checks':checks,'all_listed_checks_pass':all(checks.values()),'etch_screen_counts':counts,'lateral_ground_summary':ref['lateral_front_ground']['summary'],'bus_route_lengths':route_lengths,'source_bytes_unchanged':True,'reproduction_commands':commands,'tool_and_declaration_hashes':{str(p):sha(p)for p in used},'limitations':['No CAD writes or zone refill performed. Results refer to saved candidate geometry.','Native DRC/ERC and the exact project/rule configuration are separately verified by the parent review.','Lateral reference metrics are reported, not reduced to an unsupported uniform-impedance claim.','Etch-screen thresholds are inherited from the documented full-copper screen, not supplier process guarantees.']}
dump(out/'summary.json',summary)
dump(out/'evidence-hashes.json',{'pcb_sha256':a.after_sha256,'files':{p.name:sha(p)for p in sorted(out.iterdir())if p.is_file()}})
print(json.dumps(summary,indent=2))
if not summary['all_listed_checks_pass']:sys.exit(2)
