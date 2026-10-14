#!/usr/bin/env python3
"""Read-only rigid-footprint and connectivity check of a bounded RF placement edit."""
from pathlib import Path
import argparse,hashlib,json,sys,math,copy
import pcbnew,wx
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'analysis/v1_1_solar_attachments_20261012/review'))
import check_solar_attachments as audit
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--expected-poses',type=Path,required=True);p.add_argument('--expected-edits',type=Path,help='Exact before/after node lists for footprint model, pad zone_connect, or C5 courtyard only');p.add_argument('--report',type=Path,required=True);args=p.parse_args()
raw=[x.read_bytes()for x in [args.before,args.after]];hashes=[hashlib.sha256(x).hexdigest()for x in raw];app=wx.App(False);boards=[pcbnew.LoadBoard(str(x))for x in [args.before,args.after]];trees=[audit.parse(x.decode())for x in raw]
expected=json.loads(args.expected_poses.read_text());allowed=set(expected)
fps=[{f.GetReference():f for f in b.GetFootprints()}for b in boards];assert fps[0].keys()==fps[1].keys()
ftrees=[{audit.prop(f,'Reference'):f for f in audit.nodes(t,'footprint')}for t in trees]
normalized=copy.deepcopy(ftrees)
edits=json.loads(args.expected_edits.read_text())if args.expected_edits else []
seen=set()
def edited_nodes(target,kind):
 if kind=='courtyard':return[x for x in target if isinstance(x,list)and x and x[0]in['fp_line','fp_arc','fp_rect','fp_poly']and audit.field(x,'layer')in['F.CrtYd','B.CrtYd']]
 return audit.nodes(target,kind)
for edit in edits:
 assert set(edit)=={'ref','pad','kind','before','after'},('Unexpected edit fields',edit)
 ref,pad,kind=edit['ref'],edit['pad'],edit['kind'];key=(ref,pad,kind)
 assert key not in seen and edit['before']!=edit['after'],('Duplicate or no-op edit',key);seen.add(key)
 assert (kind=='model' and pad is None)or(kind=='zone_connect' and pad is not None)or(kind=='courtyard'and ref=='C5'and pad is None),('Unscoped metadata edit',key)
 targets=[]
 for side in normalized:
  target=side[ref]
  if pad is not None:
   found=[x for x in audit.nodes(target,'pad')if x[1]==pad];assert len(found)==1,(ref,pad,'Ambiguous pad');target=found[0]
  targets.append(target)
 for target,name in zip(targets,['before','after']):assert edited_nodes(target,kind)==edit[name],('Unexpected exact node value',key,name,edited_nodes(target,kind),edit[name])
 for target in targets:
  allowed_nodes=edited_nodes(target,kind);target[:]=[x for x in target if x not in allowed_nodes]
for kind in ['general','setup','net','gr_line','gr_arc','gr_rect']:
 assert audit.nodes(trees[0],kind)==audit.nodes(trees[1],kind),('Board invariant changed',kind)
def pose(f):return {'x_mm':f.GetPosition().x/1e6,'y_mm':f.GetPosition().y/1e6,'angle_deg':f.GetOrientationDegrees()%360,'layer':f.GetLayerName()}
def localpad(p):
 return {'number':p.GetNumber(),'net':p.GetNetname(),'local_xy_nm':list(p.GetFPRelativePosition()),'local_angle_deg':p.GetFPRelativeOrientation().AsDegrees(),'size_nm':list(p.GetSize()),'drill_nm':list(p.GetDrillSize()),'offset_nm':list(p.GetOffset()),'shape':int(p.GetShape()),'attribute':int(p.GetAttribute()),'layers':p.GetLayerSet().FmtHex(),'round_ratio':p.GetRoundRectRadiusRatio(),'chamfer_ratio':p.GetChamferRectRatio(),'chamfer_positions':p.GetChamferPositions()}
def without_pose(tree):
 result=copy.deepcopy(tree)
 result[:]=[x for x in result if not(isinstance(x,list)and x and x[0]=='at')]
 for kind in ['pad','property','fp_text']:
  for node in audit.nodes(result,kind):node[:]=[x for x in node if not(isinstance(x,list)and x and x[0]=='at')]
 scalars=[x for x in result if not isinstance(x,list)]
 children=[x for x in result if isinstance(x,list)]
 return scalars+sorted(children,key=lambda x:(x[0],audit.field(x,'uuid')or(str(x[1])if len(x)>1 else '')))
def nearly_identical(a,b):
 if isinstance(a,list)or isinstance(b,list):return isinstance(a,list)and isinstance(b,list)and len(a)==len(b)and all(nearly_identical(x,y)for x,y in zip(a,b))
 if a==b:return True
 try:return abs(float(a)-float(b))<=.000003
 except(ValueError,TypeError):return False
changed=[];pad_count=0
for ref in fps[0]:
 a,b=fps[0][ref],fps[1][ref]
 if ref not in allowed:assert normalized[0][ref]==normalized[1][ref],('Unapproved footprint change',ref)
 else:
  ep=expected[ref];actual=pose(b)
  for k,v in ep.items():assert abs(actual[k]-v)<1e-6 if isinstance(v,(int,float))else actual[k]==v,(ref,k,actual,ep)
  assert a.GetFPID()==b.GetFPID()and a.GetValue()==b.GetValue()and a.GetLayer()==b.GetLayer()
  for kind in ['model','descr','tags','attr','path','sheetname','sheetfile']:
   assert audit.nodes(normalized[0][ref],kind)==audit.nodes(normalized[1][ref],kind),('Footprint metadata/model changed',ref,kind)
  assert {f.GetName():f.GetText()for f in a.GetFields()}=={f.GetName():f.GetText()for f in b.GetFields()},('Footprint properties changed',ref)
  assert nearly_identical(without_pose(normalized[0][ref]),without_pose(normalized[1][ref])),('Footprint local artwork/metadata changed beyond rigid pose and declared edits',ref)
  assert pose(a)!=pose(b),('Unused movement allowance',ref)
  changed.append({'ref':ref,'before':pose(a),'after':actual})
 ap={q.m_Uuid.AsString():q for q in a.Pads()};bp={q.m_Uuid.AsString():q for q in b.Pads()};assert ap.keys()==bp.keys(),('Pad UUIDs changed',ref)
 sourcepads=[audit.keyed(audit.nodes(side[ref],'pad'))for side in normalized]
 for u in ap:
  source_metadata=[[x for x in side[u]if not(isinstance(x,list)and x and x[0]=='at')]for side in sourcepads]
  assert source_metadata[0]==source_metadata[1],('Pad metadata changed beyond declared zone connection',ref,u)
 for u in ap:
  old,new=localpad(ap[u]),localpad(bp[u]);oldxy=old.pop('local_xy_nm');newxy=new.pop('local_xy_nm');assert old==new,('Pad geometry/net changed',ref,u,old,new);assert math.dist(oldxy,newxy)<=3,('Pad failed rigid transform',ref,u,oldxy,newxy);pad_count+=1
# Native connected-pad sets, independently of DRC exclusion list.
groups=[audit.pad_groups(b)for b in boards];assert groups[0].keys()==groups[1].keys();conn=[b.GetConnectivity()for b in boards]
for key in groups[0]:
 ap={q.m_Uuid.AsString():q for q in groups[0][key]};bp={q.m_Uuid.AsString():q for q in groups[1][key]}
 for u in ap:assert audit.connected_keys(conn[0],ap[u])==audit.connected_keys(conn[1],bp[u]),('Connected pad set changed',key,u)
opens=[c.GetUnconnectedCount(False)for c in conn];assert opens==[0,0],opens
tracks=[]
for kind in ['segment','arc','via','gr_poly','zone']:
 a,b=[audit.keyed(audit.nodes(t,kind))for t in trees]
 tracks.append({'kind':kind,'removed':sorted(a.keys()-b.keys()),'added':sorted(b.keys()-a.keys()),'changed':sorted(u for u in a.keys()&b.keys()if a[u]!=b[u])})
assert raw==[x.read_bytes()for x in [args.before,args.after]]
report={'before_sha256':hashes[0],'after_sha256':hashes[1],'declared_changed_poses':changed,'declared_exact_node_edits':edits,'all_other_footprints_exactly_unchanged_except_declared_node_edits':len(fps[0])-len(allowed),'physical_pad_uuid_net_local_shape_and_transform_checks':pad_count,'logical_pad_connectivity_checks':len(groups[0]),'native_opens':opens,'board_setup_net_outline_primitives_unchanged':True,'changes':tracks,'source_bytes_unchanged':True,'limitation':'Rigid pad geometry and logical connectivity are not physical collision, RF performance, thermal or assembly qualification; review complementary mechanical and RF reports.'}
args.report.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items()if k!='changes'},indent=2))
